# AI Innovation Portfolio — Built Against the Posting

Three working prototypes built to demonstrate one thing: the ability to single-handedly stand up
practical, responsible AI solutions across a healthcare payer's value chain — from idea to a
demoable tool with measured results.

I treated the AI Innovation Lead posting as a backlog. Each project targets a different point in
the post-payment / payment-integrity space, exercises a different AI capability the role calls
for, and ships with the same discipline: a decision log, a demo script, and an evaluation step.
All three use **synthetic or public data only — no PHI, no internal systems.**

---

## The three projects

| # | Project | What it shows | Maps to (posting) |
|---|---------|---------------|-------------------|
| 1 | **AI Use-Case Intake & Prioritization Console** | Product/strategy thinking: structured intake, five-dimension scoring, ROI hypotheses, a "when *not* to use AI" flag, and an exec decision brief | AI opportunity pipeline, prioritization frameworks, ROI cases, responsible-AI judgment |
| 2 | **Regulatory RAG Copilot for Post-Payment** | Responsible RAG: grounded, cited answers over public CMS rules (COB/MSP/ESRD/subrogation), abstention when unsure, and a real evaluation harness | RAG, model evaluation, hallucination risk, human-in-the-loop, post-payment domain |
| 3 | **Payment-Integrity Claims Reviewer** | The right division of labor: transparent rules detect, AI explains, a human decides — with a measured detector and an estimated-savings dashboard | Automation, decision support, human-in-the-loop, cost-savings impact, payment integrity |

## How they fit the value chain

- **Project 1** is the front of the pipeline — deciding *where* to apply AI at all.
- **Project 2** is decision support inside a knowledge-heavy post-payment workflow.
- **Project 3** is operational automation in a high-stakes review workflow.

Together they cover prioritization, knowledge work, and operations — and across them, the full
set of capabilities the posting names: GenAI, RAG, agents/tooling, automation, model
evaluation, ROI measurement, and responsible AI.

## The operating pattern (consistent across all three)

Every repo is built the same way, which is itself the point — this is how I work:

- **Front-loaded structure** — `README`, `CLAUDE.md`, `TODO.md`, `DECISIONS.md`, `DEMO.md`
  (and `EVAL.md` where evaluation is substantial) before implementation.
- **Phased build with approval gates**, committing at each phase boundary so the git history is
  a readable record of decisions.
- **A decision log** capturing each tradeoff and its rejected alternative — the answer to "why
  did you build it this way?"
- **An evaluation step** so each project is judged on numbers, not just a demo.
- **Responsible-AI defaults** — synthetic/public data, human-in-the-loop, AI used where it's
  strong and deliberately not where it isn't, and honest framing of estimates and limitations.

## A note on data and scope

These are personal portfolio prototypes built on synthetic or public data. None of them use,
reference, or connect to any employer's data, code, or systems. Where a project involves
regulation, it is decision support that points to sources for human verification — not legal or
financial advice.

## Repos

- `ai-usecase-intake-console/`
- `postpay-regulatory-copilot/`
- `payment-integrity-reviewer/`

Each contains its own README, decision log, demo script, and (where applicable) evaluation
harness.
