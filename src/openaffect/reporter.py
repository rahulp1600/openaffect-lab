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
    if not isinstance(report, dict) or "scenarios" not in report:
        raise ValueError(f"{path} is not an OpenAffect report")
    if "model" not in report and "models" not in report:
        raise ValueError(f"{path} is not an OpenAffect report (missing 'model'/'models')")
    return report


def _rate(t: dict) -> str:
    return "n/a" if t.get("pass_rate") is None else f"{t['pass_rate']:.0%}"


def render_comparison_text(comparison: dict) -> str:
    m = comparison["models"]
    m_a, m_b = m[0], m[1]
    name_a = f"{m_a.get('provider', '')}:{m_a.get('name', 'model_a')}".lstrip(":")
    name_b = f"{m_b.get('provider', '')}:{m_b.get('name', 'model_b')}".lstrip(":")
    sum_a = comparison["summary"].get(name_a, {})
    sum_b = comparison["summary"].get(name_b, {})

    out = [
        f"OpenAffect comparison: {name_a} vs {name_b}",
        f"created {comparison['created']}  scenarios={sum_a.get('scenarios', len(comparison.get('scenarios', [])))}  file={comparison.get('scenario_file', '')}",
        "",
        "OVERALL COMPARISON:",
        f"  {'Metric':<28} {name_a:<22} {name_b:<22}",
        f"  {'-'*28} {'-'*22} {'-'*22}",
        f"  {'Pass Rate (decided)':<28} {_rate(sum_a):<22} {_rate(sum_b):<22}",
        f"  {'Passed Checks':<28} {str(sum_a.get('passed', 0)):<22} {str(sum_b.get('passed', 0)):<22}",
        f"  {'Failed Checks':<28} {str(sum_a.get('failed', 0)):<22} {str(sum_b.get('failed', 0)):<22}",
        f"  {'Inconclusive':<28} {str(sum_a.get('inconclusive', 0)):<22} {str(sum_b.get('inconclusive', 0)):<22}",
        f"  {'Execution Errors':<28} {str(sum_a.get('error', 0)):<22} {str(sum_b.get('error', 0)):<22}",
        f"  {'Avg Latency':<28} {str(sum_a.get('avg_latency_s', 'n/a')) + 's':<22} {str(sum_b.get('avg_latency_s', 'n/a')) + 's':<22}",
        "",
        "BEHAVIORAL DIMENSIONS (Decided Pass Rate):",
        f"  {'Dimension':<34} {name_a:<22} {name_b:<22}",
        f"  {'-'*34} {'-'*22} {'-'*22}",
    ]

    for dim, row in comparison.get("by_behavior", {}).items():
        da, db = row.get(name_a, {}), row.get(name_b, {})
        dec_a = da.get("passed", 0) + da.get("failed", 0)
        dec_b = db.get("passed", 0) + db.get("failed", 0)
        rate_a_str = f"{_rate(da)} ({da.get('passed', 0)}/{dec_a})" if dec_a else "n/a"
        rate_b_str = f"{_rate(db)} ({db.get('passed', 0)}/{dec_b})" if dec_b else "n/a"
        out.append(f"  {dim.replace('_', ' ').capitalize():<34} {rate_a_str:<22} {rate_b_str:<22}")

    out.extend([
        "",
        "SCENARIO CATEGORIES (Decided Pass Rate):",
        f"  {'Category':<34} {name_a:<22} {name_b:<22}",
        f"  {'-'*34} {'-'*22} {'-'*22}",
    ])

    for cat, row in comparison.get("by_category", {}).items():
        ca, cb = row.get(name_a, {}), row.get(name_b, {})
        dec_a = ca.get("passed", 0) + ca.get("failed", 0)
        dec_b = cb.get("passed", 0) + cb.get("failed", 0)
        rate_a_str = f"{_rate(ca)} ({ca.get('passed', 0)}/{dec_a})" if dec_a else "n/a"
        rate_b_str = f"{_rate(cb)} ({cb.get('passed', 0)}/{dec_b})" if dec_b else "n/a"
        out.append(f"  {cat:<34} {rate_a_str:<22} {rate_b_str:<22}")

    divergences = []
    for sc in comparison.get("scenarios", []):
        sid = sc["scenario_id"]
        sa = sc.get(name_a, {})
        sb = sc.get(name_b, {})
        fa, fb = sa.get("failures", []), sb.get("failures", [])
        ea, eb = sa.get("execution_error"), sb.get("execution_error")
        if fa or fb or ea or eb or sa.get("inconclusive") or sb.get("inconclusive"):
            divergences.append((sid, sc.get("expected_behavior", ""), sa, sb))

    if divergences:
        out.extend(["", "DIVERGENCES & FINDINGS:"])
        for sid, exp, sa, sb in divergences:
            out.append(f"[{sid}] expected: {exp}")
            for mname, sm in ((name_a, sa), (name_b, sb)):
                if sm.get("execution_error"):
                    out.append(f"  {mname}: EXECUTION ERROR: {sm['execution_error']}")
                elif sm.get("failures"):
                    for f in sm["failures"]:
                        out.append(f"  {mname}: FAILED {f['check_id']} - {f['explanation']}")
                        for ev in f.get("evidence", []):
                            out.append(f"    evidence: {ev}")
                elif sm.get("inconclusive"):
                    for inc in sm["inconclusive"]:
                        out.append(f"  {mname}: INCONCLUSIVE {inc['check_id']} - {inc['explanation']}")
                else:
                    out.append(f"  {mname}: ALL CHECKS PASSED")
            out.append("")

    out.append("Note: " + comparison.get("disclaimer", ""))
    return "\n".join(out)


def render_text(report: dict, show_passes: bool = False) -> str:
    if report.get("type") == "comparison" or "models" in report:
        return render_comparison_text(report)
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
