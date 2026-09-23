<!--
Payment-Integrity Claims Reviewer — case study draft for tjromack.com/work/payment-integrity-reviewer.
Written to the site's existing standard (cf. /work/mcp-suite): metadata block, then
Overview · The Problem · Constraints · Architecture · Key Decisions · How It's Verified ·
What I'd Do Differently · Limits · Closing. Mixed first/third person, past tense, terse.
Voice per repo CLAUDE.md: state the numbers, no honesty-signalling. Every figure is reproducible
from the repo — see EVAL.md, `make eval`, `make holdout`.
-->

# Payment-Integrity Claims Reviewer — rules detect, an LLM explains, a human decides

**Shipped:** Aug 2026 · hardened Sep 2026
**Demonstrates:** the right division of labour — rules detect, an LLM explains, a human decides — with the detector scored on a separately-written holdout, not just the seed it was built from
**Lenses:** Applied AI (primary), Product & delivery
**Stack:** python · fastapi · htmx · sqlite · anthropic-api · docker

> Three transparent rules flag payment-integrity issues on synthetic claims, an LLM explains each flag grounded in the
> rule that fired, and a human approves, dismisses, or escalates. The detector scores 1.00 on the seed it was built
> from and 0.47 recall on a holdout written to break it — and the holdout is the number that matters.

## Overview

The reviewer takes a batch of synthetic claim lines and flags three payment-integrity issues — duplicate billing,
unbundling (a panel's components billed separately to bill more than the panel), and out-of-network claims adjudicated
as in-network. Each flag records the rule that fired and the exact fields that triggered it, with a confidence derived
from the rule, not a model. An LLM then turns that trigger into a plain-English rationale for the reviewer, and a human
approves, dismisses, or escalates each flag from a prioritised queue. A dashboard tallies the dollars identified,
labelled as an estimate.

The design choice the whole project is built around is where the model sits: **the LLM has zero authority over what gets
flagged or how it ranks.** Detection is deterministic Python; the model only explains, grounded strictly in the rule
and the triggering fields, with the model and prompt version recorded on every explanation. In a regulated review
workflow, why a claim was flagged has to be auditable — and an opaque model verdict is not.

## The Problem

Payment integrity hinges on finding the small share of claims worth a closer look without drowning reviewers in false
positives or making opaque automated calls on people's claims. The access to claims is not the hard part. The hard
parts are two: *explaining* why a claim was flagged, so a reviewer can trust it and act, and *measuring* whether the
flagging is any good — because a detector that looks impressive in a demo can be catching nothing a demo didn't stage.

## Constraints

- **Synthetic and public data only.** No PHI, no real claims, no real fee schedules. Every identifier, date, and amount
  is invented; the reference tables are hand-curated and small enough to audit.
- **Detection had to be deterministic and auditable.** A reviewer — and a compliance function behind them — has to see a
  concrete, inspectable reason a claim was flagged, so no model call could sit in the detection path.
- **The model gets no authority.** The LLM explains and nothing else; it cannot flag, clear, or rank a claim, and its
  prompt forbids any new reason or approve/deny recommendation.
- **The reviewer never sees the answer key.** The synthetic claims carry ground-truth labels for the eval, but the
  review UI hides them — a reviewer who could see the label would not be a real human-in-the-loop.
- **The hosted demo makes no model call.** Explanations are cached, so a public URL cannot run up an API bill through
  traffic and needs no key on the host.

## Architecture

Detection is a pure function over the claim lines. Three rules group and compare lines — DUP-01 on member + provider +
CPT + date, UNB-01 on a panel's components sharing a date, OON-01 on network status versus how the line was paid — and
each emits a flag carrying the rule id, the exact triggering fields, and a rule-derived confidence. It reads nothing
from the model layer and makes no external call, so the same claims always produce the same flags.

The explanation layer is separate and downstream. For each flag it sends the model only the rule description and the
recorded triggering fields; a fixed system prompt constrains it to explain those, forbids new reasons, and forbids any
recommendation. Each explanation stores the model id and a prompt version so it is reproducible. The reviewer queue is a
prioritised worklist — a per-flag dollar figure (a triage signal, not a recovered amount), filterable by decision and
sortable by priority, amount, or confidence — and every approve/dismiss/escalate is an append-only decision row. The
dashboard shows **Identified** (all flagged) against **Confirmed** (approved only), the dollar total single-sourced from
one ROI module and badged as an estimate. Detection and the whole served app run offline; the model is touched only when
explanations are generated, and on the hosted demo they are already cached.

## Key Decisions

1. **Rules detect; the LLM only explains.** Every flag is produced by inspectable Python and traces to concrete fields,
   so detection is deterministic and auditable and the model cannot invent a flag. The tradeoff is that the rules are
   only as good as they are written — which is exactly what the holdout below measures.
2. **Score against a holdout, not only the seed.** The demo seed was authored alongside the rules, so it scores a
   perfect 1.00 — which measures that the rules behave as designed, not what they cover. A separately-written holdout,
   reusing only the row schema, probes claim shapes the rules were not tuned on. The tradeoff is two datasets to keep;
   the benefit is a coverage number that means something.
3. **Faithfulness is deterministic-grounding-first, judge-second.** A deterministic check guarantees an explanation
   names the rule and cites a real triggering field; an LLM-as-judge with a versioned rubric then catches a fluent
   invented reason the keyword check would miss. The tradeoff is that the judge has its own error rate — on the run
   below, its one "unfaithful" verdict was itself the error.
4. **The reviewer works from the same evidence a real reviewer would.** Hiding the ground-truth label keeps the human
   accountable for the call and preserves a labelled decision history for a future feedback loop. There was no material
   cost to this.
5. **Host from a committed, pre-explained database.** The explanations are static over a fixed seed, so the image ships
   them cached: the running app makes no model call, needs no key, and costs nothing to host. The tradeoff is that
   refreshing the demo is a regenerate-and-recommit step rather than a live call.

## How It's Verified

Because the synthetic claims carry ground-truth labels, both halves are measurable, and every check is a deterministic
assertion over the pipeline's own output.

| Check | Result |
|---|---|
| Detector P/R/F1 on the demo seed (`make eval`) — rule-aligned by construction | **1.00 / 1.00 / 1.00** |
| Near-misses (issue-like but legitimate) correctly not flagged | 17 / 17 |
| Detector P/R/F1 on a separately-written holdout (`make holdout`) | **0.85 / 0.47 / 0.61** |
| — duplicate · unbundling · OON, on the holdout | 0.57/0.36 · 1.00/0.43 · 1.00/1.00 |
| Explanation faithfulness — deterministic grounding + LLM-judge | **0.97** (33/34; the one miss was a judge error) |
| Automated suite (offline; boundary + malformed-input tests included) | 53 tests |

The holdout is where the detector's shape shows. It nails the textbook cases (exact-date duplicates, full-panel
unbundling, and OON — all at 100%) and misses the real-world variants: **modifier-59 abuse** (a true duplicate stamped
with a distinct-service modifier it did not earn — the most-cited unbundling tactic in payment integrity), **date-drift
duplicates** (the same service billed a day apart), and **partial or cross-date unbundling**. All three trace to the
same root: DUP-01 keys on an exact date and trusts modifier 59, and UNB-01 requires the whole panel in one date-group.
Every missed line is listed in `EVAL.md` with the fix direction.

