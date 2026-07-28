"""Estimated-dollars-identified math.

Implements the per-issue assumptions documented in `data/roi_assumptions.md`.
This is the single source of truth for those numbers; the dashboard surfaces
`ASSUMPTIONS` so the figure is never an unexplained headline. It is an ESTIMATE
of dollars identified for review, NOT dollars recovered (CLAUDE.md §5).
"""
from __future__ import annotations

import json

from app.reference import CPT_ALLOWED

# Assumptions (see data/roi_assumptions.md). Adjust here and the dashboard follows.
OON_PRICING_DELTA = 0.35       # OON paid-as-in-network: assumed in-vs-OON price gap
UNBUNDLING_FALLBACK = 0.40     # used only if a panel has no reference price

ASSUMPTIONS = {
    "duplicate": "100% of the redundant line's allowed amount",
    "unbundling": "sum(component allowed) − comprehensive panel allowed "
    f"(or {int(UNBUNDLING_FALLBACK * 100)}% of components if the panel has no price)",
    "oon_mismatch": f"{int(OON_PRICING_DELTA * 100)}% of the line's allowed amount",
}

ISSUES = ("duplicate", "unbundling", "oon_mismatch")


def _trig(flag: dict) -> dict:
    t = flag["triggering_fields"]
    return json.loads(t) if isinstance(t, str) else t


def flag_estimate(flag: dict, claims_by_line: dict[str, dict]) -> float:
    """A single flag's estimated dollars — a **per-flag priority signal** for sorting the queue.

    Uses the same per-issue assumptions as `estimated_savings`. Note the difference in intent: the
    dashboard total dedupes unbundling to one figure per claim group, but this attributes the group
    delta to each unbundling flag so a reviewer sees its priority — so these per-flag figures are NOT
    additive into the dashboard total. It's a "review this one first" number, not an accounting line.
    """
    rule_id = flag["rule_id"]
    if rule_id == "DUP-01":
        line = claims_by_line.get(flag["claim_line_id"])
        return round(line["allowed_amount"], 2) if line else 0.0
    if rule_id == "OON-01":
        line = claims_by_line.get(flag["claim_line_id"])
        return round(OON_PRICING_DELTA * line["allowed_amount"], 2) if line else 0.0
    if rule_id == "UNB-01":
        t = _trig(flag)
        components_allowed = sum(
            claims_by_line[lid]["allowed_amount"]
            for lid in t.get("component_line_ids", [])
            if lid in claims_by_line
        )
        panel_allowed = CPT_ALLOWED.get(t.get("panel_code"))
        delta = (components_allowed - panel_allowed) if panel_allowed is not None \
            else UNBUNDLING_FALLBACK * components_allowed
        return round(max(delta, 0.0), 2)
    return 0.0


def estimated_savings(flags: list[dict], claims_by_line: dict[str, dict]) -> dict:
    """Estimate dollars identified across `flags`.

    Unbundling is counted ONCE per claim group (panel + member + provider + date),
    never once per component line, to avoid multiplying the same overpayment.
    Returns {"total": float, "by_issue": {issue: float}}.
    """
    by_issue = {issue: 0.0 for issue in ISSUES}
    seen_unbundling: set[tuple] = set()

    for flag in flags:
        rule_id = flag["rule_id"]
        if rule_id == "DUP-01":
            line = claims_by_line.get(flag["claim_line_id"])
            if line:
                by_issue["duplicate"] += line["allowed_amount"]

        elif rule_id == "OON-01":
            line = claims_by_line.get(flag["claim_line_id"])
            if line:
                by_issue["oon_mismatch"] += OON_PRICING_DELTA * line["allowed_amount"]

        elif rule_id == "UNB-01":
            t = _trig(flag)
            key = (t["panel_code"], t["member_id"], t["provider_id"], t["date_of_service"])
            if key in seen_unbundling:
                continue
            seen_unbundling.add(key)
            components_allowed = sum(
                claims_by_line[lid]["allowed_amount"]
                for lid in t["component_line_ids"]
                if lid in claims_by_line
            )
            panel_allowed = CPT_ALLOWED.get(t["panel_code"])
            if panel_allowed is not None:
                delta = components_allowed - panel_allowed
            else:
                delta = UNBUNDLING_FALLBACK * components_allowed
            by_issue["unbundling"] += max(delta, 0.0)

    by_issue = {k: round(v, 2) for k, v in by_issue.items()}
    return {"total": round(sum(by_issue.values()), 2), "by_issue": by_issue}
