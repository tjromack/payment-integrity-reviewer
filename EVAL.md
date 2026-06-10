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

Include **near-miss claims** in the seed (e.g., legitimate same-day services that *look* like a
duplicate) so recall isn't trivially 1.0 and precision is actually tested.

```
DETECTOR (overall)     precision 0.88  recall 0.81  F1 0.84
  duplicate            precision 0.93  recall 0.90  F1 0.92
  unbundling           precision 0.84  recall 0.74  F1 0.79
  oon_mismatch         precision 0.86  recall 0.79  F1 0.82
  false positives: [clm_0142, clm_0317]   false negatives: [clm_0088, ...]
```

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

```
EXPLANATION FAITHFULNESS   0.96  (unfaithful: 1/26 — invented a reason on clm_0203)
```

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
