"""Save, load and render reports."""
from __future__ import annotations

import json
from pathlib import Path


def save_report(report: dict, path: str | Path) -> None:
    Path(path).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")


def load_report(path: str | Path) -> dict:
    try:
        report = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise ValueError(f"Cannot read report {path}: {e}") from e
    if not isinstance(report, dict) or "scenarios" not in report or "model" not in report:
        raise ValueError(f"{path} is not an OpenAffect report (missing 'model'/'scenarios')")
    return report


def _rate(t: dict) -> str:
    return "n/a" if t["pass_rate"] is None else f"{t['pass_rate']:.0%}"


def render_text(report: dict, show_passes: bool = False) -> str:
    m, t = report["model"], report["totals"]
    out = [f"OpenAffect report  model={m['name']} ({m['provider']})  options={m.get('options')}",
           f"created {report['created']}  scenarios={t['scenarios']}  file={report.get('scenario_file', '')}", "",
           f"Checks: {t['passed']} passed, {t['failed']} failed, {t['inconclusive']} inconclusive, "
           f"{t['error']} error  | pass rate (decided checks only): {_rate(t)}", "", "By category:"]
    for cat, ct in report["by_category"].items():
        out.append(f"  {cat:28s} {ct['passed']}/{ct['passed'] + ct['failed']} decided passed"
                   f"  (inconclusive {ct['inconclusive']}, error {ct['error']})")
    out.append("")
    for e in report["scenarios"]:
        bad = [r for r in e["results"] if r["status"] != "passed"]
        if not bad and not show_passes:
            continue
        out.append(f"[{e['scenario_id']}] latency {e['latency_s']}s  expected: {e['expected_behavior']}")
        if e["execution_error"]:
            out.append(f"  EXECUTION ERROR: {e['execution_error']}")
        else:
            out.append(f"  response: {(e['response'] or '').strip()[:400]!r}")
        for r in (e["results"] if show_passes else bad):
            out.append(f"  - {r['status'].upper():12s} {r['check_id']}: {r['explanation']}")
            for ev in r["evidence"]:
                out.append(f"      evidence: {ev}")
        out.append("")
    out.append("Note: " + report["disclaimer"])
    return "\n".join(out)
