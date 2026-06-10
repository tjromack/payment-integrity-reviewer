"""Rules-engine tests: each rule fires on a true positive and, crucially, does
NOT fire on its near-miss. These guard the Phase 2 gate — flags are correct and
explainable from the rule alone — and lock in the precision-protecting behavior.
"""
import json

from app import detect
from app.detect import detect_flags, rule_duplicate, rule_unbundling, rule_oon_mismatch
from app.seed import build_rows


def _line(**over):
    """A minimal in-network clean claim line; override fields per test."""
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


# --- DUP-01 ------------------------------------------------------------------
def test_duplicate_fires_on_redundant_later_line():
    a = _line(claim_id="c1", line_id="c1-1", submitted_date="2026-02-03")
    b = _line(claim_id="c2", line_id="c2-1", submitted_date="2026-02-07")
    flags = rule_duplicate([a, b])
    assert [f["claim_line_id"] for f in flags] == ["c2-1"]  # later line only
    trig = json.loads(flags[0]["triggering_fields"])
    assert trig["duplicate_of_line_id"] == "c1-1"
    assert flags[0]["confidence"] == 0.95  # identical amount + units


def test_duplicate_skips_near_miss_with_distinct_modifier():
    a = _line(claim_id="c1", line_id="c1-1", submitted_date="2026-02-03")
    b = _line(claim_id="c2", line_id="c2-1", submitted_date="2026-02-07", modifiers='["76"]')
    assert rule_duplicate([a, b]) == []


# --- UNB-01 ------------------------------------------------------------------
def test_unbundling_fires_on_full_panel_split():
    comps = ["82465", "83718", "84478"]  # lipid panel 80061 components
    lines = [_line(claim_id="c1", line_id=f"c1-{i}", cpt_code=c) for i, c in enumerate(comps, 1)]
    flags = rule_unbundling(lines)
    assert sorted(f["claim_line_id"] for f in flags) == ["c1-1", "c1-2", "c1-3"]
    assert json.loads(flags[0]["triggering_fields"])["panel_code"] == "80061"


def test_unbundling_skips_near_miss_with_distinct_modifier():
    comps = ["82465", "83718", "84478"]
    lines = [
        _line(claim_id="c1", line_id=f"c1-{i}", cpt_code=c, modifiers='["59"]')
        for i, c in enumerate(comps, 1)
    ]
    assert rule_unbundling(lines) == []


def test_unbundling_skips_incomplete_panel():
    lines = [_line(line_id="c1-1", cpt_code="82465"), _line(line_id="c1-2", cpt_code="83718")]
    assert rule_unbundling(lines) == []  # only 2 of 3 components


# --- OON-01 ------------------------------------------------------------------
def test_oon_fires_on_out_paid_as_in_without_auth():
    line = _line(provider_network_status="out", paid_as_network="in", auth_or_emergency=0)
    flags = rule_oon_mismatch([line])
    assert len(flags) == 1 and flags[0]["rule_id"] == "OON-01"


def test_oon_skips_authorized_near_miss():
    line = _line(provider_network_status="out", paid_as_network="in", auth_or_emergency=1)
    assert rule_oon_mismatch([line]) == []


def test_oon_skips_correctly_paid_out_of_network():
    line = _line(provider_network_status="out", paid_as_network="out", auth_or_emergency=0)
    assert rule_oon_mismatch([line]) == []


# --- end-to-end on the real seed --------------------------------------------
def test_seed_detection_is_perfect_and_skips_all_near_misses():
    rows = build_rows()
    by_id = {r["line_id"]: r for r in rows}
    flagged = {f["claim_line_id"] for f in detect_flags(rows)}

    issues = {lid for lid, r in by_id.items() if r["label"] != "clean"}
    near_misses = {lid for lid, r in by_id.items() if r["is_near_miss"]}

    assert flagged == issues          # no false positives, no false negatives
    assert flagged & near_misses == set()  # never fires on a near-miss


def test_rule_to_issue_covers_every_rule():
    produced = {f["rule_id"] for f in detect_flags(build_rows())}
    assert produced == set(detect.RULE_TO_ISSUE)