## What I'd Do Differently

Two of the holdout's early "failures" were in the eval, not the model. The metric counted a *fabrication* for any
adversarial case that failed — but a case that fails by *abstaining* emits no lure, so the count was corrected to fire
only when a forbidden value actually appears; a second grader demanded a spelled-out number the model had answered as a
digit. The fix was to the checks, not the rules. The detector's own gap — recall on near-date and partial variants — is
a rule change I have scoped rather than made: a date window on DUP-01, partial-panel detection on UNB-01, and treating
modifier 59 as scrutiny-worthy rather than exculpatory. Closing it would only need a fresh holdout to keep testing what
the rules are not tuned on.

## Limits

- It assembles evidence and a cited rationale for a human reviewer; it is **not an adjudication engine** and does not
  decide, price, or pay a claim. No auto-clear, no auto-deny.
- Synthetic, hand-labelled data only — no PHI, no real fee schedules, no payer policy library. The results show whether
  the rules behave as designed, not real-world performance on live claims.
- Three narrow rules, with a **0.47 holdout recall**: modifier-59 abuse, date-drift duplicates, and partial/cross-date
  unbundling are missed today, and are the stated fix direction.
- The dollars figure is an **estimate**, not recovered dollars — labelled *Identified*, split from *Confirmed*, with the
  assumptions surfaced on the dashboard.
- The LLM only explains, and its explanations are scored for faithfulness against a judge that has its own error rate.

## Closing

The repo is linked at the top of this page, and the live demo — https://payment-integrity-reviewer.onrender.com/ —
serves the reviewer queue and the flag detail with cached rationales, no key, on the free tier. Inside the repo,
`make eval` prints the seed metrics, `make holdout` prints the coverage number, and `EVAL.md` carries the full
breakdown: every miss, its root cause, and what would close it.
