# EVAL.md — Evaluation Harness

This project's data is synthetic, so it carries **ground-truth labels** — which means detection
quality is actually measurable, not just demoable. The eval answers two questions: *is the
detector any good?* and *are the AI explanations faithful to why a claim was flagged?*

Run with `make eval` (`python -m app.eval`). Each run records the LLM + prompt version.

---

## What we measure, and why

| Metric | Question it answers | Why it matters here |
|--------|--------------------|---------------------|
| **Detector precision** | Of the claims we flagged, how many were truly problematic? | High false positives waste reviewer time and erode trust. |
| **Detector recall** | Of the truly problematic claims, how many did we catch? | Misses are leaked dollars. |
| **F1, by issue type** | Balanced performance per issue (duplicate / unbundling / OON)? | A rule set can be great on one issue and useless on another; per-type breakdown exposes that. |
| **Explanation faithfulness** | Does the explanation reference the rule + fields that actually fired, and add nothing unsupported? | An invented rationale misleads reviewers — worse than no explanation. |

## Detector precision / recall / F1

Because every synthetic claim has a ground-truth label (issue type or "clean"), this is a
straightforward classification eval:

- Run `make detect` over the labeled seed.
- Compare each flag against the label.
- Report precision, recall, and F1 **overall and per issue type**, plus a small confusion
  summary (false positives and false negatives listed by claim id for inspection).

The seed carries **near-miss claims** (legitimate same-day services that *look* like an issue) so precision is
exercised. Real output of `make eval` against the demo seed:

```
DETECTOR (overall)     precision 1.00  recall 1.00  F1 1.00
  duplicate            precision 1.00  recall 1.00  F1 1.00
  unbundling           precision 1.00  recall 1.00  F1 1.00
  oon_mismatch         precision 1.00  recall 1.00  F1 1.00
  false positives: []   false negatives: []
  near-misses correctly not flagged: 17/17
```

1.00 does not mean the rules are complete. The seed was authored alongside the rules, so its positives are exactly the
patterns the rules look for and its near-misses use exactly the modifiers the rules know. A perfect score here measures
that the rules behave as designed; it does not measure coverage of cases they were not written for. The holdout does.

## Holdout (`make holdout`)

The demo seed cannot fail, so it cannot show where the rules break. `app/holdout.py` is a separately-written generator:
realistic claim shapes the rules were not tuned on, labeled for what a competent integrity system should catch. It
reuses only the row schema, never the seed's scenarios. Output:

```
HOLDOUT — 65 claim lines, separately generated
DETECTOR (overall)     precision 0.85  recall 0.47  F1 0.61
  duplicate            precision 0.57  recall 0.36  F1 0.44
  unbundling           precision 1.00  recall 0.43  F1 0.60
  oon_mismatch         precision 1.00  recall 1.00  F1 1.00

By scenario (problematic lines caught / total):
  exact_dup            caught 4/4      ← textbook cases: the rules nail them
  full_unbundle        caught 9/9
  oon                  caught 4/4
  date_drift_dup       caught 0/4      ← same service billed on adjacent days
  mod59_abuse          caught 0/3      ← a true duplicate stamped with modifier 59 it didn't earn
  partial_unbundle     caught 0/6      ← 2 of 3 panel components split out
  cross_date_unbundle  caught 0/6      ← a panel split across two days
  bilateral_fp         3/3 FALSE POSITIVES ← legit bilateral (mod 50) repeats wrongly flagged
```

**What this says, plainly.** The rules are **precise on the exact patterns they encode and have a large recall gap on
real-world variants.** OON detection is a robust field check (1.00/1.00). But duplicate/unbundling detection is narrow:

- **Recall gap (the leaked dollars).** Three of the misses are genuine blind spots worth closing — most of all
  **modifier-59 abuse**, the single most-cited unbundling/duplication tactic in payment integrity: the rule trusts a
  distinct-service modifier unconditionally, so stamping a true duplicate with `59` walks it straight through.
  **Date-drift** duplicates and **partial/cross-date** unbundling all fail on the same root cause: the rules key on an
  *exact* `date_of_service` and require the *whole* panel present.
- **Precision leak.** Modifier `50` (bilateral) is a legitimately distinct repeat, but it isn't in the rule's
  distinct-service set, so the rule flags it — 3 false positives. A real reviewer would lose trust fast.
