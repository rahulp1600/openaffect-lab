"""Runs scenarios through an adapter, evaluates responses, and builds a report dict."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

from . import __version__
from .evaluator import CheckResult, Status, evaluate_response, summarize
from .scenarios import Scenario

DISCLAIMER = ("Results describe behavior on these scenarios only, judged by the listed heuristic checks. "
              "They are not a measure of emotional intelligence, and failures are observations, "
              "not explanations of the model's internal reasoning.")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def run_scenarios(scenarios: list[Scenario], adapter, scenario_file: str = "", progress=None) -> dict:
    entries = []
    for i, sc in enumerate(scenarios, start=1):
        if progress:
            progress(i, len(scenarios), sc.id)
        gen = adapter.generate([{"role": m.role, "content": m.content} for m in sc.messages])
        if gen.error or gen.text is None:
            results = [CheckResult(c.id, c.type, Status.ERROR, f"No response to evaluate: {gen.error}")
                       for c in sc.checks]
        else:
            results = evaluate_response(sc, gen.text)
        checks_meta = {c.id: c for c in sc.checks}
        entries.append({
            "scenario_id": sc.id, "category": sc.category, "pair_id": sc.pair_id, "variant": sc.variant,
            "behavior_tested": sc.behavior_tested, "expected_behavior": sc.expected_behavior,
            "timestamp": _now(), "response": gen.text, "latency_s": round(gen.latency_s, 3),
            "execution_error": gen.error,
            "results": [{**r.to_dict(), "description": checks_meta[r.check_id].description,
                         "rationale": checks_meta[r.check_id].rationale} for r in results],
            "summary": summarize(results),
        })
    return {
        "openaffect_version": __version__, "created": _now(), "scenario_file": scenario_file,
        "model": adapter.describe(), "scenarios": entries,
        "totals": aggregate(entries), "by_category": aggregate_by_category(entries),
        "disclaimer": DISCLAIMER,
    }


def aggregate(entries: list[dict]) -> dict:
    t = {"passed": 0, "failed": 0, "inconclusive": 0, "error": 0}
    for e in entries:
        for k, v in e["summary"].items():
            t[k] += v
    decided = t["passed"] + t["failed"]
    t["pass_rate"] = round(t["passed"] / decided, 3) if decided else None  # excludes inconclusive/error
    t["scenarios"] = len(entries)
    t["scenarios_with_failures"] = sum(1 for e in entries if e["summary"]["failed"])
    return t


def aggregate_by_category(entries: list[dict]) -> dict:
    groups = defaultdict(list)
    for e in entries:
        groups[e["category"]].append(e)
    return {cat: aggregate(es) for cat, es in sorted(groups.items())}
