"""Explanation-layer tests — all offline via a fake client (no network/API key).

These guard the Phase 3 contract: the prompt is grounded in the rule + fields,
the model + prompt version are recorded, and the grounding check catches an
explanation that invents a reason not present in the inputs.
"""
import json

import pytest

from app import explain
from app.explain import build_messages, explain_flag, is_grounded, referenced_values


DUP_FLAG = {
    "id": 1,
    "rule_id": "DUP-01",
    "triggering_fields": json.dumps(
        {
            "member_id": "mbr_2882",
            "provider_id": "prv_167",
            "cpt_code": "99213",
            "date_of_service": "2026-03-14",
            "duplicate_of_line_id": "clm_0031-1",
            "allowed_amount": 75.0,
        }
    ),
}


class _FakeBlock:
    type = "text"

    def __init__(self, text):
        self.text = text


class _FakeResp:
    def __init__(self, text, model="claude-opus-4-8"):
        self.content = [_FakeBlock(text)]
        self.model = model


class _FakeClient:
    """Records the call kwargs and returns a canned, grounded explanation."""

    def __init__(self, text):
        self._text = text
        self.last_kwargs = None
        self.messages = self

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        return _FakeResp(self._text)


def test_build_messages_grounds_in_rule_and_fields():
    system, user = build_messages(DUP_FLAG)
    # The defining guardrails are present in the system prompt.
    assert "explainer, not a decision-maker" in system
    assert "Do NOT introduce any reason" in system
    # The rule description and the actual field values are in the user message.
    assert "DUP-01" in user
    assert "99213" in user and "clm_0031-1" in user and "2026-03-14" in user


def test_explain_flag_records_model_and_prompt_version_and_omits_sampling():
    fake = _FakeClient(
        "This line repeats CPT 99213 for member mbr_2882 on 2026-03-14, already "
        "submitted on claim clm_0031-1, so rule DUP-01 flagged it as a duplicate."
    )
    result = explain_flag(DUP_FLAG, client=fake)

    assert result["explanation_model"] == "claude-opus-4-8"
    assert result["explanation_prompt_version"] == explain.PROMPT_VERSION
    # Opus 4.x would 400 on these — they must never be sent.
    assert "temperature" not in fake.last_kwargs
    assert "top_p" not in fake.last_kwargs
    assert "thinking" not in fake.last_kwargs
    assert fake.last_kwargs["model"] == "claude-opus-4-8"


def test_grounded_explanation_passes_the_check():
    text = (
        "Rule DUP-01 flagged this line because CPT 99213 was billed for member "
        "mbr_2882 on 2026-03-14, the same service already submitted on clm_0031-1."
    )
    triggering = json.loads(DUP_FLAG["triggering_fields"])
    assert is_grounded(text, "DUP-01", triggering)
    cited = referenced_values(text, triggering)
    assert "99213" in cited and "clm_0031-1" in cited


def test_invented_reason_without_rule_or_fields_fails_the_check():
    # Mentions neither the rule/issue nor any triggering value, and invents a reason.
    text = "This claim looks suspicious because the provider has a bad reputation."
    triggering = json.loads(DUP_FLAG["triggering_fields"])
    assert not is_grounded(text, "DUP-01", triggering)


def test_explain_all_raises_clearly_without_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    # _client() should refuse rather than make a doomed call.
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        explain.explain_all()
