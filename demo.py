"""Offline demonstration of OpenAffect Lab evaluation and counterfactual pairs."""
from pathlib import Path
import sys

# Locate repository root relative to this script
REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from openaffect.scenarios import load_scenarios
from openaffect.evaluator import evaluate_response
from openaffect.reporter import load_report, render_text


def run_demo():
    print("=" * 60)
    print("OpenAffect Lab - Offline Counterfactual Evaluation Demo")
    print("=" * 60 + "\n")

    scenarios_path = REPO_ROOT / "scenarios" / "core.jsonl"
    if not scenarios_path.exists():
        print(f"Error: Scenario file not found at {scenarios_path}")
        return

    scenarios = load_scenarios(scenarios_path)
    pair = [s for s in scenarios if s.pair_id == "driving-test"]
    baseline = next((s for s in pair if s.variant == "baseline"), None)
    boundary = next((s for s in pair if s.variant == "with_boundary"), None)

    if not baseline or not boundary:
        print("Error: Could not locate complete 'driving-test' baseline and boundary variants.")
        return

    # Illustrative synthetic response crafted to demonstrate counterfactual divergence
    illustrative_reply = (
        "I'm so sorry to hear that you failed, but don't worry, it's okay! You'll get it next time. "
        "When you rebook, bring your driver's license or permit, identification, and proof of address."
    )

    print("[ILLUSTRATIVE SYNTHETIC RESPONSE - NOT A REAL MODEL OUTPUT]")
    print(f"\"{illustrative_reply}\"\n")

    print(f"1. Evaluating Baseline ({baseline.id}):")
    print(f"   Context: User asked for documents; reassurance is permitted.")
    res_base = evaluate_response(baseline, illustrative_reply)
    for r in res_base:
        print(f"   - {r.check_id:<24} [{r.status.value.upper():<7}] {r.explanation}")

    print(f"\n2. Evaluating Boundary Variant ({boundary.id}):")
    print(f"   Context: Exact same situation, but user explicitly said: 'Please don't comfort me'.")
    res_bound = evaluate_response(boundary, illustrative_reply)
    for r in res_bound:
        print(f"   - {r.check_id:<24} [{r.status.value.upper():<7}] {r.explanation}")
        for ev in r.evidence:
            print(f"       evidence: {ev}")

    comp_report_path = REPO_ROOT / "examples" / "comparison_report.json"
    print("\n" + "=" * 60)
    print("Saved Empirical Report Inspection:")
    print("=" * 60)
    if comp_report_path.exists():
        rep = load_report(comp_report_path)
        print("\n" + render_text(rep))
    else:
        print(f"\nSample comparison report not found at {comp_report_path}.")
        print("To generate real model reports, run:")
        print("  python -m openaffect compare --models phi3:mini llama3.2:3b")


if __name__ == "__main__":
    run_demo()
