# TODO — Phased Build Plan

Build in phases. **Stop at each approval gate.** Commit at every phase boundary.

---

## Phase 0 — Scaffold
- [ ] Repo structure per README; `requirements.txt`, `Makefile`, `.env.example`, `.gitignore`.
- [ ] FastAPI boots with a health route; base template renders.
- [ ] All docs present (`README`, `CLAUDE.md`, `TODO.md`, `DECISIONS.md`, `DEMO.md`, `EVAL.md`).
- **Gate:** app boots; structure agreed.

## Phase 1 — Synthetic claims with ground truth
- [ ] SQLite schema: `claim` (fields needed for the rules), `flag` (claim_id, rule_id,
      triggering_fields, confidence, explanation, created_at), `decision` (flag_id, action,
      reviewer, note, created_at).
- [ ] `app/seed.py`: generate synthetic claims (via Synthea or authored) labeled with
      ground-truth issue type (or "clean"), covering duplicates, unbundling, OON mismatch, and
      clean claims, including near-miss edge cases.
- [ ] `data/roi_assumptions.md`: document the per-issue dollar assumptions behind the estimate.
- [ ] `make seed` loads claims + labels; `make reset` returns to clean state.
- **Gate:** labeled seed inspectable; rule targets and ROI assumptions reviewed.

## Phase 2 — Detection engine (transparent rules)
- [ ] `app/detect.py`: rules for duplicates, unbundling patterns, and out-of-network mismatch.
- [ ] Each flag records rule id, the exact triggering fields, and a confidence score derived
      from the rule (not the LLM).
- [ ] Optional: a simple statistical/anomaly score as a clearly separate secondary signal.
- [ ] `make detect` runs the engine and persists flags.
- **Gate:** flags are correct and explainable from the rule alone, with no LLM involved.

## Phase 3 — Explanation layer (LLM)
- [ ] `app/explain.py`: given a flag's rule + triggering fields, generate a plain-English
      rationale grounded strictly in those inputs. No new reasons.
- [ ] Record LLM + prompt version with each explanation.
- **Gate:** explanations are faithful to the triggering rule on a sample of flags.

## Phase 4 — Reviewer queue & dashboard
- [ ] Queue UI: list flags; open one to see the claim, the triggering rule/fields, and the
      explanation; approve / dismiss / escalate; persist the decision as a label.
- [ ] Dashboard: flagged volume, outcomes breakdown, and **estimated dollars identified** with
      the assumptions surfaced.
- **Gate:** review one flag end to end; dashboard updates; estimate labeled as such.

## Phase 5 — Evaluation
- [ ] `app/eval.py`: detector **precision / recall / F1** vs ground-truth labels, broken out by
      issue type; plus **explanation faithfulness** (does the explanation reference the actual
      triggering rule + fields and add nothing unsupported?).
- [ ] `make eval` prints a per-issue-type table + summary; record model/prompt versions.
- **Gate:** eval runs; metrics reviewed against the thresholds in `EVAL.md`.

## Phase 6 — Polish & demo
- [ ] Empty/error states; graceful handling of the LLM call.
- [ ] Finalize `DEMO.md`; verify `make reset` → demo path works cold.
- **Gate:** full demo + eval run from a clean state.

---

## Out of scope (note in README "Path to Production")
Trained/monitored ML model as a secondary signal, RBAC + audit trail, retraining from reviewer
labels, Postgres, drift tracking, CI eval gates, validated ROI methodology.
