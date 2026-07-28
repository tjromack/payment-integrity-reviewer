"""Queue UX pass (2026-07-28): a per-flag priority $ + filter/sort a reviewer can drive.

`flag_estimate` gives each flag a "review this first" dollar figure; `sort_and_filter_items` is the pure,
testable worklist logic behind the queue's filter chips + sort links. The route just wires them to the URL.
"""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from app import dashboard, roi
from app.detect import detect
from app.main import app
from app.models import connect, init_db
from app.seed import seed


# --- per-flag priority $ (pure) ----------------------------------------------

def test_flag_estimate_per_issue():
    claims = {"c1": {"allowed_amount": 200.0}}
    assert roi.flag_estimate({"rule_id": "DUP-01", "claim_line_id": "c1"}, claims) == 200.0
    # OON: 35% pricing delta of the line
    assert roi.flag_estimate({"rule_id": "OON-01", "claim_line_id": "c1"}, claims) == 70.0


def test_flag_estimate_unbundling_is_components_minus_panel():
    claims = {"a": {"allowed_amount": 30.0}, "b": {"allowed_amount": 30.0}}
    flag = {"rule_id": "UNB-01", "triggering_fields": {
        "panel_code": "80053", "component_line_ids": ["a", "b"]}}
    # CPT_ALLOWED for the panel is looked up; if present, delta = 60 - panel (>= 0)
    est = roi.flag_estimate(flag, claims)
    assert est >= 0.0 and est <= 60.0


def test_flag_estimate_unknown_or_missing_line_is_zero():
    assert roi.flag_estimate({"rule_id": "DUP-01", "claim_line_id": "nope"}, {}) == 0.0
    assert roi.flag_estimate({"rule_id": "???", "claim_line_id": "c1"}, {"c1": {"allowed_amount": 5}}) == 0.0


# --- filter + sort (pure) ----------------------------------------------------

def _item(fid, status, estimate, confidence=0.5):
    return {"flag": {"id": fid, "confidence": confidence}, "status": status, "estimate": estimate}


def _items():
    return [
        _item(1, "pending", 100.0, 0.6),
        _item(2, "approve", 500.0, 0.9),
        _item(3, "pending", 300.0, 0.7),
        _item(4, "dismiss", 50.0, 0.4),
    ]


def test_filter_by_status():
    out = dashboard.sort_and_filter_items(_items(), status="pending")
    assert {it["flag"]["id"] for it in out} == {1, 3}


def test_sort_priority_is_pending_first_then_dollars():
    out = dashboard.sort_and_filter_items(_items(), status="all", sort="priority")
    # pending (highest $ first): 3 then 1, then the decided ones by $ : 2 then 4
    assert [it["flag"]["id"] for it in out] == [3, 1, 2, 4]


def test_sort_amount_is_dollars_desc_regardless_of_status():
    out = dashboard.sort_and_filter_items(_items(), sort="amount")
    assert [it["flag"]["id"] for it in out] == [2, 3, 1, 4]


def test_sort_confidence_desc():
    out = dashboard.sort_and_filter_items(_items(), sort="confidence")
    assert [it["flag"]["id"] for it in out] == [2, 3, 1, 4]


def test_invalid_status_and_sort_fall_back_gracefully():
    out = dashboard.sort_and_filter_items(_items(), status="bogus", sort="bogus")
    assert len(out) == 4                                  # status bogus -> 'all'
    assert [it["flag"]["id"] for it in out] == [3, 1, 2, 4]   # sort bogus -> 'priority'


# --- the route wires it to the URL -------------------------------------------

@pytest.fixture
def seeded(tmp_path, monkeypatch):
    path = tmp_path / "test.db"
    monkeypatch.setattr("app.models.DB_PATH", path)
    seed()
    detect()
    yield path


def test_queue_route_renders_controls_and_estimates(seeded):
    client = TestClient(app)
    r = client.get("/queue")
    assert r.status_code == 200
    assert "Est. $ (priority)" in r.text
    assert 'class="chip' in r.text and "Sort:" in r.text


def test_queue_route_filters_and_marks_active_chip(seeded):
    client = TestClient(app)
    r = client.get("/queue?status=pending&sort=amount")
    assert r.status_code == 200
    # the active filter + sort chips are marked 'on'
    assert 'href="/queue?status=pending&sort=amount"' in r.text
    assert '?status=pending&sort=amount' in r.text
    # every visible row is pending (no decided badges present in the filtered table body)
    assert 'class="badge approve"' not in r.text and 'class="badge dismiss"' not in r.text


def test_queue_route_approved_filter_reflects_a_decision(seeded):
    conn = connect(seeded)
    init_db(conn)
    flag_id = dashboard.review_items(conn)[0]["flag"]["id"]
    dashboard.record_decision(conn, flag_id, "approve", "alice", "true positive")
    conn.close()

    client = TestClient(app)
    r = client.get("/queue?status=approve&sort=priority")
    assert r.status_code == 200
    assert 'class="badge approve"' in r.text
    assert 'class="badge pending"' not in r.text          # filtered to approved only
