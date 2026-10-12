"""Command-line interface: `python -m openaffect run|report|compare`."""
from __future__ import annotations

import argparse
import sys
from datetime import datetime

from .model_adapter import DEFAULT_HOST, OllamaAdapter
from .reporter import load_report, render_comparison_text, render_text, save_report
from .runner import compare_reports, run_scenarios
from .scenarios import ScenarioError, load_scenarios


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="openaffect", description="Evaluate AI behavior in emotionally sensitive conversations.")
    sub = p.add_subparsers(dest="command", required=True)

    r = sub.add_parser("run", help="Run scenarios against one Ollama model and write a JSON report.")
    r.add_argument("--model", required=True, help="Ollama model name, e.g. phi4-mini")
    r.add_argument("--scenarios", default="scenarios/core.jsonl")
    r.add_argument("--output", help="Report path (default: results/<model>-<timestamp>.json)")
    r.add_argument("--host", default=DEFAULT_HOST)
    r.add_argument("--temperature", type=float, default=0.0)
    r.add_argument("--seed", type=int, default=0)

    c = sub.add_parser("compare", help="Run scenarios against two Ollama models and write a comparison report.")
    c.add_argument("--models", nargs=2, required=True, metavar=("MODEL_A", "MODEL_B"), help="Two Ollama models to compare")
    c.add_argument("--scenarios", default="scenarios/core.jsonl")
    c.add_argument("--output", help="Report path (default: results/compare-<m1>-vs-<m2>-<timestamp>.json)")
    c.add_argument("--host", default=DEFAULT_HOST)
    c.add_argument("--temperature", type=float, default=0.0)
    c.add_argument("--seed", type=int, default=0)

    rep = sub.add_parser("report", help="Print a saved report.")
    rep.add_argument("--input", required=True)
    rep.add_argument("--all", action="store_true", help="Also show passing checks.")
    return p


def main(argv: list[str] | None = None, adapter_factory=OllamaAdapter) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "run":
            scenarios = load_scenarios(args.scenarios)
            adapter = adapter_factory(args.model, host=args.host, temperature=args.temperature, seed=args.seed)
            report = run_scenarios(
                scenarios, adapter, args.scenarios,
                progress=lambda i, n, sid: print(f"[{i}/{n}] {sid}", file=sys.stderr))
            out = args.output or f"results/{args.model.replace(':', '_').replace('/', '_')}-{datetime.now():%Y%m%d-%H%M%S}.json"
            from pathlib import Path
            Path(out).parent.mkdir(parents=True, exist_ok=True)
            save_report(report, out)
            print(render_text(report))
            print(f"\nReport saved to {out}")
            # exit 0 even with failed checks (failures are findings); nonzero only if nothing could run
            return 2 if report["totals"]["error"] == report["totals"]["passed"] + report["totals"]["failed"] + report["totals"]["inconclusive"] + report["totals"]["error"] else 0
        if args.command == "compare":
            scenarios = load_scenarios(args.scenarios)
            m_a, m_b = args.models
            adapter_a = adapter_factory(m_a, host=args.host, temperature=args.temperature, seed=args.seed)
            adapter_b = adapter_factory(m_b, host=args.host, temperature=args.temperature, seed=args.seed)
            report_a = run_scenarios(
                scenarios, adapter_a, args.scenarios,
                progress=lambda i, n, sid: print(f"[{m_a} {i}/{n}] {sid}", file=sys.stderr))
            report_b = run_scenarios(
                scenarios, adapter_b, args.scenarios,
                progress=lambda i, n, sid: print(f"[{m_b} {i}/{n}] {sid}", file=sys.stderr))
            comp = compare_reports(report_a, report_b)
            safe_a = m_a.replace(":", "_").replace("/", "_")
            safe_b = m_b.replace(":", "_").replace("/", "_")
            out = args.output or f"results/compare-{safe_a}-vs-{safe_b}-{datetime.now():%Y%m%d-%H%M%S}.json"
            from pathlib import Path
            Path(out).parent.mkdir(parents=True, exist_ok=True)
            save_report(comp, out)
            print(render_comparison_text(comp))
            print(f"\nComparison report saved to {out}")
            tot_a = report_a["totals"]
            tot_b = report_b["totals"]
            err_a = tot_a["error"] == tot_a["passed"] + tot_a["failed"] + tot_a["inconclusive"] + tot_a["error"]
            err_b = tot_b["error"] == tot_b["passed"] + tot_b["failed"] + tot_b["inconclusive"] + tot_b["error"]
            return 2 if (err_a and err_b) else 0
        if args.command == "report":
            print(render_text(load_report(args.input), show_passes=args.all))
            return 0
    except (ScenarioError, ValueError, FileNotFoundError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 1
