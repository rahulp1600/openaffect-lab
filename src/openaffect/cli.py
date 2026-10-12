"""Command-line interface: `python -m openaffect run|report`."""
from __future__ import annotations

import argparse
import sys
from datetime import datetime

from .model_adapter import DEFAULT_HOST, OllamaAdapter
from .reporter import load_report, render_text, save_report
from .runner import run_scenarios
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
        if args.command == "report":
            print(render_text(load_report(args.input), show_passes=args.all))
            return 0
    except (ScenarioError, ValueError, FileNotFoundError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 1
