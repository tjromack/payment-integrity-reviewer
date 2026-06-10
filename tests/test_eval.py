"""Eval-harness tests: detection metrics (pure) and faithfulness (fake judge)."""
import json

from app import eval as evalmod
from app.eval import detector_metrics, faithfulness_metrics, prf


def test_prf_basic():
    assert prf(8, 2, 2) == (0.8, 0.8, 0.8)
    assert prf(0, 0, 5) == (0.0, 0.0, 0.0)


def _claim(line_id, label, near=0):
    return {"line_id": line_id, "label": label, "is_near_miss": near}


def test_detector_metrics_perfect():
    claims = [_claim("a", "duplicate"), _claim("b", "clean"), _claim("c", "oon_mismatch")]
    flags = [
        {"claim_line_id": "a", "rule_id": "DUP-01"},
        {"claim_line_id": "c", "rule_id": "OON-01"},
    ]
    m = detector_metrics(claims, flags)
    assert m["overall"] == {"precision": 1.0, "recall": 1.0, "f1": 1.0}
    assert m["per_issue"]["duplicate"]["f1"] == 1.0
    assert m["false_positives"] == [] and m["false_negatives"] == []


def test_detector_metrics_counts_fp_and_fn():
    claims = [
        _claim("a", "duplicate"),        # missed -> FN
        _claim("b", "clean", near=1),    # flagged -> FP (a near-miss)
        _claim("c", "oon_mismatch"),     # caught
    ]
    flags = [
        {"claim_line_id": "b", "rule_id": "DUP-01"},  # wrong: b is clean
        {"claim_line_id": "c", "rule_id": "OON-01"},
    ]
    m = detector_metrics(claims, flags)
    assert m["false_positives"] == ["b"]
    assert m["false_negatives"] == ["a"]
    assert m["near_miss_flagged"] == 1 and m["near_miss_total"] == 1
    # duplicate: tp 0, fp 1 (b), fn 1 (a) -> precision 0, recall 0
    assert m["per_issue"]["duplicate"] == {"precision": 0.0, "recall": 0.0, "f1": 0.0}


def test_faithfulness_no_explanations():
    flags = [{"claim_line_id": "a", "rule_id": "DUP-01", "triggering_fields": "{}", "explanation": None}]
    assert faithfulness_metrics(flags)["status"] == "no_explanations"


class _JudgeBlock:
    type = "text"

    def __init__(self, text):
        self.text = text


class _JudgeResp:
    def __init__(self, payload):
        self.content = [_JudgeBlock(json.dumps(payload))]
        self.model = "claude-opus-4-8"


class _FakeJudge:
    """Returns faithful=1 unless the explanation contains the word 'reputation'."""

    def __init__(self):
        self.messages = self

    def create(self, **kwargs):
        user = kwargs["messages"][0]["content"]
        bad = "reputation" in user
        return _JudgeResp({"faithful": 0 if bad else 1, "issues": ["invented reason"] if bad else []})


def test_faithfulness_with_judge_flags_invented_reason():
    trig = json.dumps({"cpt_code": "99213", "duplicate_of_line_id": "x-1"})
    flags = [
        {
            "claim_line_id": "good",
            "rule_id": "DUP-01",
            "triggering_fields": trig,
            "explanation": "Rule DUP-01: CPT 99213 duplicates earlier line x-1.",
        },
        {
            "claim_line_id": "bad",
            "rule_id": "DUP-01",
            "triggering_fields": trig,
            # grounded (names duplicate + cites 99213) but invents a reason -> judge fails it
            "explanation": "This duplicate of 99213 is suspicious due to provider reputation.",
        },
    ]
    m = faithfulness_metrics(flags, client=_FakeJudge())
    assert m["count"] == 2 and m["faithful"] == 1
    assert m["judged_by_llm"] and m["rubric_version"] == evalmod.RUBRIC_VERSION
    assert m["unfaithful"][0]["line_id"] == "bad"
