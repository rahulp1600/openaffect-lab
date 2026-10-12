#!/usr/bin/env python3
"""
generate_dashboard.py
Generates a standalone, reproducible HTML evaluation dashboard for OpenAffect Lab
from a comparison or evaluation JSON report.

Zero runtime dependencies: uses only the Python standard library.
"""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional


def load_report(report_path: Path) -> Dict[str, Any]:
    """Load and parse the JSON report file safely."""
    if not report_path.exists():
        print(f"Error: Report file not found at '{report_path}'.", file=sys.stderr)
        print("Run an evaluation or pass a valid report path using --input.", file=sys.stderr)
        sys.exit(1)

    try:
        with open(report_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as exc:
        print(f"Error: Failed to parse JSON report '{report_path}': {exc}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"Error: Unexpected error reading '{report_path}': {exc}", file=sys.stderr)
        sys.exit(1)

    if not isinstance(data, dict):
        print(f"Error: Expected root JSON object in '{report_path}', got {type(data).__name__}.", file=sys.stderr)
        sys.exit(1)

    return data


def format_model_label(model_key: str, models_info: List[Dict[str, Any]]) -> str:
    """Format a model key into a clean display title."""
    for m in models_info:
        if isinstance(m, dict):
            provider = m.get("provider", "")
            name = m.get("name", "")
            combined = f"{provider}:{name}" if provider else name
            if combined == model_key:
                return f"{name} ({provider})" if provider else name

    # Fallback if not matched in models list
    if ":" in model_key:
        parts = model_key.split(":", 1)
        return f"{parts[1]} ({parts[0]})"
    return model_key


def get_scenario_status(model_data: Dict[str, Any]) -> str:
    """Determine the top-level outcome status for a model in a scenario."""
    if not isinstance(model_data, dict):
        return "UNKNOWN"
    if model_data.get("execution_error"):
        return "ERROR"
    summary = model_data.get("summary", {})
    if summary.get("failed", 0) > 0 or len(model_data.get("failures", [])) > 0:
        return "FAILED"
    if summary.get("inconclusive", 0) > 0 or len(model_data.get("inconclusive", [])) > 0:
        return "INCONCLUSIVE"
    if summary.get("error", 0) > 0:
        return "ERROR"
    return "PASSED"


def generate_html(report: Dict[str, Any]) -> str:
    """Build the complete, standalone HTML document from the report dictionary."""
    version = html.escape(str(report.get("openaffect_version", "0.1.0")))
    created_at = html.escape(str(report.get("created", "Unknown")))
    scenario_file = html.escape(str(report.get("scenario_file", "scenarios/core.jsonl")))
    report_type = html.escape(str(report.get("type", "evaluation")).title())
    disclaimer_text = html.escape(
        str(
            report.get(
                "disclaimer",
                "Results describe behavior on these scenarios only, judged by heuristic checks.",
            )
        )
    )

    models_info = report.get("models", [])
    summary_data = report.get("summary", {})
    by_behavior = report.get("by_behavior", {})
    by_category = report.get("by_category", {})
    scenarios = report.get("scenarios", [])

    model_keys = list(summary_data.keys())
    if not model_keys and models_info:
        for m in models_info:
            p = m.get("provider")
            n = m.get("name")
            k = f"{p}:{n}" if p else n
            if k:
                model_keys.append(k)

    # 1. KPI Cards HTML
    kpi_cards_html = []
    for m_key in model_keys:
        m_summary = summary_data.get(m_key, {})
        m_display = html.escape(format_model_label(m_key, models_info))
        passed = m_summary.get("passed", 0)
        failed = m_summary.get("failed", 0)
        inconclusive = m_summary.get("inconclusive", 0)
        errors = m_summary.get("error", 0)
        total_decided = passed + failed
        pass_rate_val = m_summary.get("pass_rate")
        if pass_rate_val is not None:
            pass_rate_str = f"{pass_rate_val * 100:.1f}%"
        elif total_decided > 0:
            pass_rate_str = f"{(passed / total_decided) * 100:.1f}%"
        else:
            pass_rate_str = "N/A"

        scenarios_total = m_summary.get("scenarios", len(scenarios))
        scenarios_failed = m_summary.get("scenarios_with_failures", 0)

        latency_html = ""
        avg_latency = m_summary.get("avg_latency_s")
        if avg_latency is not None:
            latency_html = f"""
            <div class="kpi-metric-row">
              <span class="label">Avg Response Latency</span>
              <span class="value">{avg_latency:.2f}s</span>
            </div>
            """

        kpi_cards_html.append(f"""
        <div class="card kpi-card">
          <div class="kpi-model-badge">{m_display}</div>
          <div class="kpi-headline">
            <span class="kpi-number">{pass_rate_str}</span>
            <span class="kpi-subtext">Pass Rate (Decided Checks)</span>
          </div>
          <div class="kpi-stats">
            <div class="stat-pill stat-pass"><span>{passed}</span> Passed</div>
            <div class="stat-pill stat-fail"><span>{failed}</span> Failed</div>
            <div class="stat-pill stat-inc"><span>{inconclusive}</span> Inconclusive</div>
            {f'<div class="stat-pill stat-err"><span>{errors}</span> Error</div>' if errors > 0 else ''}
          </div>
          <div class="kpi-divider"></div>
          <div class="kpi-metrics">
            <div class="kpi-metric-row">
              <span class="label">Total Scenarios</span>
              <span class="value">{scenarios_total}</span>
            </div>
            <div class="kpi-metric-row">
              <span class="label">Scenarios with Failures</span>
              <span class="value">{scenarios_failed}</span>
            </div>
            {latency_html}
          </div>
        </div>
        """)

    # 2. Behavioral Dimensions Comparison
    behavior_rows_html = []
    for b_key, b_models in by_behavior.items():
        b_label = html.escape(b_key.replace("_", " ").title())
        cells = []
        for m_key in model_keys:
            m_stat = b_models.get(m_key, {})
            b_pass = m_stat.get("passed", 0)
            b_fail = m_stat.get("failed", 0)
            b_rate = m_stat.get("pass_rate")
            if b_rate is not None:
                rate_pct = b_rate * 100
                rate_str = f"{rate_pct:.0f}%"
            else:
                total = b_pass + b_fail
                rate_pct = (b_pass / total * 100) if total > 0 else 0
                rate_str = f"{rate_pct:.0f}%"

            bar_color = "var(--color-pass)" if rate_pct >= 90 else ("var(--color-fail)" if rate_pct < 80 else "var(--color-warn)")

            cells.append(f"""
            <div class="dim-cell">
              <div class="dim-header">
                <span class="dim-rate">{rate_str}</span>
                <span class="dim-counts">{b_pass} passed / {b_fail} failed</span>
              </div>
              <div class="progress-bar-bg">
                <div class="progress-bar-fill" style="width: {rate_pct}%; background: {bar_color};"></div>
              </div>
            </div>
            """)

        behavior_rows_html.append(f"""
        <div class="dim-row">
          <div class="dim-name-col">
            <strong>{b_label}</strong>
          </div>
          <div class="dim-models-grid" style="grid-template-columns: repeat({len(model_keys)}, 1fr);">
            {"".join(cells)}
          </div>
        </div>
        """)

    # 3. Scenario Categories Comparison
    category_rows_html = []
    for c_key, c_models in by_category.items():
        c_label = html.escape(c_key.replace("_", " ").title())
        cat_cells = []
        for m_key in model_keys:
            c_stat = c_models.get(m_key, {})
            c_pass = c_stat.get("passed", 0)
            c_fail = c_stat.get("failed", 0)
            c_inc = c_stat.get("inconclusive", 0)
            c_rate = c_stat.get("pass_rate")
            rate_str = f"{c_rate * 100:.0f}%" if c_rate is not None else "N/A"
            badge_cls = "badge-pass" if c_fail == 0 else "badge-fail"
            cat_cells.append(f"""
            <td class="cat-cell">
              <span class="badge {badge_cls}">{rate_str}</span>
              <span class="cat-detail">({c_pass}P / {c_fail}F{f' / {c_inc}I' if c_inc else ''})</span>
            </td>
            """)
        category_rows_html.append(f"""
        <tr>
          <td class="cat-title-cell"><code>{c_label}</code></td>
          {"".join(cat_cells)}
        </tr>
        """)

    category_headers = "".join(
        f"<th>{html.escape(format_model_label(m_key, models_info))}</th>"
        for m_key in model_keys
    )

    # 4. Scenario-Level Breakdown Cards
    scenarios_cards_html = []
    for sc in scenarios:
        sc_id = html.escape(sc.get("scenario_id", "unknown"))
        sc_cat = html.escape(sc.get("category", "").replace("_", " ").title())
        sc_pair = sc.get("pair_id")
        sc_variant = sc.get("variant")
        expected_behavior = html.escape(sc.get("expected_behavior", "Not specified"))

        pair_badge = f'<span class="badge badge-neutral">Pair: {html.escape(sc_pair)}</span>' if sc_pair else ""
        variant_badge = ""
        if sc_variant == "baseline":
            variant_badge = '<span class="badge badge-info">Variant: Baseline</span>'
        elif sc_variant == "with_boundary":
            variant_badge = '<span class="badge badge-purple">Variant: With Boundary</span>'
        elif sc_variant:
            variant_badge = f'<span class="badge badge-info">Variant: {html.escape(sc_variant)}</span>'

        model_eval_cards = []
        for m_key in model_keys:
            m_display = html.escape(format_model_label(m_key, models_info))
            m_eval = sc.get(m_key, {})
            status = get_scenario_status(m_eval)

            status_badge_cls = {
                "PASSED": "badge-pass",
                "FAILED": "badge-fail",
                "INCONCLUSIVE": "badge-inc",
                "ERROR": "badge-err",
                "UNKNOWN": "badge-neutral",
            }.get(status, "badge-neutral")

            summary_box = m_eval.get("summary", {})
            p_cnt = summary_box.get("passed", 0)
            f_cnt = summary_box.get("failed", 0)
            i_cnt = summary_box.get("inconclusive", 0)

            lat = m_eval.get("latency_s")
            lat_str = f"{lat:.2f}s" if lat is not None else "N/A"

            # Failures details
            failures_html = ""
            failures_list = m_eval.get("failures", [])
            if failures_list:
                failure_items = []
                for fail in failures_list:
                    cid = html.escape(fail.get("check_id", "unknown"))
                    ctype = html.escape(fail.get("check_type", ""))
                    expl = html.escape(fail.get("explanation", ""))
                    evidence_lines = fail.get("evidence", [])
                    evidence_rendered = "".join(
                        f"<code>{html.escape(line)}</code><br/>" for line in evidence_lines
                    ) if evidence_lines else "<em>None</em>"

                    failure_items.append(f"""
                    <div class="evidence-block fail-block">
                      <div class="evidence-title">
                        <span class="badge badge-fail">Failed Check</span>
                        <strong>{cid}</strong> <span class="check-type">({ctype})</span>
                      </div>
                      <div class="evidence-desc">{expl}</div>
                      <div class="evidence-snippet">
                        <div class="snippet-label">Evidence:</div>
                        <div class="snippet-body">{evidence_rendered}</div>
                      </div>
                    </div>
                    """)
                failures_html = "".join(failure_items)

            # Inconclusive details
            inc_html = ""
            inc_list = m_eval.get("inconclusive", [])
            if inc_list:
                inc_items = []
                for item in inc_list:
                    cid = html.escape(item.get("check_id", "unknown"))
                    ctype = html.escape(item.get("check_type", ""))
                    expl = html.escape(item.get("explanation", ""))
                    evidence_lines = item.get("evidence", [])
                    evidence_rendered = "".join(
                        f"<code>{html.escape(line)}</code><br/>" for line in evidence_lines
                    ) if evidence_lines else "<em>None</em>"

                    inc_items.append(f"""
                    <div class="evidence-block inc-block">
                      <div class="evidence-title">
                        <span class="badge badge-inc">Manual Review Required</span>
                        <strong>{cid}</strong> <span class="check-type">({ctype})</span>
                      </div>
                      <div class="evidence-desc">{expl}</div>
                      <div class="evidence-snippet">
                        <div class="snippet-label">Review Guidance:</div>
                        <div class="snippet-body">{evidence_rendered}</div>
                      </div>
                    </div>
                    """)
                inc_html = "".join(inc_items)

            # Model Response Text
            resp = m_eval.get("response")
            resp_html = ""
            if resp:
                resp_escaped = html.escape(resp)
                resp_html = f"""
                <details class="response-drawer">
                  <summary>View Model Response</summary>
                  <pre class="response-text">{resp_escaped}</pre>
                </details>
                """

            model_eval_cards.append(f"""
            <div class="scenario-model-col">
              <div class="scenario-model-header">
                <strong>{m_display}</strong>
                <span class="badge {status_badge_cls}">{status}</span>
              </div>
              <div class="scenario-model-meta">
                <span>Checks: {p_cnt}P / {f_cnt}F / {i_cnt}I</span>
                {f'<span class="lat-badge">Latency: {lat_str}</span>' if lat is not None else ''}
              </div>
              {failures_html}
              {inc_html}
              {resp_html}
            </div>
            """)

        scenarios_cards_html.append(f"""
        <div class="card scenario-card">
          <div class="scenario-header">
            <div class="scenario-title-area">
              <h3 class="scenario-id">{sc_id}</h3>
              <div class="scenario-tags">
                <span class="badge badge-neutral">{sc_cat}</span>
                {pair_badge}
                {variant_badge}
              </div>
            </div>
          </div>
          <div class="scenario-expectations">
            <span class="expect-label">Expected Behavior:</span>
            <span class="expect-text">{expected_behavior}</span>
          </div>
          <div class="scenario-models-grid" style="grid-template-columns: repeat({len(model_keys)}, 1fr);">
            {"".join(model_eval_cards)}
          </div>
        </div>
        """)

    # Dimension column headers
    dim_col_headers = "".join(
        f'<div class="dim-head-col">{html.escape(format_model_label(m_key, models_info))}</div>'
        for m_key in model_keys
    )

    full_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>OpenAffect Lab - Evaluation Dashboard</title>
  <style>
    :root {{
      --bg-base: #0B0F19;
      --bg-surface: #111827;
      --bg-card: #182234;
      --bg-hover: #1f2d45;
      --border-color: #24324a;
      --border-light: #324361;

      --text-main: #F3F4F6;
      --text-muted: #9CA3AF;
      --text-sub: #6B7280;

      --accent-blue: #3B82F6;
      --accent-indigo: #6366F1;
      --accent-purple: #8B5CF6;

      --color-pass: #10B981;
      --color-pass-bg: rgba(16, 185, 129, 0.12);
      --color-fail: #F43F5E;
      --color-fail-bg: rgba(244, 63, 94, 0.12);
      --color-warn: #F59E0B;
      --color-warn-bg: rgba(245, 158, 11, 0.12);
      --color-err: #A855F7;
      --color-err-bg: rgba(168, 85, 247, 0.12);
    }}

    * {{
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }}

    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif, "Apple Color Emoji", "Segoe UI Emoji";
      background-color: var(--bg-base);
      color: var(--text-main);
      line-height: 1.5;
      padding: 0 0 60px 0;
      -webkit-font-smoothing: antialiased;
    }}

    code, pre {{
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
    }}

    .container {{
      max-width: 1240px;
      margin: 0 auto;
      padding: 0 24px;
    }}

    /* Header */
    header {{
      background: linear-gradient(180deg, #101726 0%, var(--bg-base) 100%);
      border-bottom: 1px solid var(--border-color);
      padding: 36px 0 28px 0;
      margin-bottom: 32px;
    }}

    .header-content {{
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      flex-wrap: wrap;
      gap: 20px;
    }}

    .brand-title {{
      font-size: 1.75rem;
      font-weight: 700;
      letter-spacing: -0.02em;
      display: flex;
      align-items: center;
      gap: 10px;
    }}

    .brand-title .logo-accent {{
      color: var(--accent-indigo);
    }}

    .brand-desc {{
      color: var(--text-muted);
      font-size: 0.95rem;
      margin-top: 6px;
      max-width: 680px;
    }}

    .meta-badges {{
      display: flex;
      flex-direction: column;
      align-items: flex-end;
      gap: 6px;
    }}

    .meta-tag {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      background: var(--bg-surface);
      border: 1px solid var(--border-color);
      border-radius: 6px;
      padding: 4px 10px;
      font-size: 0.8rem;
      color: var(--text-muted);
    }}

    .meta-tag strong {{
      color: var(--text-main);
    }}

    /* Layout Cards */
    .card {{
      background: var(--bg-surface);
      border: 1px solid var(--border-color);
      border-radius: 12px;
      padding: 24px;
      box-shadow: 0 4px 20px rgba(0, 0, 0, 0.25);
    }}

    .section-title {{
      font-size: 1.25rem;
      font-weight: 600;
      margin-bottom: 18px;
      display: flex;
      align-items: center;
      gap: 8px;
      letter-spacing: -0.01em;
    }}

    .section-title .section-icon {{
      color: var(--accent-blue);
    }}

    /* KPI Grid */
    .kpi-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
      gap: 20px;
      margin-bottom: 36px;
    }}

    .kpi-card {{
      display: flex;
      flex-direction: column;
      background: linear-gradient(145deg, var(--bg-surface) 0%, var(--bg-card) 100%);
      border: 1px solid var(--border-color);
      position: relative;
      overflow: hidden;
    }}

    .kpi-card::before {{
      content: "";
      position: absolute;
      top: 0;
      left: 0;
      right: 0;
      height: 3px;
      background: linear-gradient(90deg, var(--accent-indigo), var(--accent-purple));
    }}

    .kpi-model-badge {{
      font-size: 0.95rem;
      font-weight: 600;
      color: var(--text-muted);
      text-transform: uppercase;
      letter-spacing: 0.05em;
      margin-bottom: 12px;
    }}

    .kpi-headline {{
      display: flex;
      align-items: baseline;
      gap: 12px;
      margin-bottom: 16px;
    }}

    .kpi-number {{
      font-size: 2.75rem;
      font-weight: 800;
      letter-spacing: -0.03em;
      color: #FFFFFF;
      line-height: 1;
    }}

    .kpi-subtext {{
      color: var(--text-muted);
      font-size: 0.85rem;
      font-weight: 500;
    }}

    .kpi-stats {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-bottom: 18px;
    }}

    .stat-pill {{
      font-size: 0.8rem;
      font-weight: 600;
      border-radius: 6px;
      padding: 4px 10px;
      display: flex;
      align-items: center;
      gap: 6px;
    }}

    .stat-pass {{
      background: var(--color-pass-bg);
      color: var(--color-pass);
      border: 1px solid rgba(16, 185, 129, 0.25);
    }}

    .stat-fail {{
      background: var(--color-fail-bg);
      color: var(--color-fail);
      border: 1px solid rgba(244, 63, 94, 0.25);
    }}

    .stat-inc {{
      background: var(--color-warn-bg);
      color: var(--color-warn);
      border: 1px solid rgba(245, 158, 11, 0.25);
    }}

    .stat-err {{
      background: var(--color-err-bg);
      color: var(--color-err);
      border: 1px solid rgba(168, 85, 247, 0.25);
    }}

    .kpi-divider {{
      height: 1px;
      background: var(--border-color);
      margin: 4px 0 16px 0;
    }}

    .kpi-metrics {{
      display: flex;
      flex-direction: column;
      gap: 8px;
      font-size: 0.85rem;
    }}

    .kpi-metric-row {{
      display: flex;
      justify-content: space-between;
      color: var(--text-muted);
    }}

    .kpi-metric-row .value {{
      font-weight: 600;
      color: var(--text-main);
    }}

    /* Badges */
    .badge {{
      display: inline-flex;
      align-items: center;
      font-size: 0.75rem;
      font-weight: 600;
      padding: 3px 8px;
      border-radius: 5px;
      letter-spacing: 0.02em;
    }}

    .badge-pass {{
      background: var(--color-pass-bg);
      color: var(--color-pass);
      border: 1px solid rgba(16, 185, 129, 0.3);
    }}

    .badge-fail {{
      background: var(--color-fail-bg);
      color: var(--color-fail);
      border: 1px solid rgba(244, 63, 94, 0.3);
    }}

    .badge-inc {{
      background: var(--color-warn-bg);
      color: var(--color-warn);
      border: 1px solid rgba(245, 158, 11, 0.3);
    }}

    .badge-err {{
      background: var(--color-err-bg);
      color: var(--color-err);
      border: 1px solid rgba(168, 85, 247, 0.3);
    }}

    .badge-neutral {{
      background: var(--bg-card);
      color: var(--text-muted);
      border: 1px solid var(--border-color);
    }}

    .badge-info {{
      background: rgba(59, 130, 246, 0.12);
      color: #60A5FA;
      border: 1px solid rgba(59, 130, 246, 0.3);
    }}

    .badge-purple {{
      background: rgba(139, 92, 246, 0.12);
      color: #A78BFA;
      border: 1px solid rgba(139, 92, 246, 0.3);
    }}

    /* Behavioral Dimensions Section */
    .dimensions-section {{
      margin-bottom: 36px;
    }}

    .dim-table {{
      display: flex;
      flex-direction: column;
      gap: 12px;
    }}

    .dim-header-row {{
      display: flex;
      padding: 0 16px 8px 16px;
      border-bottom: 1px solid var(--border-color);
      font-size: 0.8rem;
      font-weight: 600;
      color: var(--text-muted);
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }}

    .dim-head-name {{
      flex: 1.2;
    }}

    .dim-head-grid {{
      flex: 2;
      display: grid;
      gap: 24px;
    }}

    .dim-row {{
      background: var(--bg-card);
      border: 1px solid var(--border-color);
      border-radius: 8px;
      padding: 14px 18px;
      display: flex;
      align-items: center;
      gap: 20px;
    }}

    .dim-name-col {{
      flex: 1.2;
      font-size: 0.95rem;
    }}

    .dim-models-grid {{
      flex: 2;
      display: grid;
      gap: 24px;
    }}

    .dim-cell {{
      display: flex;
      flex-direction: column;
      gap: 6px;
    }}

    .dim-header {{
      display: flex;
      justify-content: space-between;
      font-size: 0.8rem;
    }}

    .dim-rate {{
      font-weight: 700;
      color: var(--text-main);
    }}

    .dim-counts {{
      color: var(--text-muted);
    }}

    .progress-bar-bg {{
      height: 8px;
      background: #0f1624;
      border-radius: 4px;
      overflow: hidden;
      border: 1px solid var(--border-color);
    }}

    .progress-bar-fill {{
      height: 100%;
      border-radius: 4px;
      transition: width 0.3s ease;
    }}

    /* Categories Table */
    .categories-section {{
      margin-bottom: 36px;
    }}

    .cat-table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 0.9rem;
    }}

    .cat-table th {{
      text-align: left;
      padding: 10px 14px;
      border-bottom: 1px solid var(--border-color);
      color: var(--text-muted);
      font-size: 0.8rem;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }}

    .cat-table td {{
      padding: 12px 14px;
      border-bottom: 1px solid var(--border-color);
    }}

    .cat-table tr:last-child td {{
      border-bottom: none;
    }}

    .cat-title-cell code {{
      font-size: 0.85rem;
      color: #93C5FD;
    }}

    .cat-cell {{
      display: flex;
      align-items: center;
      gap: 8px;
    }}

    .cat-detail {{
      color: var(--text-muted);
      font-size: 0.8rem;
    }}

    /* Scenarios Section */
    .scenarios-section {{
      margin-bottom: 36px;
    }}

    .scenario-card {{
      margin-bottom: 20px;
      border-left: 3px solid var(--accent-indigo);
    }}

    .scenario-header {{
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      margin-bottom: 10px;
    }}

    .scenario-title-area {{
      display: flex;
      flex-direction: column;
      gap: 6px;
    }}

    .scenario-id {{
      font-size: 1.05rem;
      font-weight: 700;
      color: #FFFFFF;
      font-family: ui-monospace, SFMono-Regular, monospace;
    }}

    .scenario-tags {{
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
    }}

    .scenario-expectations {{
      background: rgba(11, 15, 25, 0.5);
      border: 1px solid var(--border-color);
      border-radius: 6px;
      padding: 10px 14px;
      font-size: 0.85rem;
      margin-bottom: 18px;
    }}

    .expect-label {{
      font-weight: 600;
      color: var(--text-muted);
      margin-right: 6px;
    }}

    .expect-text {{
      color: var(--text-main);
    }}

    .scenario-models-grid {{
      display: grid;
      gap: 16px;
    }}

    .scenario-model-col {{
      background: var(--bg-card);
      border: 1px solid var(--border-color);
      border-radius: 8px;
      padding: 14px;
      display: flex;
      flex-direction: column;
      gap: 10px;
    }}

    .scenario-model-header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding-bottom: 8px;
      border-bottom: 1px solid var(--border-color);
    }}

    .scenario-model-meta {{
      display: flex;
      justify-content: space-between;
      font-size: 0.8rem;
      color: var(--text-muted);
    }}

    .lat-badge {{
      background: rgba(15, 23, 42, 0.8);
      border: 1px solid var(--border-color);
      border-radius: 4px;
      padding: 2px 6px;
      font-family: ui-monospace, SFMono-Regular, monospace;
      color: #94A3B8;
    }}

    .evidence-block {{
      border-radius: 6px;
      padding: 10px 12px;
      font-size: 0.8rem;
      display: flex;
      flex-direction: column;
      gap: 6px;
    }}

    .fail-block {{
      background: var(--color-fail-bg);
      border: 1px solid rgba(244, 63, 94, 0.3);
    }}

    .inc-block {{
      background: var(--color-warn-bg);
      border: 1px solid rgba(245, 158, 11, 0.3);
    }}

    .evidence-title {{
      display: flex;
      align-items: center;
      gap: 6px;
      flex-wrap: wrap;
    }}

    .check-type {{
      color: var(--text-sub);
      font-size: 0.75rem;
    }}

    .evidence-desc {{
      color: var(--text-main);
    }}

    .evidence-snippet {{
      margin-top: 4px;
    }}

    .snippet-label {{
      font-size: 0.75rem;
      color: var(--text-muted);
      margin-bottom: 3px;
    }}

    .snippet-body {{
      background: #0B0F19;
      border: 1px solid var(--border-color);
      border-radius: 4px;
      padding: 8px;
      color: #E2E8F0;
      font-size: 0.75rem;
      line-height: 1.4;
      max-height: 120px;
      overflow-y: auto;
    }}

    .response-drawer {{
      margin-top: 6px;
      font-size: 0.8rem;
    }}

    .response-drawer summary {{
      cursor: pointer;
      color: #93C5FD;
      font-weight: 500;
      user-select: none;
      padding: 4px 0;
    }}

    .response-drawer summary:hover {{
      color: #BFDBFE;
    }}

    .response-text {{
      margin-top: 8px;
      background: #0B0F19;
      border: 1px solid var(--border-color);
      border-radius: 6px;
      padding: 12px;
      color: #E2E8F0;
      font-size: 0.75rem;
      white-space: pre-wrap;
      max-height: 240px;
      overflow-y: auto;
      line-height: 1.45;
    }}

    /* Disclaimer Section */
    .disclaimer-card {{
      background: rgba(17, 24, 39, 0.7);
      border: 1px solid var(--border-color);
      border-left: 4px solid var(--accent-blue);
      border-radius: 8px;
      padding: 18px 22px;
      margin-top: 36px;
    }}

    .disclaimer-title {{
      font-size: 0.95rem;
      font-weight: 700;
      color: #93C5FD;
      margin-bottom: 6px;
    }}

    .disclaimer-body {{
      font-size: 0.85rem;
      color: var(--text-muted);
      line-height: 1.5;
    }}

    /* Footer */
    footer {{
      margin-top: 48px;
      text-align: center;
      font-size: 0.8rem;
      color: var(--text-sub);
      border-top: 1px solid var(--border-color);
      padding-top: 24px;
    }}

    @media (max-width: 768px) {{
      .header-content {{
        flex-direction: column;
        align-items: flex-start;
      }}
      .meta-badges {{
        align-items: flex-start;
      }}
      .dim-row {{
        flex-direction: column;
        align-items: flex-start;
      }}
      .dim-models-grid {{
        width: 100%;
        grid-template-columns: 1fr !important;
      }}
      .scenario-models-grid {{
        grid-template-columns: 1fr !important;
      }}
      .dim-header-row {{
        display: none;
      }}
    }}
  </style>
