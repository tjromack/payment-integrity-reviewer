# Talking Track — Payment-Integrity Claims Reviewer

> Your study reference for speaking on this project. Stage in the portfolio arc: **AUGMENT** (flag
> problems and explain them, but keep AI on a tight leash). This project draws the sharpest line in
> the portfolio about what AI is and isn't allowed to do.

## ⚡ At a glance

- **Pitch:** Flags claims issues (duplicates, unbundling, out-of-network) with auditable rules, has AI
  explain each in plain English, and routes every one to a human.
- **Architecture:** A deterministic rules engine detects (DUP-01 / UNB-01 / OON-01 with rule ID +
  triggering fields); a constrained LLM explains only; reviewers approve/dismiss/escalate (append-only).
- **Signature decision:** Rules detect, AI explains, human decides — the LLM gets *zero authority*
  over what's flagged.
- **Eval story:** Detection precision/recall/F1 by issue type + near-miss rejection (17/17), and
  explanation faithfulness of 0.97 (deterministic check + LLM-as-judge).

---

## The 60-second pitch

**Business framing:**
"This spots likely payment-integrity issues on claims — duplicates, unbundling, out-of-network
mismatches — explains each one in plain English, routes it to a reviewer, and tracks the dollars
identified. The discipline that makes it defensible: the *detection* is transparent rules you can
audit, AI *only* writes the explanation, and a human makes every decision. Nothing about why a claim
was flagged is a black box."

**Technical framing:**
"Three concerns deliberately separated. A deterministic Python rules engine detects — DUP-01,
UNB-01, OON-01 — each flag carrying its rule ID, the exact triggering fields, and a rule-derived
confidence. Claude explains, grounded strictly in that rule and those fields, and is *forbidden* from
inventing reasons, recommending an outcome, or deciding to flag or clear. Reviewers approve, dismiss,
or escalate, stored append-only as labels — which doubles as a future training signal."

---

## Architecture (rules detect · AI explains · human decides)

```
synthetic labeled claims ──▶ RULES detect (DUP-01 / UNB-01 / OON-01)
                                   │  flag = rule ID + triggering fields + confidence
                                   ▼
                             AI explains (grounded in rule+fields ONLY; prompt versioned)
                                   │
                                   ▼
                             reviewer queue ──▶ approve / dismiss / escalate (append-only labels)
                                   │
                                   ▼
                             dashboard: volume, outcomes, ROI (Identified vs Confirmed)
```

- `app/detect.py` — the three transparent rules. Plain Python you can read and reason about.
- `app/explain.py` — the constrained LLM layer; records model id + prompt version (`explain-v2`) on
  every explanation so each is reproducible.
- `app/reference.py` — CPT prices, unbundling panel definitions, distinct-service modifiers.
- `app/roi.py` — the estimated-dollars math; assumptions documented in `data/roi_assumptions.md`.
- `app/eval.py` — detector metrics + explanation faithfulness (below).
- Tables: `claim`, `flag`, `decision` (append-only).

---

## The eval story (prove detection AND explanations)

Because the seed data carries ground-truth labels, you can measure both halves:

1. **Detection** — precision / recall / F1 **by issue type**. The real precision test is the
   **near-miss check: issue-like-but-legitimate claims correctly NOT flagged — 17/17.**
2. **Explanation faithfulness — 0.97** — a two-layer check: a deterministic keyword/field match
   *plus* an LLM-as-judge with a versioned rubric (`faithful-judge-v1`) for "no invented reasons."
   Both must pass.

---

## The signature decision

**Rules detect (auditable), AI explains (constrained), human decides.** (DECISIONS 002.) In regulated
claims work, *why* a claim was flagged must be auditable — an LLM verdict is opaque and
non-deterministic, so the LLM is given **zero authority** over detection or ranking. It only does
what it's genuinely good at: readable natural language.

---

## Honest weakness (say it before they do)

- **Recall is 1.0 only because the seed is rule-aligned by construction** — stated openly, not hidden.
  Recall against messy real-world claims would be the real test.
- The **ROI number is an estimate**, not recovered dollars — which is exactly why it's labeled
  "dollars *identified*," split from "Confirmed," with adjustable assumptions surfaced on the dashboard.

---

## Other things worth mentioning

- **The three rules, concretely:** DUP-01 = duplicate claim lines; UNB-01 = unbundling (billing a
  panel's components separately to inflate payment); OON-01 = out-of-network mismatch.
- **ROI assumptions are documented and adjustable** (duplicate 100%, unbundling gap calc, OON 35%
  delta) — the method is on the dashboard, not buried.
- **The human loop builds the dataset:** every approve/dismiss/escalate is a stored label, so the
  workflow generates the labeled data a future ML secondary signal would need.
- **Graceful degradation:** detection works with no API key; explanations are skipped and reported,
  fillable later with `make explain`.

---

## The one-liner to remember

> **"Rules detect, AI explains, a human decides — the AI never gets authority over what's flagged,
> only over how it's described."**
