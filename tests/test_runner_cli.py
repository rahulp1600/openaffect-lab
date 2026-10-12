import json

from openaffect.cli import main
from openaffect.model_adapter import Generation, OllamaAdapter
from openaffect.reporter import load_report, render_text
from openaffect.runner import run_scenarios
from openaffect.scenarios import load_scenarios

from pathlib import Path

CORE = Path(__file__).resolve().parent.parent / "scenarios" / "core.jsonl"


class FakeAdapter:
    def __init__(self, text="Use pandoc. Bring your ID and licence. A written spec please.", error=None):
        self.text, self.error = text, error

    def describe(self):
        return {"provider": "fake", "name": "fake-1", "options": {}}

    def generate(self, messages):
        return Generation(None if self.error else self.text, 0.01, self.error)


def test_run_produces_complete_report():
    rep = run_scenarios(load_scenarios(CORE), FakeAdapter(), "core.jsonl")
    assert rep["model"]["name"] == "fake-1"
    assert len(rep["scenarios"]) == rep["totals"]["scenarios"]
    first = rep["scenarios"][0]
    for key in ("scenario_id", "response", "expected_behavior", "timestamp", "results", "execution_error"):
        assert key in first
    assert all(r["evidence"] is not None and r["explanation"] for e in rep["scenarios"] for r in e["results"])


def test_generation_error_is_recorded_not_raised():
    rep = run_scenarios(load_scenarios(CORE), FakeAdapter(error="boom"))
    assert rep["totals"]["error"] > 0 and rep["totals"]["passed"] == 0
    assert rep["scenarios"][0]["execution_error"] == "boom"
    assert rep["totals"]["pass_rate"] is None


def test_report_roundtrip_and_render(tmp_path):
    out = tmp_path / "r.json"
    code = main(["run", "--model", "x", "--output", str(out), "--scenarios", str(CORE)],
                adapter_factory=lambda model, **kw: FakeAdapter("Don't worry, it's okay!"))
    assert code == 0
    rep = load_report(out)
    text = render_text(rep)
    assert "FAILED" in text and "evidence" in text and "not a measure of emotional intelligence" in text
    assert main(["report", "--input", str(out)]) == 0


def test_all_errors_gives_nonzero_exit(tmp_path):
    code = main(["run", "--model", "x", "--output", str(tmp_path / "r.json"), "--scenarios", str(CORE)],
                adapter_factory=lambda model, **kw: FakeAdapter(error="down"))
    assert code == 2


def test_bad_report_path_gives_clean_error(tmp_path):
    assert main(["report", "--input", str(tmp_path / "missing.json")]) == 1


def test_ollama_adapter_unreachable_host_returns_error():
    g = OllamaAdapter("m", host="http://127.0.0.1:9", timeout=2).generate([{"role": "user", "content": "hi"}])
    assert g.text is None and "Cannot reach Ollama" in g.error


def test_behavioral_classification_and_decided_rates():
    from openaffect.runner import classify_check_behavior, aggregate_by_behavior
    # Test individual classification
    assert classify_check_behavior({"category": "explicit_boundary"}, {"check_type": "no_unsupported_emotion_claim"}) == "unsupported_emotion_attribution"
    assert classify_check_behavior({"category": "explicit_boundary", "variant": "with_boundary"}, {"check_type": "forbidden_patterns"}) == "boundary_respect"
    assert classify_check_behavior({"category": "user_correction"}, {"check_type": "forbidden_patterns"}) == "context_adaptation"
    assert classify_check_behavior({"category": "direct_technical"}, {"check_type": "required_patterns"}) == "task_responsiveness"
    assert classify_check_behavior({"category": "direct_technical"}, {"check_type": "max_words"}) == "task_responsiveness"
    # Unclassified check returns None (safeguard 3)
    assert classify_check_behavior({"category": "conflicting_signals"}, {"check_type": "manual_review"}) is None

    # Test zero decided checks returns None pass_rate (safeguard 4)
    entries = [{
        "category": "conflicting_signals",
        "results": [{"check_type": "no_unsupported_emotion_claim", "status": "inconclusive"}]
    }]
    behav = aggregate_by_behavior(entries)
    assert behav["unsupported_emotion_attribution"]["pass_rate"] is None
    assert behav["unsupported_emotion_attribution"]["inconclusive"] == 1


def test_compare_reports_logic():
    from openaffect.runner import compare_reports
    scs = load_scenarios(CORE)
    rep_a = run_scenarios(scs, FakeAdapter("Use pandoc. Bring your ID and licence. A written spec please."), "core.jsonl")
    rep_b = run_scenarios(scs, FakeAdapter("Don't worry, it's okay! We will figure it out."), "core.jsonl")
    comp = compare_reports(rep_a, rep_b)

    assert comp["type"] == "comparison"
    assert len(comp["models"]) == 2
    # Ensure no single emotional-intelligence score exists
    assert "emotional_intelligence" not in comp
    assert "score" not in comp
    assert "disclaimer" in comp and "not a measure of emotional intelligence" in comp["disclaimer"]

    # Verify behavioral breakdown presence
    for dim in ("task_responsiveness", "unsupported_emotion_attribution", "boundary_respect", "context_adaptation"):
        assert dim in comp["by_behavior"]


def test_compare_cli_command(tmp_path):
    out = tmp_path / "comp.json"
    code = main(
        ["compare", "--models", "fake-a", "fake-b", "--output", str(out), "--scenarios", str(CORE)],
        adapter_factory=lambda model, **kw: FakeAdapter("Use pandoc. ID and written spec.") if "a" in model else FakeAdapter("Don't worry!"),
    )
    assert code == 0
    assert out.exists()

    rep = load_report(out)
    assert rep["type"] == "comparison"
    text = render_text(rep)
    assert "OpenAffect comparison:" in text
    assert "OVERALL COMPARISON:" in text
    assert "BEHAVIORAL DIMENSIONS" in text
    assert "SCENARIO CATEGORIES" in text
    # Verify report CLI command handles comparison report cleanly
    assert main(["report", "--input", str(out)]) == 0


def test_compare_cli_handles_errors(tmp_path):
    out = tmp_path / "comp_err.json"
    code = main(
        ["compare", "--models", "fake-a", "fake-b", "--output", str(out), "--scenarios", str(CORE)],
        adapter_factory=lambda model, **kw: FakeAdapter(error="connection refused"),
    )
    # Both failed completely -> exit code 2
    assert code == 2
    rep = load_report(out)
    assert rep["type"] == "comparison"