- **Scope vs. defect.** Some narrowness is a precision/recall trade: flag only exact-date repeats to avoid firing on
  legitimate next-day care. Modifier-59 scrutiny and bilateral handling are defects. The fix direction is a date window
  on DUP-01, partial-panel detection on UNB-01, and a modifier policy that treats `59` as scrutiny-worthy rather than
  exculpatory — scoped as future work.

## The false-positive cost, and why precision comes first

A false positive here is not just wasted reviewer time. A wrong flag that reaches a provider — a demand to return money
on a legitimately-paid claim — causes **provider abrasion**: it generates pushback and appeals, consumes goodwill, and
erodes provider trust in the integrity program itself. A missed overpayment (a false negative) leaks a dollar; a false
positive can cost the relationship. The two errors are not symmetric, and the asymmetry favours precision.

That asymmetry is visible in the design, not just asserted:

- **The rules are precision-first.** They fire only on the patterns they are confident about — exact-date duplicates,
  a whole panel billed as components, an unambiguous out-of-network mismatch — and each flag carries a rule-derived
  confidence. They do **not** chase recall at the cost of firing on legitimate claims. The holdout makes the posture a
  number: **precision 0.85, recall 0.47** — the rules would rather miss a real-world variant than flag a clean claim.
- **The human is the last false-positive backstop.** No provider is ever contacted on a rule's say-so: a person
  approves, dismisses, or escalates every flag, and the "dollars identified" figure is split from the reviewer-confirmed
  figure precisely so an unreviewed flag never counts as a recovery. The most important threshold is not a number — it
  is the human in the loop.
- **The tunable threshold reflects the cost.** `PRECISION_TARGET` (≥ 0.85 in the eval) is the dial: it is set against a
  reviewer's tolerance for false positives, not against a recall goal. In production it would be calibrated from the
  approve/dismiss history — the accumulated cost of each wrong flag — rather than a fixed assumption.

The tradeoff is stated openly in the holdout: precision-first means real recall gaps (modifier-59 abuse, date-drift
duplicates, partial unbundling). Closing them is a rule change that must not raise the false-positive rate — which is the
whole point of scoring precision and recall separately, and never letting recall be bought with provider abrasion.

## Explanation faithfulness

The LLM only explains; this checks it explains *honestly*. For each flagged claim, the
faithfulness check verifies the explanation:

1. **References the triggering rule** that actually fired (rule id / name), and
2. **Cites the actual triggering fields** present on the claim, and
3. **Introduces no new reason** not implied by the rule + fields.

Implement as a deterministic check where possible (does the explanation mention the rule and the
fields the detector recorded?), backed by an LLM-as-judge pass for the "no invented reasons"
part, with a versioned rubric:

```
You are given the RULE that fired, the TRIGGERING FIELDS, and an EXPLANATION.
Score faithful=1 only if the explanation is fully supported by the rule and fields and adds no
new reason; faithful=0 otherwise. Output strict JSON: {"faithful": 0|1, "issues": [..]}.
Judge only against the rule and fields provided; use no outside knowledge.
```

Real output of `make explain` + `make eval` (deterministic grounding on every flag, then the LLM-judge for the
"no invented reasons" part):

```
EXPLANATION FAITHFULNESS   0.97  (33/34 faithful — LLM-judged by claude-opus-4-8, rubric faithful-judge-v1)
  unfaithful clm_0058-2: judge flagged a component_map / line-id mismatch
```

The single flagged case is, on inspection, a **judge error, not an explanation defect** — the judge's own rationale
walks through the mapping and concludes the explanation is consistent, then still returns `faithful=0`. This is exactly
the LLM-as-judge error rate the limitations section warns about, which is why the check is deterministic-grounding-first
and the judge is spot-checked rather than trusted blindly. Grounding (the deterministic half) passes on all 34.

## Suggested thresholds (tune as the rules settle)

- Explanation faithfulness ≥ 0.95 — an explanation that fabricates a reason is a real defect.
- Detector precision: set against reviewer tolerance for false positives (e.g., ≥ 0.85).
- Detector recall: set against the cost of misses; report it honestly rather than chasing 1.0.

## Note on the savings estimate (not a model metric)

The dashboard's "estimated dollars identified" is a business estimate, not an eval metric. Its
assumptions live in `data/roi_assumptions.md` and should be reviewed separately. Keep it labeled
as an estimate; do not treat it as validated recovery.

## Limitations (state these honestly)

- Synthetic, hand-labeled data — results show whether the rules behave as designed, not
  real-world performance.
- LLM-as-judge for the "no invented reasons" check has its own error rate; spot-check a sample.
- Per-type metrics depend on having enough examples of each issue in the seed.
