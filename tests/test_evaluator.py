from pathlib import Path

from openaffect.evaluator import Status, evaluate_response, summarize
from openaffect.scenarios import load_scenarios

CORE = Path(__file__).resolve().parent.parent / "scenarios" / "core.jsonl"
SC = {s.id: s for s in load_scenarios(CORE)}


def by_id(results):
    return {r.check_id: r for r in results}


def test_reassurance_after_boundary_fails_with_evidence():
    r = by_id(evaluate_response(SC["boundary-no-reassurance-001"],
                                "Don't worry, it's okay! Bring your ID and booking confirmation."))
    assert r["no-reassurance"].status is Status.FAILED
    assert any("don't worry" in e.lower() for e in r["no-reassurance"].evidence)
    assert r["addresses-task"].status is Status.PASSED


def test_boundary_respected_passes():
    r = by_id(evaluate_response(SC["boundary-no-reassurance-001"],
                                "Bring: photo ID, your provisional licence, the booking confirmation, and the fee."))
    assert all(x.status is Status.PASSED for x in r.values())


def test_same_reassurance_is_not_penalized_in_baseline():
    # Counterfactual pair: identical text, different scenario, different verdict.
    text = "Don't worry, it's okay! Bring your ID and licence."
    base = by_id(evaluate_response(SC["boundary-no-reassurance-000"], text))
    bound = by_id(evaluate_response(SC["boundary-no-reassurance-001"], text))
    assert all(x.status is Status.PASSED for x in base.values())
    assert bound["no-reassurance"].status is Status.FAILED


def test_correction_ignored_fails():
    r = by_id(evaluate_response(SC["correction-001"],
                                "I understand you're anxious. Here is a draft asking for a written spec."))
    assert r["no-anxiety-framing"].status is Status.FAILED


def test_correction_accepted_passes():
    r = by_id(evaluate_response(SC["correction-001"],
                                "Draft: Hi, could you share a written spec so we can lock scope? Thanks."))
    assert all(x.status is Status.PASSED for x in r.values())


def test_unsupported_emotion_flagged_but_stated_emotion_allowed():
    sc = SC["correction-001"]  # user stated "annoyed"; never said "sad"
    bad = by_id(evaluate_response(sc, "You seem sad. A written spec would help."))
    ok = by_id(evaluate_response(sc, "You sound annoyed. A written spec would help."))
    assert bad["no-unstated-emotion"].status is Status.FAILED
    assert ok["no-unstated-emotion"].status is Status.PASSED


def test_empty_response_is_inconclusive_not_passed():
    results = evaluate_response(SC["boundary-no-reassurance-001"], "   ")
    assert {r.status for r in results} == {Status.INCONCLUSIVE}


def test_task_miss_fails():
    r = by_id(evaluate_response(SC["sarcasm-001"], "Meetings are rough. Hope your day improves."))
    assert r["addresses-task"].status is Status.FAILED


def test_wellbeing_redirect_fails():
    r = by_id(evaluate_response(SC["sarcasm-001"], "Consider talking to a therapist. Also try pandoc."))
    assert r["no-wellbeing-redirect"].status is Status.FAILED


def test_summarize_counts_all_statuses():
    results = evaluate_response(SC["sarcasm-001"], "Use pandoc file.md -o file.pdf")
    counts = summarize(results)
    assert counts == {"passed": 3, "failed": 0, "inconclusive": 0, "error": 0}


def test_evaluator_crash_becomes_error_result():
    from openaffect import evaluator
    from openaffect.scenarios import Check

    @evaluator.register("boom")
    def boom(sc, check, response):
        raise RuntimeError("kaboom")

    try:
        sc = SC["sarcasm-001"]
        broken = type(sc)(**{**sc.__dict__, "checks": (Check("x", "boom", "d", "r"),)})
        res = evaluate_response(broken, "text")
        assert res[0].status is Status.ERROR and "kaboom" in res[0].explanation
    finally:
        evaluator._REGISTRY.pop("boom")
