"""Scenario data model and JSONL loader.

A scenario is a scripted multi-turn conversation that ends with a user message,
plus explicit, scenario-specific checks. Scenarios are synthetic; they contain
no real personal conversations.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

VALID_ROLES = {"user", "assistant"}


class ScenarioError(ValueError):
    """Raised when a scenario file or record is malformed."""


@dataclass(frozen=True)
class Message:
    role: str
    content: str


@dataclass(frozen=True)
class Check:
    id: str
    type: str
    description: str
    rationale: str
    params: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Scenario:
    id: str
    category: str
    description: str
    messages: tuple[Message, ...]
    behavior_tested: str
    expected_behavior: str
    checks: tuple[Check, ...]
    pair_id: str | None = None   # links counterfactual variants of one situation
    variant: str | None = None   # e.g. "baseline" or "with_boundary"
    metadata: dict = field(default_factory=dict)


def _req(rec: dict, key: str, where: str):
    if not isinstance(rec, dict) or key not in rec or rec[key] in (None, "", [], {}):
        raise ScenarioError(f"{where}: missing required field '{key}'")
    return rec[key]


def parse_scenario(rec: dict, where: str = "record") -> Scenario:
    if not isinstance(rec, dict):
        raise ScenarioError(f"{where}: expected a JSON object")
    messages = []
    for i, m in enumerate(_req(rec, "messages", where)):
        if not isinstance(m, dict) or m.get("role") not in VALID_ROLES or not str(m.get("content", "")).strip():
            raise ScenarioError(f"{where}: messages[{i}] needs role in {sorted(VALID_ROLES)} and non-empty content")
        messages.append(Message(m["role"], m["content"]))
    if messages[-1].role != "user":
        raise ScenarioError(f"{where}: the last message must be from the user")

    checks = []
    for i, c in enumerate(_req(rec, "checks", where)):
        cw = f"{where}: checks[{i}]"
        checks.append(Check(
            id=_req(c, "id", cw), type=_req(c, "type", cw),
            description=_req(c, "description", cw), rationale=_req(c, "rationale", cw),
            params=c.get("params", {}),
        ))
    if len({c.id for c in checks}) != len(checks):
        raise ScenarioError(f"{where}: duplicate check ids")

    return Scenario(
        id=_req(rec, "id", where), category=_req(rec, "category", where),
        description=_req(rec, "description", where), messages=tuple(messages),
        behavior_tested=_req(rec, "behavior_tested", where),
        expected_behavior=_req(rec, "expected_behavior", where),
        checks=tuple(checks), pair_id=rec.get("pair_id"), variant=rec.get("variant"),
        metadata=rec.get("metadata", {}),
    )


def load_scenarios(path: str | Path, validate_checks: bool = True) -> list[Scenario]:
    """Load scenarios from a JSONL file (one JSON object per line; blank lines ignored)."""
    from .evaluator import validate_check  # local import avoids a cycle

    path = Path(path)
    scenarios: list[Scenario] = []
    seen: set[str] = set()
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        where = f"{path.name}:{lineno}"
        try:
            rec = json.loads(line)
        except json.JSONDecodeError as e:
            raise ScenarioError(f"{where}: invalid JSON ({e})") from e
        sc = parse_scenario(rec, where)
        if sc.id in seen:
            raise ScenarioError(f"{where}: duplicate scenario id '{sc.id}'")
        seen.add(sc.id)
        if validate_checks:
            for c in sc.checks:
                validate_check(c, f"{where} ({sc.id}/{c.id})")
        scenarios.append(sc)
    if not scenarios:
        raise ScenarioError(f"{path}: no scenarios found")
    return scenarios
