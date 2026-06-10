# CLAUDE.md — Operating Contract

Working agreement for building this project with Claude Code. Read it before each session.

## Purpose

Build the **Payment-Integrity Claims Reviewer**: a FastAPI app that flags likely
payment-integrity issues on synthetic claims with transparent rules, explains each flag with an
LLM, and routes them through a human review queue with an estimated-savings dashboard. An
interview-demo prototype that must run reliably and be auditable.

## Operating principles (guardrails)

1. **Synthetic data only.** Use synthetic claims with authored ground-truth labels. Never use
   real claims, PHI, or any internal data/systems.
2. **Detection is transparent and deterministic.** Flags come from inspectable rules (and,
   optionally, a simple statistical score). Every flag records the rule id and the claim fields
   that triggered it. Detection logic must be explainable without an LLM.
3. **The LLM explains; it never decides.** The LLM may only generate a plain-English rationale
   for a flag, grounded strictly in the triggering rule and claim fields. It must not flag,
   clear, or re-rank claims, and must not invent reasons beyond what fired.
4. **Human-in-the-loop is the decision point.** Reviewers approve / dismiss / escalate; every
   decision is stored as a label.
5. **The savings figure is an estimate.** Compute it from documented assumptions in
   `data/roi_assumptions.md`; always present it as an estimate, never as actual recovered dollars.
6. **Minimal dependencies; deterministic where possible.** Confine non-determinism to the LLM
   explanation step; record LLM + prompt version with each explanation.

## Stack

- Python 3.11+, FastAPI, Uvicorn
- Detection in plain Python (rules); optional `scikit-learn` for a simple secondary score
- SQLite via `sqlite3`
- Anthropic SDK for explanations only
- HTMX + Jinja2 templates; `pytest` for tests

## Commands

```bash
make install   # venv + install
make seed      # generate synthetic claims with ground-truth labels
make detect    # run the rules engine; persist flags + confidence + triggers
make run       # uvicorn app.main:app --reload
make eval      # detector P/R/F1 + explanation faithfulness
make test      # pytest
make reset     # wipe + re-seed + re-detect (clean demo state)
make fmt       # format
```

## Conventions

- Small, single-purpose modules (see README structure).
- Each flag persists: rule id, triggering fields, confidence, and (later) the LLM explanation.
- No secrets in code; read from `.env`.
- **Commit at each phase boundary** with a readable message; the git history is an interview
  artifact.
- Update `DECISIONS.md` on every non-trivial choice (a rule's logic, the rules-vs-LLM split,
  confidence scoring, the ROI method) with the rejected alternative and the why.

## Definition of done (per phase)

- The phase's checklist in `TODO.md` is complete.
- `make run` works and the relevant screen is demoable on seeded, detected data.
- For the eval phase: `make eval` runs and prints metrics per `EVAL.md`.
- New decisions recorded; a commit marks the phase boundary.
- **Stop and wait for my approval before the next phase.**

## Do not

- Do not let the LLM decide which claims are flagged or cleared.
- Do not let an explanation introduce a reason that the rules did not actually trigger.
- Do not present the estimated savings as real recovered dollars.
- Do not use real or PHI data; do not proceed past an approval gate without approval.
