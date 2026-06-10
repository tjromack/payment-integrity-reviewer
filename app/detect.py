"""Transparent, deterministic rules engine.

This is the heart of the project's defining decision: **rules detect, the LLM does
not**. Every flag is produced here, by inspectable Python, and records the rule
id, the *exact* claim fields/values that triggered it, and a confidence derived
from the rule itself — never from a model. Detection makes no external calls and
reads nothing from the LLM layer.

Three rules, each with a near-miss it must NOT fire on:
  DUP-01  duplicate           same member+provider+CPT+date, later submission,
                              no distinct-service modifier (76/59/91/...).
  UNB-01  unbundling          a panel's components billed separately on the same
                              member+provider+date, without distinct-service
                              modifiers, when one comprehensive code exists.
  OON-01  oon_mismatch        out-of-network provider adjudicated as in-network
                              with no authorization/emergency on file.

Confidence is rule-derived and reproducible (see DECISIONS.md 003 / 009).
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone

from app import reference as ref
from app.models import connect, init_db

RULE_TO_ISSUE = {
    "DUP-01": "duplicate",
    "UNB-01": "unbundling",
    "OON-01": "oon_mismatch",
}


# --- helpers -----------------------------------------------------------------
def _mods(row: dict) -> set[str]:
    return set(json.loads(row["modifiers"]))


def _has_distinct_modifier(row: dict) -> bool:
    return bool(_mods(row) & ref.DISTINCT_SERVICE_MODIFIERS)


def _flag(line_id: str, rule_id: str, triggering: dict, confidence: float) -> dict:
    return {
        "claim_line_id": line_id,
        "rule_id": rule_id,
        "triggering_fields": json.dumps(triggering),
        "confidence": round(confidence, 2),
    }


# --- DUP-01: duplicate -------------------------------------------------------
def rule_duplicate(rows: list[dict]) -> list[dict]:
    """Flag redundant same-day repeats of an identical service.

    Lines sharing member + provider + CPT + date_of_service are grouped; the
    earliest submission is the legitimate one, later identical lines are
    redundant — unless a later line carries a distinct-service modifier
    (e.g. 76/59/91), which makes the repeat legitimately separate.
    """
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        key = (r["member_id"], r["provider_id"], r["cpt_code"], r["date_of_service"])
        groups[key].append(r)

    flags: list[dict] = []
    for key, lines in groups.items():
        if len(lines) < 2:
            continue
        lines.sort(key=lambda r: (r["submitted_date"], r["line_id"]))
        original = lines[0]
        for dup in lines[1:]:
            if _has_distinct_modifier(dup):
                continue  # legitimate distinct/repeat service — near-miss, don't flag
            identical_amount = (
                dup["allowed_amount"] == original["allowed_amount"]
                and dup["units"] == original["units"]
            )
            confidence = 0.95 if identical_amount else 0.85
            flags.append(
                _flag(
                    dup["line_id"],
                    "DUP-01",
                    {
                        "member_id": dup["member_id"],
                        "provider_id": dup["provider_id"],
                        "cpt_code": dup["cpt_code"],
                        "date_of_service": dup["date_of_service"],
                        "duplicate_of_line_id": original["line_id"],
                        "this_submitted_date": dup["submitted_date"],
                        "original_submitted_date": original["submitted_date"],
                        "allowed_amount": dup["allowed_amount"],
                        "modifiers": json.loads(dup["modifiers"]),
                    },
                    confidence,
                )
            )
    return flags


# --- UNB-01: unbundling ------------------------------------------------------
def rule_unbundling(rows: list[dict]) -> list[dict]:
    """Flag component codes of a panel billed separately instead of the panel.

    Lines sharing member + provider + date_of_service are grouped; if the group's
    CPTs contain every component of a known panel, and the component lines do not
    all carry a distinct-service modifier, each component line is flagged.
    """
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        key = (r["member_id"], r["provider_id"], r["date_of_service"])
        groups[key].append(r)

    flags: list[dict] = []
    for key, lines in groups.items():
        cpts = {r["cpt_code"] for r in lines}
        panel = ref.panel_for_components(cpts)
        if panel is None:
            continue
        components = set(ref.BUNDLES[panel]["components"])
        component_lines = [r for r in lines if r["cpt_code"] in components]
        # If every component asserts a distinct service, treat as legitimate.
        if all(_has_distinct_modifier(r) for r in component_lines):
            continue
        present = sorted({r["cpt_code"] for r in component_lines})
        line_ids = sorted(r["line_id"] for r in component_lines)
        for r in component_lines:
            flags.append(
                _flag(
                    r["line_id"],
                    "UNB-01",
                    {
                        "panel_code": panel,
                        "panel_name": ref.BUNDLES[panel]["name"],
                        "components_present": present,
                        "component_line_ids": line_ids,
                        "this_cpt_code": r["cpt_code"],
                        "member_id": r["member_id"],
                        "provider_id": r["provider_id"],
                        "date_of_service": r["date_of_service"],
                        "modifiers": json.loads(r["modifiers"]),
                    },
                    0.90,
                )
            )
    return flags


# --- OON-01: out-of-network mismatch -----------------------------------------
def rule_oon_mismatch(rows: list[dict]) -> list[dict]:
    """Flag out-of-network lines adjudicated as in-network with no auth/emergency."""
    flags: list[dict] = []
    for r in rows:
        if (
            r["provider_network_status"] == ref.NETWORK_OUT
            and r["paid_as_network"] == ref.NETWORK_IN
            and not r["auth_or_emergency"]
        ):
            flags.append(
                _flag(
                    r["line_id"],
                    "OON-01",
                    {
                        "provider_network_status": r["provider_network_status"],
                        "paid_as_network": r["paid_as_network"],
                        "auth_or_emergency": r["auth_or_emergency"],
                        "provider_id": r["provider_id"],
                        "allowed_amount": r["allowed_amount"],
                    },
                    0.92,
                )
            )
    return flags


RULES = (rule_duplicate, rule_unbundling, rule_oon_mismatch)


def detect_flags(rows: list[dict]) -> list[dict]:
    """Run every rule over the claim lines and return all flags (pure function)."""
    flags: list[dict] = []
    for rule in RULES:
        flags.extend(rule(rows))
    return flags


def detect() -> dict[str, int]:
    """Load claims, run the rules, and persist flags (idempotent)."""
    conn = connect()
    init_db(conn)
    rows = [dict(r) for r in conn.execute("SELECT * FROM claim")]

    flags = detect_flags(rows)

    # Idempotent re-detection: flags are upstream of human review, so clear any
    # prior flags (and the decisions that referenced them) before re-persisting.
    cleared_decisions = conn.execute("SELECT COUNT(*) FROM decision").fetchone()[0]
    conn.execute("DELETE FROM decision")
    conn.execute("DELETE FROM flag")
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    conn.executemany(
        """INSERT INTO flag (claim_line_id, rule_id, triggering_fields, confidence, created_at)
           VALUES (:claim_line_id, :rule_id, :triggering_fields, :confidence, :created_at)""",
        [{**f, "created_at": now} for f in flags],
    )
    conn.commit()

    counts: dict[str, int] = {"total": len(flags), "_cleared_decisions": cleared_decisions}
    for f in flags:
        counts[f["rule_id"]] = counts.get(f["rule_id"], 0) + 1
    conn.close()
    return counts


def main() -> None:
    counts = detect()
    print(f"Detected {counts['total']} flags (rules only - no LLM involved).")
    for rule_id, issue in RULE_TO_ISSUE.items():
        print(f"  {rule_id}  {issue:<13} {counts.get(rule_id, 0)}")
    if counts["_cleared_decisions"]:
        print(f"  (cleared {counts['_cleared_decisions']} prior reviewer decision(s) on re-detect)")


if __name__ == "__main__":
    main()
