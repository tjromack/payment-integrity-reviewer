# DECISIONS.md — Decision Log

Lightweight ADRs. One entry per non-trivial choice: the decision, the alternative, the why.
These are the script for "why did you build it this way?" Add an entry on every real tradeoff.

**Template**
```
## NNN. <Decision title>
- Date / phase:
- Decision:
- Alternatives considered:
- Why:
- Tradeoff accepted:
- Revisit if:
```

---

## 001. Stack: FastAPI + SQLite + HTMX
- Phase: 0
- Decision: Server-rendered HTMX on FastAPI with file-based SQLite.
- Alternatives considered: React SPA + API; Streamlit.
- Why: One developer, short timeline, must demo reliably and reset in one command. SQLite makes
  repeatable demos trivial; HTMX gives a real queue/dashboard UI without a build step.
- Revisit if: Multi-user concurrency or richer UI is needed → Postgres + a JS framework.

## 002. Rules detect; the LLM does NOT (the defining decision)
- Phase: 2/3
- Decision: Detection is done by transparent, deterministic rules. The LLM is used only to
  explain a flag in plain English, grounded in the rule and fields that fired.
- Alternatives considered: Having an LLM read each claim and decide whether it's problematic.
- Why: In a payment-integrity / regulated context, *why* a claim was flagged must be auditable
  and consistent. Rules give a concrete, inspectable trigger every time; an LLM verdict would be
  opaque, non-deterministic, and hard to defend to a reviewer or auditor. This is the core
  "where AI should and should not be used" judgment — AI is great at explanation, wrong as the
  unaccountable decision-maker here.
- Tradeoff accepted: Rules miss novel patterns a model might catch; addressed by adding a
  *monitored, explainable* ML signal later (see Path to Production), never an opaque one.
- Revisit if: Detection needs to generalize beyond hand-written rules → add a trained model as a
  clearly-labeled secondary signal with its own explainability.

## 003. Confidence score comes from the rules, not the LLM
- Phase: 2
- Decision: Each flag's confidence is derived from rule logic / signal strength.
- Why: Confidence must be reproducible and defensible. An LLM-produced number would be
  arbitrary and uncalibrated.

## 004. Human-in-the-loop is the decision point; decisions are stored as labels
- Phase: 4
- Decision: Reviewers approve / dismiss / escalate; every decision persists as labeled data.
- Why: Keeps a human accountable for the call and builds a labeled dataset that could tune
  detection later — turning the review workflow into a feedback loop.

## 005. Synthetic claims with authored ground-truth labels
- Phase: 1
- Decision: Generate synthetic claims (Synthea or authored) labeled with the true issue type,
  including clean claims and near-miss edge cases.
- Alternatives considered: Unlabeled synthetic data; anonymized real claims.
- Why: Governance (no real/PHI data) and measurability — ground-truth labels are what make
  detector precision/recall computable in `EVAL.md`. Near-miss cases make the eval honest.

## 006. The savings number is an explicit estimate with documented assumptions
- Phase: 4
- Decision: Compute "estimated dollars identified" from assumptions in
  `data/roi_assumptions.md`; always label it an estimate.
- Alternatives considered: Showing a single headline savings figure.
- Why: Overstating ROI is both dishonest and easy to puncture in an interview. Showing the
  method and assumptions is more credible than a big number, and demonstrates how I'd build a
  defensible ROI case — which the role explicitly asks for.

## 007. Explanation faithfulness is enforced and measured
- Phase: 3/5
- Decision: The explanation prompt is constrained to the triggering rule + fields; the eval
  checks that explanations don't introduce unsupported reasons.
- Why: An explanation that invents a rationale is worse than none — it would mislead a reviewer.
  Faithfulness is a measurable safety property, so it gets measured (`EVAL.md`).
