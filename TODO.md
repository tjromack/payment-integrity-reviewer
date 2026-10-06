# TODO — Phased Build Plan

Build in phases. **Stop at each approval gate.** Commit at every phase boundary.

---

## Phase 0 — Scaffold
- [x] Repo structure per README; `requirements.txt`, `Makefile`, `.env.example`, `.gitignore`.
- [x] FastAPI boots with a health route; base template renders.
- [x] All docs present (`README`, `CLAUDE.md`, `TODO.md`, `DECISIONS.md`, `DEMO.md`, `EVAL.md`).
- **Gate:** app boots; structure agreed.

## Phase 1 — Synthetic claims with ground truth
- [x] SQLite schema: `claim` (fields needed for the rules), `flag` (claim_id, rule_id,
      triggering_fields, confidence, explanation, created_at), `decision` (flag_id, action,
      reviewer, note, created_at).
- [x] `app/seed.py`: generate synthetic claims (via Synthea or authored) labeled with
      ground-truth issue type (or "clean"), covering duplicates, unbundling, OON mismatch, and
      clean claims, including near-miss edge cases.
- [x] `data/roi_assumptions.md`: document the per-issue dollar assumptions behind the estimate.
- [x] `make seed` loads claims + labels; `make reset` returns to clean state.
- **Gate:** labeled seed inspectable; rule targets and ROI assumptions reviewed.

## Phase 2 — Detection engine (transparent rules)
- [x] `app/detect.py`: rules for duplicates, unbundling patterns, and out-of-network mismatch.
- [x] Each flag records rule id, the exact triggering fields, and a confidence score derived
      from the rule (not the LLM).
- [x] Optional: a simple statistical/anomaly score as a clearly separate secondary signal.
- [x] `make detect` runs the engine and persists flags.
- **Gate:** flags are correct and explainable from the rule alone, with no LLM involved.

## Phase 3 — Explanation layer (LLM)
- [x] `app/explain.py`: given a flag's rule + triggering fields, generate a plain-English
      rationale grounded strictly in those inputs. No new reasons.
- [x] Record LLM + prompt version with each explanation.
- **Gate:** explanations are faithful to the triggering rule on a sample of flags.

## Phase 4 — Reviewer queue & dashboard
- [x] Queue UI: list flags; open one to see the claim, the triggering rule/fields, and the
      explanation; approve / dismiss / escalate; persist the decision as a label.
- [x] Dashboard: flagged volume, outcomes breakdown, and **estimated dollars identified** with
      the assumptions surfaced.
- **Gate:** review one flag end to end; dashboard updates; estimate labeled as such.

## Phase 5 — Evaluation
- [x] `app/eval.py`: detector **precision / recall / F1** vs ground-truth labels, broken out by
      issue type; plus **explanation faithfulness** (does the explanation reference the actual
      triggering rule + fields and add nothing unsupported?).
- [x] `make eval` prints a per-issue-type table + summary; record model/prompt versions.
- **Gate:** eval runs; metrics reviewed against the thresholds in `EVAL.md`.

## Phase 6 — Polish & demo
- [x] Empty/error states; graceful handling of the LLM call.
- [x] Finalize `DEMO.md`; verify `make reset` → demo path works cold.
- **Gate:** full demo + eval run from a clean state.

## Phase 7 — Portfolio audit remediation
- [x] A separately-written holdout (`app/holdout.py`, `make holdout`) that tests the rules instead of confirming
      them; published P/R/F1 (0.85 / 0.47 / 0.61) with every miss + the fix direction in `EVAL.md` (DECISIONS 015).
- [x] Boundary + malformed-input tests (`tests/test_boundaries.py`, +15) targeting the failure modes.
- [x] Real `make explain` + faithfulness published (0.97, 33/34); EVAL.md illustrative numbers replaced with real output.
- [x] Explicit **Limits** + a **Demonstrates** line + two screenshots in the README; cross-platform quickstart.
- [x] Keyless live demo on Render (committed pre-explained fixture; DECISIONS 016) —
      https://payment-integrity-reviewer.onrender.com/
- **Gate:** clears the portfolio rubric at Featured; the case study is the last step.

## A1 add-on — the rules in SQL (portfolio playbook v3, 2026-10-06)
- [x] Re-express DUP-01 / UNB-01 / OON-01 in SQL over the same SQLite table (`app/detect_sql.py`); build the SQL from
      `reference.py` so there's one source of truth (DECISIONS 017).
- [x] Prove parity with the Python engine: bidirectional `EXCEPT` (empty both ways, equal counts) on seed + holdout,
      comparing claim_line_id + rule_id + confidence (`make sql`).
- [x] Explicit OON NULL-network policy (unknown never fires); tested on a relaxed table.
- [x] Close the two named gaps: **DUP-02** date-drift (self-join *and* `LAG`, proven equal) and **UNB-02** partial
      unbundling (DECISIONS 018). Holdout recall 0.47 → 0.86, precision 0.85 → 0.91, no new false positives.
- [x] Scoring in SQL by conditional aggregation; reproduces the Python holdout numbers for the three rules.
- [x] `make sql-dump` renders the live SQL to `sql/payment_integrity_rules.sql` (feeds the SQL drill lab).
- [x] Tests: `tests/test_detect_sql.py` (+8 → 61 total). EVAL.md, DECISIONS.md, README, case study updated.
- **Still open (documented):** modifier-59 abuse, the next-day tail of a cross-date split, the bilateral (mod-50) FP.

---

## Out of scope (note in README "Path to Production")
Trained/monitored ML model as a secondary signal, RBAC + audit trail, retraining from reviewer
labels, Postgres, drift tracking, CI eval gates, validated ROI methodology.
