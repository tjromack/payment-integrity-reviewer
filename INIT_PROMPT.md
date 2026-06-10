# INIT_PROMPT.md — Claude Code Kickoff

Paste this into Claude Code in a repo that already contains `README.md`, `CLAUDE.md`, `TODO.md`,
`DECISIONS.md`, `DEMO.md`, and `EVAL.md`.

---

You are helping me build the **Payment-Integrity Claims Reviewer**. Before writing any code,
read `README.md`, `CLAUDE.md`, `TODO.md`, `DECISIONS.md`, and `EVAL.md`. `CLAUDE.md` is your
operating contract — follow its guardrails exactly, especially the defining one: **transparent
rules do the detection; the LLM only explains a flag and never decides which claims are flagged
or cleared; a human makes the decision.**

Work through `TODO.md` **one phase at a time**. For each phase:

1. Briefly state your plan and any decision points before starting.
2. Implement only that phase. Keep modules small and single-purpose.
3. Make sure `make run` works and the relevant screen is demoable on seeded, detected data.
4. Record any non-trivial choice (rule logic, confidence scoring, the rules-vs-LLM split, ROI
   method) in `DECISIONS.md` with the rejected alternative and the why.
5. Make a single, readable commit summarizing what shipped and why.
6. **Stop and wait for my approval before starting the next phase.**

Key requirements:
- Synthetic claims only, with authored ground-truth labels (issue type or "clean"), covering
  duplicates, unbundling, and out-of-network mismatch, plus clean claims and near-miss edge
  cases. No real or PHI data.
- Each flag persists the rule id, the exact triggering fields, and a rule-derived confidence
  score. Detection must be fully explainable without the LLM.
- The explanation layer is constrained to the triggering rule + fields and must not invent
  reasons; record the LLM + prompt version with each explanation.
- The reviewer queue supports approve / dismiss / escalate and stores each decision as a label.
- The dashboard shows flagged volume, outcomes, and an **estimated** dollars-identified figure,
  with assumptions surfaced from `data/roi_assumptions.md`.
- Phase 5 builds the eval exactly as specified in `EVAL.md`: detector precision/recall/F1 by
  issue type against ground truth, and explanation faithfulness; `make eval` prints the report.
- `make reset` must wipe, re-seed, and re-detect for repeatable demos.

For Phase 1, propose the synthetic-claims approach (Synthea vs authored), the claim fields the
rules will need, and the per-issue dollar assumptions for `data/roi_assumptions.md`, for my
approval. Then implement Phase 0 (scaffold) and stop at the gate.
