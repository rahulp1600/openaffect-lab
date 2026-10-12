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


def classify_check_behavior(entry: dict, check_result: dict) -> str | None:
    """Classify a check into one of four behavioral dimensions where supported.

    - unsupported_emotion_attribution: check_type == 'no_unsupported_emotion_claim'
    - boundary_respect: forbidden_patterns in explicit boundary / with_boundary contexts
    - context_adaptation: forbidden_patterns in user_correction, context_shift, sarcasm, ambiguous contexts
    - task_responsiveness: required_patterns and max_words checks
    Returns None if the check cannot be confidently classified (e.g. manual tone review).
    """
    ctype = check_result.get("check_type")
    cat = entry.get("category")
    var = entry.get("variant")

    if ctype == "no_unsupported_emotion_claim":
        return "unsupported_emotion_attribution"
    if ctype == "forbidden_patterns" and (var == "with_boundary" or cat == "explicit_boundary"):
        return "boundary_respect"
    if ctype == "forbidden_patterns" and cat in ("user_correction", "context_shift", "sarcasm_misleading_cue", "ambiguous_language"):
        return "context_adaptation"
    if ctype in ("required_patterns", "max_words"):
        return "task_responsiveness"
    return None


def aggregate_by_behavior(entries: list[dict]) -> dict:
    """Aggregate check counts and pass rates for each behavioral dimension."""
    groups = defaultdict(lambda: {"passed": 0, "failed": 0, "inconclusive": 0, "error": 0})
    for e in entries:
        for r in e.get("results", []):
            dim = classify_check_behavior(e, r)
            if dim:
                groups[dim][r["status"]] += 1

    out = {}
    for dim, counts in sorted(groups.items()):
        decided = counts["passed"] + counts["failed"]
        counts["pass_rate"] = round(counts["passed"] / decided, 3) if decided else None
        out[dim] = dict(counts)
    return out


def compare_reports(report_a: dict, report_b: dict) -> dict:
    """Compare two scenario evaluation reports side-by-side."""
    model_a = report_a["model"]
    model_b = report_b["model"]
    name_a = f"{model_a.get('provider', '')}:{model_a.get('name', 'model_a')}".lstrip(":")
    name_b = f"{model_b.get('provider', '')}:{model_b.get('name', 'model_b')}".lstrip(":")

    lat_a = [e["latency_s"] for e in report_a.get("scenarios", []) if e.get("latency_s") is not None]
    lat_b = [e["latency_s"] for e in report_b.get("scenarios", []) if e.get("latency_s") is not None]
    avg_lat_a = round(sum(lat_a) / len(lat_a), 3) if lat_a else 0.0
    avg_lat_b = round(sum(lat_b) / len(lat_b), 3) if lat_b else 0.0

    behav_a = aggregate_by_behavior(report_a.get("scenarios", []))
    behav_b = aggregate_by_behavior(report_b.get("scenarios", []))
    all_behaviors = sorted(set(behav_a.keys()) | set(behav_b.keys()))

    all_categories = sorted(set(report_a.get("by_category", {}).keys()) | set(report_b.get("by_category", {}).keys()))

    scenarios_b = {e["scenario_id"]: e for e in report_b.get("scenarios", [])}
    per_scenario = []

    for ea in report_a.get("scenarios", []):
        sid = ea["scenario_id"]
        eb = scenarios_b.get(sid, {})
        per_scenario.append({
            "scenario_id": sid,
            "category": ea.get("category"),
            "pair_id": ea.get("pair_id"),
            "variant": ea.get("variant"),
            "expected_behavior": ea.get("expected_behavior"),
            name_a: {
                "latency_s": ea.get("latency_s"),
                "execution_error": ea.get("execution_error"),
                "summary": ea.get("summary", {}),
                "failures": [r for r in ea.get("results", []) if r.get("status") == Status.FAILED.value],
                "inconclusive": [r for r in ea.get("results", []) if r.get("status") == Status.INCONCLUSIVE.value],
                "response": ea.get("response"),
            },
            name_b: {
                "latency_s": eb.get("latency_s"),
                "execution_error": eb.get("execution_error"),
                "summary": eb.get("summary", {}),
                "failures": [r for r in eb.get("results", []) if r.get("status") == Status.FAILED.value],
                "inconclusive": [r for r in eb.get("results", []) if r.get("status") == Status.INCONCLUSIVE.value],
                "response": eb.get("response"),
            },
        })

    return {
        "openaffect_version": __version__,
        "created": _now(),
        "type": "comparison",
        "scenario_file": report_a.get("scenario_file") or report_b.get("scenario_file", ""),
        "models": [model_a, model_b],
        "summary": {
            name_a: {**report_a["totals"], "avg_latency_s": avg_lat_a},
            name_b: {**report_b["totals"], "avg_latency_s": avg_lat_b},
        },
        "by_behavior": {
            dim: {
                name_a: behav_a.get(dim, {"passed": 0, "failed": 0, "inconclusive": 0, "error": 0, "pass_rate": None}),
                name_b: behav_b.get(dim, {"passed": 0, "failed": 0, "inconclusive": 0, "error": 0, "pass_rate": None}),
            }
            for dim in all_behaviors
        },
        "by_category": {
            cat: {
                name_a: report_a.get("by_category", {}).get(cat, {"passed": 0, "failed": 0, "inconclusive": 0, "error": 0, "pass_rate": None}),
                name_b: report_b.get("by_category", {}).get(cat, {"passed": 0, "failed": 0, "inconclusive": 0, "error": 0, "pass_rate": None}),
            }
            for cat in all_categories
        },
        "scenarios": per_scenario,
        "disclaimer": DISCLAIMER,
    }
