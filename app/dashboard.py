"""Read-side aggregation for the queue and dashboard.

Pulls flags joined to their claim line and current review status, and computes
the volume / outcomes / estimated-savings figures. Pure-ish: all DB access is
funneled through small helpers so the numbers are easy to test.
"""
from __future__ import annotations

import json

from app import roi
from app.detect import RULE_TO_ISSUE

ACTIONS = ("approve", "dismiss", "escalate")
STATUS_PENDING = "pending"


def _claims_by_line(conn) -> dict[str, dict]:
    return {r["line_id"]: dict(r) for r in conn.execute("SELECT * FROM claim")}


def _latest_status(conn) -> dict[int, dict]:
    """Map flag_id -> its most recent decision row (by id)."""
    latest: dict[int, dict] = {}
    for r in conn.execute("SELECT * FROM decision ORDER BY id"):
        latest[r["flag_id"]] = dict(r)  # later rows overwrite -> last wins
    return latest


def review_items(conn) -> list[dict]:
    """Every flag with its claim line, issue type, and current status."""
    claims = _claims_by_line(conn)
    status = _latest_status(conn)
    items = []
    for f in conn.execute("SELECT * FROM flag ORDER BY id"):
        flag = dict(f)
        claim = claims.get(flag["claim_line_id"], {})
        decision = status.get(flag["id"])
        items.append(
            {
                "flag": flag,
                "claim": claim,
                "issue": RULE_TO_ISSUE.get(flag["rule_id"], flag["rule_id"]),
                "status": decision["action"] if decision else STATUS_PENDING,
                "decision": decision,
                "triggering_fields": json.loads(flag["triggering_fields"]),
            }
        )
    # Pending first (the reviewer's worklist), then by id.
    items.sort(key=lambda it: (it["status"] != STATUS_PENDING, it["flag"]["id"]))
    return items


def flag_detail(conn, flag_id: int) -> dict | None:
    """One flag with everything the detail view needs, or None if missing."""
    row = conn.execute("SELECT * FROM flag WHERE id = ?", (flag_id,)).fetchone()
    if row is None:
        return None
    flag = dict(row)
    claim = conn.execute(
        "SELECT * FROM claim WHERE line_id = ?", (flag["claim_line_id"],)
    ).fetchone()
    status = _latest_status(conn).get(flag_id)
    return {
        "flag": flag,
        "claim": dict(claim) if claim else {},
        "issue": RULE_TO_ISSUE.get(flag["rule_id"], flag["rule_id"]),
        "triggering_fields": json.loads(flag["triggering_fields"]),
        "status": status["action"] if status else STATUS_PENDING,
        "decision": status,
    }


def record_decision(conn, flag_id: int, action: str, reviewer: str, note: str = "") -> None:
    """Persist a reviewer decision as a label (CLAUDE.md §4)."""
    if action not in ACTIONS:
        raise ValueError(f"invalid action: {action!r}")
    from datetime import datetime, timezone

    conn.execute(
        """INSERT INTO decision (flag_id, action, reviewer, note, created_at)
           VALUES (?, ?, ?, ?, ?)""",
        (flag_id, action, reviewer, note, datetime.now(timezone.utc).isoformat(timespec="seconds")),
    )
    conn.commit()


def summary(conn) -> dict:
    """Volume, outcomes, and estimated dollars identified vs reviewer-confirmed."""
    claims = _claims_by_line(conn)
    status = _latest_status(conn)
    flags = [dict(r) for r in conn.execute("SELECT * FROM flag ORDER BY id")]

    outcomes = {STATUS_PENDING: 0, **{a: 0 for a in ACTIONS}}
    for f in flags:
        decision = status.get(f["id"])
        outcomes[decision["action"] if decision else STATUS_PENDING] += 1

    approved = [f for f in flags if (status.get(f["id"]) or {}).get("action") == "approve"]

    identified = roi.estimated_savings(flags, claims)
    confirmed = roi.estimated_savings(approved, claims)

    return {
        "volume": {
            "flags": len(flags),
            "claims_flagged": len({f["claim_line_id"] for f in flags}),
        },
        "outcomes": outcomes,
        "identified": identified,
        "confirmed": confirmed,
        "assumptions": roi.ASSUMPTIONS,
    }
