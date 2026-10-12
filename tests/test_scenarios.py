import json
from pathlib import Path

import pytest

from openaffect.scenarios import ScenarioError, load_scenarios

CORE = Path(__file__).resolve().parent.parent / "scenarios" / "core.jsonl"


def _valid(**over):
    rec = {
        "id": "t-1", "category": "c", "description": "d",
        "messages": [{"role": "user", "content": "hi"}],
        "behavior_tested": "b", "expected_behavior": "e",
        "checks": [{"id": "k", "type": "manual_review", "description": "d", "rationale": "r"}],
    }
    rec.update(over)
    return rec


def _write(tmp_path, *recs):
    p = tmp_path / "s.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in recs), encoding="utf-8")
    return p


def test_core_dataset_loads_and_ids_are_unique():
    scenarios = load_scenarios(CORE)
    assert len(scenarios) >= 4
    assert len({s.id for s in scenarios}) == len(scenarios)


def test_core_pairs_have_both_variants():
    scenarios = load_scenarios(CORE)
    pairs = {}
    for s in scenarios:
        if s.pair_id:
            pairs.setdefault(s.pair_id, set()).add(s.variant)
    assert pairs, "expected at least one counterfactual pair"
    for pid, variants in pairs.items():
        assert len(variants) >= 2, f"pair {pid} has only {variants}"


def test_valid_record_loads(tmp_path):
    assert load_scenarios(_write(tmp_path, _valid()))[0].id == "t-1"


def test_missing_field_reports_line(tmp_path):
    rec = _valid()
    del rec["expected_behavior"]
    with pytest.raises(ScenarioError, match=r"s.jsonl:1.*expected_behavior"):
        load_scenarios(_write(tmp_path, rec))


def test_last_message_must_be_user(tmp_path):
    rec = _valid(messages=[{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}])
    with pytest.raises(ScenarioError, match="last message"):
        load_scenarios(_write(tmp_path, rec))


def test_duplicate_ids_rejected(tmp_path):
    with pytest.raises(ScenarioError, match="duplicate scenario id"):
        load_scenarios(_write(tmp_path, _valid(), _valid()))


def test_unknown_check_type_rejected(tmp_path):
    rec = _valid(checks=[{"id": "k", "type": "nope", "description": "d", "rationale": "r"}])
    with pytest.raises(ScenarioError, match="unknown check type"):
        load_scenarios(_write(tmp_path, rec))


def test_invalid_regex_rejected(tmp_path):
    rec = _valid(checks=[{"id": "k", "type": "forbidden_patterns", "description": "d",
                          "rationale": "r", "params": {"patterns": ["(unclosed"]}}])
    with pytest.raises(ScenarioError, match="invalid regex"):
        load_scenarios(_write(tmp_path, rec))


def test_bad_json_reports_line(tmp_path):
    p = tmp_path / "bad.jsonl"
    p.write_text("{not json}\n", encoding="utf-8")
    with pytest.raises(ScenarioError, match="bad.jsonl:1: invalid JSON"):
        load_scenarios(p)
