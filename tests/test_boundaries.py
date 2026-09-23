"""Boundary + malformed-input tests — the failure modes the rules are actually about.

test_detect.py covers a true positive and a near-miss per rule. This file pins the *edges*: every distinct-service
modifier suppresses a duplicate; the exact date-grouping boundary (which is where date-drift duplicates escape — a
known recall gap, see the holdout); partial-modifier unbundling; and degenerate/malformed inputs that must not crash.
"""
import json

import pytest

from app.detect import detect_flags, rule_duplicate, rule_unbundling, rule_oon_mismatch
from app import reference as ref


def _line(**over):
    base = dict(
        claim_id="clm_x", line_id="clm_x-1", member_id="mbr_1",
        provider_id="prv_1", provider_npi="1000000001",
        provider_network_status="in", paid_as_network="in", auth_or_emergency=0,
        date_of_service="2026-02-01", submitted_date="2026-02-03",
        place_of_service="11", cpt_code="99213", modifiers="[]", units=1,
        billed_amount=120.0, allowed_amount=75.0, diagnosis_codes='["I10"]',
        label="clean", is_near_miss=0, created_at="2026-02-03",
    )
    base.update(over)
    return base


def _dup_pair(mod=None):
    a = _line(claim_id="c1", line_id="c1-1", submitted_date="2026-02-03")
    b = _line(claim_id="c2", line_id="c2-1", submitted_date="2026-02-07",
              modifiers=json.dumps([mod]) if mod else "[]")
    return [a, b]


# --- malformed / degenerate input must not crash ----------------------------
def test_rules_handle_empty_input():
    assert detect_flags([]) == []


def test_duplicate_ignores_a_lone_line():
    assert rule_duplicate([_line()]) == []  # a group of one is never a duplicate


def test_unbundling_handles_unknown_cpt_codes():
    lines = [_line(line_id="c1-1", cpt_code="00000"), _line(line_id="c1-2", cpt_code="99999")]
    assert rule_unbundling(lines) == []  # no panel matches; no crash


def test_duplicate_flags_every_later_line_in_a_three_way_repeat():
    lines = [
        _line(claim_id="c1", line_id="c1-1", submitted_date="2026-02-03"),
        _line(claim_id="c2", line_id="c2-1", submitted_date="2026-02-05"),
        _line(claim_id="c3", line_id="c3-1", submitted_date="2026-02-07"),
    ]
    flagged = sorted(f["claim_line_id"] for f in rule_duplicate(lines))
    assert flagged == ["c2-1", "c3-1"]  # earliest is the original; both later repeats flagged


# --- near-miss boundary: every distinct-service modifier suppresses a dup ----
@pytest.mark.parametrize("mod", sorted(ref.DISTINCT_SERVICE_MODIFIERS))
def test_each_distinct_modifier_suppresses_a_duplicate(mod):
    assert rule_duplicate(_dup_pair(mod)) == []


def test_a_non_distinct_modifier_does_not_suppress_a_duplicate():
    # modifier 50 (bilateral) is NOT in the distinct-service set -> the rule still fires.
    # This is the precision leak the holdout documents; the test pins the current behavior.
    flags = rule_duplicate(_dup_pair("50"))
    assert [f["claim_line_id"] for f in flags] == ["c2-1"]


# --- date-grouping boundary: where date-drift duplicates escape --------------
def test_same_service_on_adjacent_dates_is_not_grouped():
    a = _line(claim_id="c1", line_id="c1-1", date_of_service="2026-02-01", submitted_date="2026-02-03")
    b = _line(claim_id="c2", line_id="c2-1", date_of_service="2026-02-02", submitted_date="2026-02-05")
    # KNOWN GAP (documented in the holdout): DUP-01 keys on exact date_of_service, so a next-day
    # duplicate is invisible. Locked here so a future date-window fix is a deliberate, tested change.
    assert rule_duplicate([a, b]) == []


# --- confidence boundary ----------------------------------------------------
def test_duplicate_confidence_reflects_amount_match():
    identical = rule_duplicate(_dup_pair())
    assert identical[0]["confidence"] == 0.95
    a = _line(claim_id="c1", line_id="c1-1", submitted_date="2026-02-03", allowed_amount=75.0)
    b = _line(claim_id="c2", line_id="c2-1", submitted_date="2026-02-07", allowed_amount=40.0)
    assert rule_duplicate([a, b])[0]["confidence"] == 0.85  # amounts differ -> lower confidence


# --- unbundling modifier boundary: ALL components must be distinct to skip ---
def test_partial_modifier_does_not_excuse_unbundling():
    comps = ["82465", "83718", "84478"]  # lipid panel; only the first carries 59
    lines = [
        _line(claim_id="c1", line_id=f"c1-{i}", cpt_code=c, modifiers='["59"]' if i == 1 else "[]")
        for i, c in enumerate(comps, 1)
    ]
    flagged = sorted(f["claim_line_id"] for f in rule_unbundling(lines))
    assert flagged == ["c1-1", "c1-2", "c1-3"]  # one distinct modifier doesn't excuse the whole split


# --- OON boundary -----------------------------------------------------------
def test_oon_requires_both_out_status_and_in_payment():
    # out + paid out -> fine; in + paid in -> fine; only out+in+no-auth fires.
    assert rule_oon_mismatch([_line(provider_network_status="out", paid_as_network="out")]) == []
    assert rule_oon_mismatch([_line(provider_network_status="in", paid_as_network="in")]) == []
    assert len(rule_oon_mismatch([_line(provider_network_status="out", paid_as_network="in")])) == 1
