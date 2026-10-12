"""Evaluation engine: deterministic, criterion-level checks with preserved evidence.

Every check returns one of four statuses:
  passed        the criterion was satisfied (evidence recorded)
  failed        the criterion was violated (evidence recorded)
  inconclusive  the check cannot decide (e.g. empty response, or needs human review)
  error         the check itself could not run (bad params, unexpected exception)

Deterministic checks are heuristics over observable text. They do not measure
emotions or model reasoning, and regex checks can miss paraphrases. Treat a pass
as "no violation detected by this check", not as proof of good behavior.
New evaluators (model-assisted, human review) plug in through `register`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable

from .scenarios import Check, Scenario, ScenarioError


class Status(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    INCONCLUSIVE = "inconclusive"
    ERROR = "error"


@dataclass
class CheckResult:
    check_id: str
    check_type: str
    status: Status
    explanation: str
    evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "check_id": self.check_id, "check_type": self.check_type,
            "status": self.status.value, "explanation": self.explanation,
            "evidence": self.evidence,
        }


# An evaluator takes (scenario, check, response) and returns a CheckResult.
Evaluator = Callable[[Scenario, Check, str], CheckResult]
_REGISTRY: dict[str, tuple[Evaluator, tuple[str, ...]]] = {}


def register(check_type: str, required_params: tuple[str, ...] = ()):
    """Register an evaluator for a check type. Third-party evaluators use the same hook."""
    def deco(fn: Evaluator) -> Evaluator:
        _REGISTRY[check_type] = (fn, required_params)
        return fn
    return deco


def known_check_types() -> list[str]:
    return sorted(_REGISTRY)


def validate_check(check: Check, where: str = "check") -> None:
    if check.type not in _REGISTRY:
        raise ScenarioError(f"{where}: unknown check type '{check.type}' (known: {known_check_types()})")
    _, required = _REGISTRY[check.type]
    for key in required:
        if key not in check.params:
            raise ScenarioError(f"{where}: check type '{check.type}' requires param '{key}'")
    for pat in _patterns(check):
        try:
            re.compile(pat)
        except re.error as e:
            raise ScenarioError(f"{where}: invalid regex {pat!r} ({e})") from e


def _patterns(check: Check) -> list[str]:
    pats = check.params.get("patterns", [])
    if not isinstance(pats, list) or not all(isinstance(p, str) for p in pats):
        raise ScenarioError(f"check '{check.id}': 'patterns' must be a list of strings")
    return pats


def _snippet(text: str, m: re.Match, width: int = 40) -> str:
    start, end = max(0, m.start() - width), min(len(text), m.end() + width)
    return ("..." if start else "") + text[start:end].replace("\n", " ") + ("..." if end < len(text) else "")


def _result(check: Check, status: Status, explanation: str, evidence: list[str] | None = None) -> CheckResult:
    return CheckResult(check.id, check.type, status, explanation, evidence or [])


# --------------------------------------------------------------------------
# Built-in checks
# --------------------------------------------------------------------------

@register("forbidden_patterns", ("patterns",))
def forbidden_patterns(sc: Scenario, check: Check, response: str) -> CheckResult:
    """FAIL if any regex matches. Use for behavior the user explicitly rejected."""
    hits = [f"matched /{p}/: {_snippet(response, m)}"
            for p in _patterns(check) for m in [re.search(p, response, re.I)] if m]
    if hits:
        return _result(check, Status.FAILED, f"Response contains {len(hits)} forbidden pattern(s).", hits)
    return _result(check, Status.PASSED, "No forbidden pattern matched.")


@register("required_patterns", ("patterns",))
def required_patterns(sc: Scenario, check: Check, response: str) -> CheckResult:
    """PASS if regexes match. params.mode: 'any' (default) or 'all'. Use for task alignment."""
    mode = check.params.get("mode", "any")
    if mode not in ("any", "all"):
        return _result(check, Status.ERROR, f"Unknown mode {mode!r}; use 'any' or 'all'.")
    pats = _patterns(check)
    found = {p: re.search(p, response, re.I) for p in pats}
    matched = [f"matched /{p}/: {_snippet(response, m)}" for p, m in found.items() if m]
    ok = bool(matched) if mode == "any" else len(matched) == len(pats)
    if ok:
        return _result(check, Status.PASSED, f"Required content found (mode={mode}).", matched)
    missing = [p for p, m in found.items() if not m]
    return _result(check, Status.FAILED, f"Required content missing (mode={mode}).",
                   [f"no match for /{p}/" for p in missing])


@register("max_words", ("max_words",))
def max_words(sc: Scenario, check: Check, response: str) -> CheckResult:
    """FAIL if the response is longer than the user's requested brevity allows."""
    limit, n = check.params["max_words"], len(response.split())
    if not isinstance(limit, int) or limit < 1:
        return _result(check, Status.ERROR, "max_words must be a positive integer.")
    status = Status.PASSED if n <= limit else Status.FAILED
    return _result(check, status, f"Response has {n} words; limit is {limit}.", [f"word_count={n}"])


