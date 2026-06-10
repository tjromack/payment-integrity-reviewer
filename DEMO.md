# DEMO.md — Live Demo Script

A tight, repeatable walkthrough. The moment that lands hardest: making explicit that **rules
detect, AI explains, and a human decides** — then showing the ROI tally and the eval. Practice
it cold.

## Before the demo
```bash
make reset      # wipe, re-seed labeled synthetic claims, re-run detection
make explain    # optional: generate the LLM rationales (needs ANTHROPIC_API_KEY in .env)
make run        # start server
make eval       # optional: have a fresh eval report ready to show
# open http://localhost:8000  (dashboard)
```
> Detection and the dashboard work with no API key. `make explain` is the only step that
> calls the LLM; without it, each flag's explanation panel shows a "run `make explain`" note.

## The ~90-second happy path

1. **Open on the dashboard.** Flagged volume, outcomes, and **estimated dollars identified**.
   *"Everything here is synthetic claims with ground-truth labels — no PHI. The dollar figure is
   an estimate, and I can show the assumptions behind it."*
   → Proves: framing, governance, honest ROI.

2. **Open a flagged claim.** Show the **rule that fired and the exact fields that triggered it**.
   *"Detection is transparent rules, not a black box — there's always a concrete, auditable
   reason a claim is here."*
   → Proves: the key design decision (transparent detection).

3. **Read the plain-English explanation.** *"The LLM's only job is to turn that trigger into a
   readable rationale for the reviewer, grounded in the rule and fields — and we record the model
   and prompt version. It explains — it never decides what gets flagged."*
   → Proves: AI used where it's strong, not as the unaccountable decision-maker.

4. **Make the call** — approve a clear duplicate, then dismiss or escalate another flag.
   *"A human decides; every decision is stored as a label — that's the feedback loop you'd train
   on later."* Go back to the dashboard: the approved flag now shows under **Confirmed** dollars;
   dismissed/escalated ones drop out of that figure.
   → Proves: human-in-the-loop + feedback loop. Watch the dashboard update.
   *(Note: there's nothing to "dismiss as a false positive" — the look-alike near-miss claims were
   never flagged in the first place. That's the precision story, and the eval shows it.)*

5. **Run the eval** (`make eval`). *"And I measure it: detector precision/recall/F1 by issue type
   against the ground-truth labels — including how many issue-like near-misses it correctly left
   alone — plus a faithfulness check that the explanations don't invent reasons."*
   → Proves: measurement beyond demos; calibrated honesty about recall and precision.

## The one-liner to anchor on
*"Rules detect, AI explains, a human decides — and I can prove each part works."*

## Anticipated questions (answers in DECISIONS.md / EVAL.md)
- *Why not let the LLM find the problems?* → Decision 002: auditability, determinism,
  defensibility; AI is the wrong tool for the unaccountable verdict here.
- *How do you know the detector is good?* → precision/recall/F1 by issue type vs ground truth
  (EVAL).
- *Could the explanation mislead a reviewer?* → faithfulness is constrained and measured (007 /
  EVAL).
- *Is that savings number real?* → it's an estimate with documented assumptions (006); here's
  the method.
- *How would this evolve?* → README Path to Production: monitored ML as a secondary signal,
  audit trail, retraining from reviewer labels.

## If something breaks
- Don't debug live. *"Let me reset to a clean state"* → `make reset` → reload.
- Keep a screenshot/recording of the happy path and a saved eval report in `docs/` as a fallback.
