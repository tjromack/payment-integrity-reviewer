# Payment-Integrity Claims Reviewer

A claims-review workflow that **detects** likely payment-integrity issues on synthetic claims
with **transparent rules**, **explains** each flag in plain English with an LLM, and routes them
through a **human approval queue** — with a running tally of estimated dollars identified.

> Built in the payment-integrity problem space using **synthetic claims only — no PHI, no
> internal systems**. This is a personal portfolio prototype. The savings figure is an explicit
> *estimate* with stated assumptions, not a financial claim.

---

## The problem it solves

Payment integrity and post-payment data mining hinge on finding the small share of claims worth
a closer look — duplicates, unbundling, out-of-network mismatches — without drowning reviewers
in false positives or making opaque automated calls on people's claims. The hard parts are
*explaining* why a claim was flagged (so a reviewer can trust and act on it) and *measuring*
whether the flagging is any good.

This tool separates those concerns cleanly: **rules detect, AI explains, a human decides**, and
a dashboard shows the resulting value.

## Who it's for

Payment-integrity / claims-review analysts and the leaders who need to see throughput and impact.

## What it does

- **Ingests synthetic claims** and flags candidate issues — duplicates, unbundling patterns,
  out-of-network mismatches — each with a confidence score and the **rule and fields that
  triggered it**.
- **Explains every flag in plain English** with an LLM, grounded strictly in the triggering
  rule and claim fields (it explains; it does not decide).
- **Human-in-the-loop queue:** reviewers approve, dismiss, or escalate; every decision is stored
  as labeled data for future improvement.
- **Dashboard:** flagged volume, reviewer outcomes (approved / dismissed / escalated), and
  **estimated dollars identified** (clearly labeled as an estimate).

## Why this design

It brings together automation, decision support, a human-in-the-loop experience, cost-savings
tracking, and responsible AI in a payment-integrity workflow. The defining design choice —
keeping *detection* transparent and auditable while using AI only for *explanation* — is the
"where AI should and should not be used" judgment applied to a regulated, high-stakes workflow.

## Tech stack

- **Backend:** FastAPI (Python)
- **Detection:** deterministic rules (+ an optional simple statistical/anomaly score), in Python
- **Explanation:** Anthropic Claude, grounded in the triggering rule + claim fields
- **Storage:** SQLite (file-based; trivial to reset for demos)
- **Frontend:** HTMX + server-rendered templates (queue + dashboard)

See `DECISIONS.md` for why each choice was made, especially why the LLM does not do detection.

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

make seed        # generate synthetic claims WITH ground-truth labels (clean + problematic)
make detect      # run the rules engine over the seed; persist flags + confidence + triggers
make run         # uvicorn app.main:app --reload  → http://localhost:8000
make eval        # detector precision/recall/F1 + explanation faithfulness (see EVAL.md)
make reset       # wipe + re-seed + re-detect for a clean demo
```

Set `ANTHROPIC_API_KEY` in `.env` for the explanation layer. Detection runs with no external
calls.

## Evaluation

Because the data is synthetic, it carries **ground-truth labels**, so detection quality is
measurable (`make eval`, see `EVAL.md`):
- **Detector precision / recall / F1** against the labeled claims.
- **Explanation faithfulness** — does the LLM explanation reference the rule and fields that
  actually fired, without inventing reasons?

## Responsible AI & data

- **Synthetic claims only**, with authored ground-truth labels. No real claims or PHI.
- **Detection is transparent.** Rules (and any statistical score) are inspectable; the reason a
  claim was flagged is always a concrete, auditable trigger — never an opaque model verdict.
- **AI explains, it does not decide.** The LLM turns a triggered rule into a readable rationale;
  it has no authority to flag or clear a claim.
- **Human decides.** Reviewers make the call; decisions are logged.
- **The dollars figure is an estimate** with assumptions shown on the dashboard.

## Path to production

- **Detection:** expand and version the rule set; add a properly trained, monitored ML model as
  a *secondary* signal with explainability, never as an unaccountable black box; track
  precision/recall drift over time.
- **Workflow:** reviewer roles/permissions, audit trail of every decision, SLA/queue management,
  and a feedback loop that retrains/tunes from reviewer labels.
- **Governance:** HIPAA-aligned handling if real claims are ever used; PII controls; full
  decision auditability; documented ROI methodology validated with finance.
- **Scale/infra:** Postgres, batch detection jobs, and eval gates in CI so a rule change can't
  ship if precision/recall regresses.

## Project structure

```
app/
  main.py          # FastAPI app + routes
  models.py        # SQLite schema (claims, flags, decisions)
  seed.py          # synthetic claims generator WITH ground-truth labels
  detect.py        # transparent rules engine (+ optional statistical score)
  explain.py       # LLM explanation grounded in the triggering rule + fields
  dashboard.py     # volume, outcomes, estimated $ identified (with assumptions)
  eval.py          # detector P/R/F1 + explanation faithfulness
  templates/       # reviewer queue + dashboard
data/
  claims.seed.json         # synthetic claims + ground-truth labels
  roi_assumptions.md       # documented assumptions behind the savings estimate
DECISIONS.md  DEMO.md  EVAL.md  TODO.md  CLAUDE.md
```

## Status

All phases complete (scaffold → labeled seed → rules engine → explanation layer → queue +
dashboard → eval → polish). `make reset && make run` gives a full demo on seeded, detected data;
`make eval` prints the metrics. New here? Start with `USER_GUIDE.md`. See `TODO.md` for the
phased plan and `DEMO.md` for the walkthrough.