</head>
<body>

  <header>
    <div class="container header-content">
      <div>
        <h1 class="brand-title">
          <span>OpenAffect</span><span class="logo-accent">Lab</span>
          <span class="badge badge-neutral" style="font-size: 0.75rem;">v{version}</span>
        </h1>
        <p class="brand-desc">
          Reproducible, offline evaluation dashboard assessing model boundary compliance,
          emotional attribution, and conversational restraint.
        </p>
      </div>
      <div class="meta-badges">
        <div class="meta-tag"><span>Type:</span> <strong>{report_type}</strong></div>
        <div class="meta-tag"><span>Dataset:</span> <code>{scenario_file}</code></div>
        <div class="meta-tag"><span>Evaluated:</span> <strong>{created_at}</strong></div>
      </div>
    </div>
  </header>

  <main class="container">

    <!-- KPI Cards -->
    <section class="kpi-grid">
      {"".join(kpi_cards_html)}
    </section>

    <!-- Behavioral Dimensions -->
    <section class="card dimensions-section">
      <h2 class="section-title">
        <span class="section-icon">◆</span> Behavioral Dimensions Breakdown
      </h2>
      <div class="dim-table">
        <div class="dim-header-row">
          <div class="dim-head-name">Behavior Dimension</div>
          <div class="dim-head-grid" style="grid-template-columns: repeat({len(model_keys)}, 1fr);">
            {dim_col_headers}
          </div>
        </div>
        {"".join(behavior_rows_html)}
      </div>
    </section>

    <!-- Scenario Categories -->
    <section class="card categories-section">
      <h2 class="section-title">
        <span class="section-icon">❖</span> Scenario Categories Breakdown
      </h2>
      <table class="cat-table">
        <thead>
          <tr>
            <th>Scenario Category</th>
            {category_headers}
          </tr>
        </thead>
        <tbody>
          {"".join(category_rows_html)}
        </tbody>
      </table>
    </section>

    <!-- Scenario Level Results -->
    <section class="scenarios-section">
      <h2 class="section-title">
        <span class="section-icon">◈</span> Scenario-Level Evaluations ({len(scenarios)} Scenarios)
      </h2>
      {"".join(scenarios_cards_html)}
    </section>

    <!-- Methodological Disclaimer -->
    <section class="disclaimer-card">
      <div class="disclaimer-title">Methodological Disclaimer & Limitations</div>
      <div class="disclaimer-body">
        <p style="margin-bottom: 8px;">{disclaimer_text}</p>
        <p>
          <strong>Dataset Scope:</strong> This evaluation was performed on 10 targeted counterfactual and multi-turn scenarios.
          Heuristic regex and word-count checks identify explicit patterns and length bounds but do not measure general semantic understanding or internal reasoning.
          Checks marked as <em>Inconclusive</em> require manual human review.
        </p>
      </div>
    </section>

  </main>

  <footer>
    <div class="container">
      OpenAffect Lab &bull; Local-first deterministic evaluation framework &bull; Zero external dependencies
    </div>
  </footer>

</body>
</html>
"""
    clean_lines = [line.rstrip() for line in full_html.splitlines()]
    return "\n".join(clean_lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a standalone HTML evaluation dashboard for OpenAffect Lab."
    )
    parser.add_argument(
        "--input",
        "-i",
        type=Path,
        default=Path("examples/comparison_report.json"),
        help="Path to evaluation or comparison JSON report (default: examples/comparison_report.json)",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=Path("dashboard.html"),
        help="Path for generated HTML file (default: dashboard.html)",
    )

    args = parser.parse_args()

    # Load report
    report_data = load_report(args.input)

    # Generate HTML
    dashboard_html = generate_html(report_data)

    # Write output
    try:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(dashboard_html)
        print(f"Successfully generated dashboard: {args.output.resolve()}")
    except Exception as exc:
        print(f"Error: Failed to write output file '{args.output}': {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