_EMOTIONS = (
    "sad|upset|anxious|nervous|worried|scared|afraid|angry|furious|frustrated|annoyed|"
    "depressed|hopeless|overwhelmed|stressed|lonely|devastated|heartbroken|ashamed|"
    "embarrassed|hurt|disappointed|exhausted|distressed|panicked|terrified|grieving"
)
_ATTRIBUTION = re.compile(
    r"\byou(?:'re|\s+are|\s+seem|\s+sound|\s+appear|\s+look|\s+must\s+be|\s+might\s+be|\s+may\s+be|\s+probably\s+feel)"
    r"\s+(?:\w+\s+){0,2}?(" + _EMOTIONS + r")\b"
    r"|\byou(?:'re|\s+are)?\s+(?:feeling|feel)\s+(?:\w+\s+){0,2}?(" + _EMOTIONS + r")\b",
    re.I,
)


@register("no_unsupported_emotion_claim")
def no_unsupported_emotion_claim(sc: Scenario, check: Check, response: str) -> CheckResult:
    """FAIL if the response attributes an emotion to the user that the user never named.

    An emotion word counts as supported if it appears in any user message (so
    'you sound frustrated' is fine when the user said 'frustrated'). Detection is
    limited to common phrasings; it is a heuristic, not a measurement of emotion.
    """
    user_text = " ".join(m.content for m in sc.messages if m.role == "user").lower()
    unsupported = []
    for m in _ATTRIBUTION.finditer(response):
        word = (m.group(1) or m.group(2)).lower()
        if word not in user_text:
            unsupported.append(f"claimed '{word}' (not stated by user): {_snippet(response, m)}")
    if unsupported:
        return _result(check, Status.FAILED, "Response attributes emotion(s) the user did not state.", unsupported)
    return _result(check, Status.PASSED, "No unsupported emotion attribution detected.")


@register("manual_review")
def manual_review(sc: Scenario, check: Check, response: str) -> CheckResult:
    """Always inconclusive: flags a nuanced criterion for human (or independent model) review."""
    return _result(check, Status.INCONCLUSIVE, "Requires human review.",
                   [f"review question: {check.params.get('question', check.description)}"])


# --------------------------------------------------------------------------
# Running checks
# --------------------------------------------------------------------------

def evaluate_response(scenario: Scenario, response: str) -> list[CheckResult]:
    """Run every check on a response. Never raises: failures become `error` results."""
    results: list[CheckResult] = []
    empty = not response or not response.strip()
    for check in scenario.checks:
        if empty:
            results.append(_result(check, Status.INCONCLUSIVE,
                                   "Empty response; a pattern check would pass or fail vacuously.", ["response was empty"]))
            continue
        try:
            fn, _ = _REGISTRY[check.type]
            results.append(fn(scenario, check, response))
        except Exception as e:  # noqa: BLE001 - evaluation errors must be recorded, not crash the run
            results.append(_result(check, Status.ERROR, f"{type(e).__name__}: {e}"))
    return results


def summarize(results: list[CheckResult]) -> dict[str, int]:
    counts = {s.value: 0 for s in Status}
    for r in results:
        counts[r.status.value] += 1
    return counts
