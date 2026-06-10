"""ROI math + the decision/dashboard flow, against a fresh seeded+detected DB."""
import json

import pytest

from app import dashboard, roi
from app.models import connect, init_db
from app.seed import seed
from app.detect import detect


@pytest.fixture
def db(tmp_path, monkeypatch):
    """Isolated DB seeded and detected, so tests never touch the real data file."""
    path = tmp_path / "test.db"
    monkeypatch.setattr("app.models.DB_PATH", path)
    seed()
    detect()
    conn = connect(path)
    init_db(conn)
    yield conn
    conn.close()


# --- ROI math (pure, no DB) --------------------------------------------------
def test_duplicate_roi_is_full_allowed_of_redundant_line():
    flags = [{"rule_id": "DUP-01", "claim_line_id": "c2-1", "triggering_fields": "{}"}]
    claims = {"c2-1": {"allowed_amount": 110.0}}
    assert roi.estimated_savings(flags, claims)["by_issue"]["duplicate"] == 110.0


def test_oon_roi_applies_pricing_delta():
    flags = [{"rule_id": "OON-01", "claim_line_id": "c1-1", "triggering_fields": "{}"}]
    claims = {"c1-1": {"allowed_amount": 100.0}}
    got = roi.estimated_savings(flags, claims)["by_issue"]["oon_mismatch"]
    assert got == round(100.0 * roi.OON_PRICING_DELTA, 2)  # 35.0


def test_unbundling_roi_is_components_minus_panel_counted_once():
    trig = {
        "panel_code": "80061", "member_id": "m", "provider_id": "p",
        "date_of_service": "2026-01-01",
        "component_line_ids": ["l1", "l2", "l3"],
    }
    # Three flags for the SAME group must not triple-count.
    flags = [{"rule_id": "UNB-01", "claim_line_id": f"l{i}", "triggering_fields": json.dumps(trig)} for i in (1, 2, 3)]
    claims = {"l1": {"allowed_amount": 9.0}, "l2": {"allowed_amount": 10.0}, "l3": {"allowed_amount": 8.0}}
    # components 27 − panel 80061 allowed (19.0) = 8.0
    assert roi.estimated_savings(flags, claims)["by_issue"]["unbundling"] == 8.0


# --- dashboard summary + decision flow --------------------------------------
def test_summary_starts_all_pending_with_zero_confirmed(db):
    s = dashboard.summary(db)
    assert s["volume"]["flags"] == 34
    assert s["outcomes"]["pending"] == 34
    assert s["confirmed"]["total"] == 0.0
    assert s["identified"]["total"] > 0.0  # something is identified across flagged claims


def test_approving_a_flag_moves_it_to_confirmed(db):
    items = dashboard.review_items(db)
    dup = next(it for it in items if it["issue"] == "duplicate")
    flag_id = dup["flag"]["id"]
    allowed = dup["claim"]["allowed_amount"]

    dashboard.record_decision(db, flag_id, "approve", "alice", "looks like a true duplicate")

    s = dashboard.summary(db)
    assert s["outcomes"]["approve"] == 1
    assert s["outcomes"]["pending"] == 33
    # The approved duplicate's full allowed amount now shows as confirmed.
    assert s["confirmed"]["by_issue"]["duplicate"] == allowed
    detail = dashboard.flag_detail(db, flag_id)
    assert detail["status"] == "approve" and detail["decision"]["reviewer"] == "alice"


def test_latest_decision_wins(db):
    flag_id = dashboard.review_items(db)[0]["flag"]["id"]
    dashboard.record_decision(db, flag_id, "approve", "alice")
    dashboard.record_decision(db, flag_id, "dismiss", "bob", "false positive")
    assert dashboard.flag_detail(db, flag_id)["status"] == "dismiss"


def test_invalid_action_is_rejected(db):
    flag_id = dashboard.review_items(db)[0]["flag"]["id"]
    with pytest.raises(ValueError):
        dashboard.record_decision(db, flag_id, "nuke", "alice")
