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
