# ROI Assumptions — "Estimated dollars identified"

The dashboard's savings figure is an **estimate**, computed from the assumptions
below applied to each flagged claim's own `allowed_amount`. It is *dollars
identified for review*, **not** dollars actually recovered. Every number here is
a documented, adjustable assumption — surfaced on the dashboard, not hidden.

These assumptions are intentionally conservative and easy to defend. They are the
script for "where does that number come from?"

---

## Per-issue method

| Issue | Estimated dollars identified per flag | Rationale |
|-------|----------------------------------------|-----------|
| **Duplicate** | `100%` of the redundant line's `allowed_amount` | The earlier submission is the legitimate payment; the later identical same-day line is a full redundant payment, so the entire allowed amount of the redundant line is recoverable. |
| **Unbundling** | `sum(component allowed_amount) − comprehensive panel allowed_amount`, computed **once per claim group** | The overpayment is the gap between billing the parts separately and the single panel price. Uses the `BUNDLES` reference table. If a claim's components map to no known panel, fall back to **40%** of the summed component allowed as the assumed overpayment. |
| **OON mismatch** | `35%` of the line's `allowed_amount` | Assumed difference between the in-network rate it was (incorrectly) paid at and the correct out-of-network obligation. A single blended pricing-delta assumption stands in for a real fee-schedule comparison. |

## Aggregation rules

- **Unbundling is counted once per claim group**, never once per component line,
  to avoid multiplying the same overpayment across the 2–3 component flags.
- The dashboard shows two figures:
  - **Identified (all flagged):** the estimate across every open/flagged claim.
  - **Confirmed (reviewer-approved):** the same method restricted to flags a
    human reviewer **approved** — the more honest "value found" number.
- Dismissed and escalated flags are excluded from the confirmed figure.

## What these assumptions deliberately do NOT claim

- They are **not** validated recovery rates from a real payer.
- They ignore appeals, partial recoveries, and collection costs.
- The OON `35%` and unbundling `40%` fallback are round, defensible placeholders
  meant to be replaced by a real fee-schedule comparison in production
  (see README → Path to Production).

## Revisit when

- A real (synthetic-but-realistic) fee schedule is available → replace the OON
  percentage and the unbundling fallback with line-level comparisons.
- Reviewer outcomes accumulate → calibrate per-issue recovery rates from the
  approve/dismiss history instead of fixed assumptions.
