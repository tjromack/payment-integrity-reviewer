# MASTERY.md — Owning This Project

Five things to do cold, no notes: **explain** it in 60 seconds, **draw** the architecture,
**rebuild** the core engine, **extend** it to a new domain, and **defend** every decision.

> **Quick map of the codebase**
> - `app/reference.py` — shared domain data: CPT prices, unbundling panels, distinct-service modifiers
> - `app/seed.py` — deterministic synthetic-claims generator with authored ground-truth labels
> - `app/models.py` — SQLite schema: `claim`, `flag`, `decision` + connection helpers
> - `app/detect.py` — the transparent rules engine (DUP-01 / UNB-01 / OON-01) → flags
> - `app/explain.py` — LLM rationale grounded strictly in the rule + triggering fields
> - `app/roi.py` — estimated-dollars-identified math (the documented assumptions)
> - `app/dashboard.py` — queue items, decisions, volume/outcomes/savings aggregation
> - `app/eval.py` — detector P/R/F1 vs labels + explanation faithfulness
> - `app/main.py` + `app/templates/` — FastAPI routes and the HTMX/Jinja UI
> - `data/roi_assumptions.md`, `DECISIONS.md`, `EVAL.md` — the documented "why"

---

## 1. Explain what it does and why, in plain English, in 60 seconds

> It's a payment-integrity claims reviewer for a healthcare payer. It takes synthetic medical
> claims and flags the ones worth a closer look — duplicates, unbundling, out-of-network
> mismatches. The whole point is the division of labor: **transparent, deterministic rules
> decide which claims get flagged; an LLM only writes a plain-English reason for each flag; and a
> human reviewer makes the actual call.** Every flag records the rule that fired and the exact
> fields that triggered it, so there's always a concrete, auditable reason — never an opaque
> model verdict. The LLM is constrained to the triggering rule and fields and is forbidden from
> recommending an outcome, and I measure that it stays faithful. A dashboard shows flagged
> volume, reviewer outcomes, and an explicitly-labeled *estimated* dollars-identified figure with
> its assumptions shown. Everything is synthetic with ground-truth labels, so detection quality
> is actually measurable.

**The one-sentence version:** Rules detect, AI explains, a human decides — and each part is
independently provable.

**The three words to never lose:** **Detect** (rules) · **Explain** (AI) · **Decide** (human).

**Self-check:** you've got it when you can say *why the LLM is deliberately kept out of the
detection decision* without reaching for notes — auditability, determinism, defensibility.

---

## 2. Draw the architecture from memory

```
              synthetic claims with authored labels
                         │  make seed  (app/seed.py)
                         ▼
                 ┌──────────────────┐
                 │  claim  (SQLite) │   label = ground truth, EVAL ONLY
                 └────────┬─────────┘
   make detect           │   rules only · OFFLINE · deterministic
   (app/detect.py)       ▼
            ┌────────────────────────────────┐
            │ flag: rule_id, triggering_      │
            │ fields, confidence              │
            └──────┬───────────────────┬──────┘
  make explain     │                   │
  (app/explain.py) │  LLM · ONLINE     │
  grounded reason ─┘  → flag.explanation│
                                        ▼
                          ┌──────────────────────────┐
                          │ reviewer queue (app/main) │
                          │ approve / dismiss /escalate│
                          └────────────┬─────────────┘
                                       │  decision row (label, append-only)
                                       ▼
                          ┌──────────────────────────┐
                          │ dashboard: outcomes +     │
                          │ estimated $ (app/roi.py)  │
                          └──────────────────────────┘

  make eval (app/eval.py): reads claim + flag
     → detector precision/recall/F1 vs labels
     → explanation faithfulness (deterministic check + LLM judge)
```

**Memory aids:**
- **Stages (mnemonic "Some Dogs Explain, Reviewers Decide"):** **S**eed → **D**etect →
  **E**xplain → **R**eview → **D**ashboard, with **eval** sitting off to the side reading the
  same tables.
- **Offline/online split:** seed, detect, the dashboard, the queue, and the *detection* half of
  eval are **fully offline and deterministic** — no key, no network. The **only** networked,
  non-deterministic step is `make explain` (and the faithfulness *judge* in `make eval`).
- **Where the model call happens:** exactly one place — `explain.explain_flag()` calling the
  Anthropic Messages API. Detection never calls a model.

**Self-check:** redraw it on a blank board and circle the single box that touches the network.

---

## 3. Rebuild this core engine from scratch

**Build order & contracts** (this is the order I actually built it, each layer standing alone):

1. **`reference.py`** — *in:* nothing; *out:* the domain tables (CPT→allowed price, panel→
   components, the set of distinct-service modifiers). Comes first because both the seed and the
   rules reason over the *same* tables.
2. **`models.py`** — *in:* a path; *out:* an SQLite connection + the `claim` / `flag` /
   `decision` schema. `connect()` resolves `DB_PATH` at call time so tests use a temp DB.
3. **`seed.py`** — *in:* the reference data + a fixed RNG seed; *out:* deterministic labeled
   claim rows (clean / duplicate / unbundling / oon_mismatch, plus near-misses). Comes before
   detection because you can't measure a detector without labeled data.
4. **`detect.py`** — *in:* claim rows; *out:* `flag` rows, each with `rule_id`,
   `triggering_fields` (the exact values that fired), and a rule-derived `confidence`. Pure
   functions (`rule_duplicate`, `rule_unbundling`, `rule_oon_mismatch`); no LLM, no I/O.
5. **`explain.py`** — *in:* one flag; *out:* a grounded rationale + the `model` + `prompt_version`
   it was made with. `build_messages()` is pure (rule description + triggering fields only);
   `is_grounded()` is the deterministic faithfulness guard.
6. **`roi.py`** — *in:* flags + claims-by-line; *out:* `{total, by_issue}` estimated dollars,
   unbundling counted once per claim group. Single source of the documented assumptions.
7. **`dashboard.py`** — *in:* a connection; *out:* queue items, per-flag detail, append-only
   decision writes, and the volume/outcomes/savings summary.
8. **`eval.py`** — *in:* claims + flags; *out:* detector P/R/F1 (+ FP/FN ids, near-miss count)
   and faithfulness (deterministic + LLM judge).

**The minimal happy path in pseudocode** (the thing to write cold):

```
rows  = load_claims()                          # SQLite (models.py)
flags = []
for rule in (duplicate, unbundling, oon):      # detect.py — pure rules
    flags += rule(rows)                         # -> rule_id, triggering_fields, confidence
persist(flags)

for flag in flags:                             # explain.py — optional, needs API key
    system, user = build_messages(flag)         # rule description + triggering fields ONLY
    text = llm(system, user)                     # opus-4-8; NO temperature / NO thinking
    save(flag, text, model, prompt_version)      # record how it was made

# review:    human picks approve/dismiss/escalate -> append a decision row
# dashboard: outcomes + estimated $ (identified across flagged vs confirmed=approved)
# eval:      detector_metrics(claims, flags)  +  faithfulness_metrics(flags)
```

**Non-core add-ons:** the web layer (`main.py` + Jinja/HTMX templates) is a thin shell over
`dashboard.py`; the eval is a measurement harness, not part of the production path. Strip both
and the engine still runs via `make seed && make detect`.

**Self-check:** write `rule_oon_mismatch` from memory — group/filter, then emit a flag with
`rule_id`, the exact triggering fields, and a fixed confidence. No model anywhere in it.

---

## 4. Extend it to a new domain by swapping the "swap layer"

This project is a **reusable engine + a thin domain swap layer**. To retarget it (say, to
prior-authorization abuse, or pharmacy-claim anomalies), you edit only the swap layer:

| Swap this | File | What changes |
|-----------|------|--------------|
| Domain reference data | `app/reference.py` | The code/price tables, the "bundle" relationships, the modifiers that make a match legitimate |
| The rules | `app/detect.py` | The `rule_*` functions + their grouping keys, near-miss exceptions, and confidence tiers; update `RULE_TO_ISSUE` |
| Claim fields | `app/models.py` | The columns on `claim` your rules need |
| Synthetic data + labels | `app/seed.py` | The scenario generators and the ground-truth labels (incl. near-misses) |
| Rule descriptions for the LLM | `app/explain.py` | `RULE_DESCRIPTIONS` (the grounding text per rule) |
| ROI assumptions | `app/roi.py` + `data/roi_assumptions.md` | The per-issue dollar method and the surfaced assumptions |

**The engine (what you DON'T touch):** the `flag`/`decision` persistence pattern; the
explanation mechanism (`build_messages` grounding + `is_grounded` + the no-outcome system
prompt); the eval harness (`prf`, `detector_metrics`, the two-layer `faithfulness_metrics` and
its rubric); the queue/decision flow and the dashboard aggregation; the offline/online split.
None of these know what a "claim" or a "CPT code" is.

**The recipe:**
1. Replace the tables in `reference.py` with your domain's reference data.
2. Add the columns your rules need to the `claim` schema in `models.py`.
3. Rewrite the `rule_*` functions in `detect.py` (keep the contract: emit `rule_id`,
   `triggering_fields`, `confidence`) and update `RULE_TO_ISSUE`.
4. Author labeled scenarios + near-misses in `seed.py`.
5. Add a `RULE_DESCRIPTIONS` entry per rule in `explain.py`.
6. Set the per-issue ROI method in `roi.py` and document it in `data/roi_assumptions.md`.
7. `make reset && make eval` — the metrics, queue, dashboard, and faithfulness check all work
   unchanged.

**Why it's this clean:** the engine only ever sees a *flag* — `(rule_id, triggering_fields,
confidence)` — and a *label*. Detection is pure functions over rows; the explainer is told "here
is a rule and the fields that fired, write why" with no domain logic baked in; the eval compares
predicted issue to ground-truth label generically. The domain lives entirely in the data and the
rule bodies, so the seam is real, not aspirational.

**Self-check:** name the six swap files and the one-line contract the engine depends on
(`rule_id` + `triggering_fields` + `confidence`).

---

## 5. Defend every design decision to a skeptic

**Why don't you just let the LLM read each claim and decide what's problematic?** Because in a
regulated, high-stakes workflow *why* a claim was flagged has to be auditable, consistent, and
defensible. Rules give a concrete, inspectable trigger every time; an LLM verdict would be
opaque and non-deterministic. AI is great at *explanation* and wrong as the unaccountable
decision-maker here (002). The cost — rules miss novel patterns — is addressed later by a
*monitored, explainable* secondary model, never an opaque one.

**Where does the confidence score come from, then?** From the rule logic, not the model — e.g.
DUP-01 is 0.95 when the redundant line matches the original on allowed amount and units, else
0.85; OON-01 is 0.92 (a deterministic adjudication discrepancy) (003, 009). An LLM-produced
number would be arbitrary and uncalibrated.

**Your detector scores precision/recall/F1 = 1.00. Isn't that a red flag?** Yes, and I say so
plainly: the synthetic seed is rule-aligned by construction, so perfect scores are *expected* and
don't claim real-world performance (009, EVAL.md). The number that actually means something is
**near-misses correctly not flagged: 17/17** — claims engineered to *look* like issues (a
same-day repeat with modifier 76, an authorized out-of-network visit) that the rules correctly
leave alone. That's what exercises precision. Run `make eval` to reproduce.

**How do you stop the explanation from inventing a reason, and how do you know it works?** The
system prompt constrains the LLM to the triggering rule + fields and forbids recommending an
outcome (007, 011). I *measure* it two ways: a deterministic `is_grounded()` check (does it name
the rule and cite a real triggering value?) plus an LLM-as-judge for "no invented reasons" using
a versioned rubric (`faithful-judge-v1`). Live, faithfulness is **0.97 (33/34)** — and the one
failure is a genuine hallucinated component code the judge caught, left as an honest finding
because the human reviewer is the backstop (013, 014). Run `make explain && make eval`.

**That 0.47 → 0.97 jump — what happened?** The first live eval surfaced two real issues:
unbundling explanations never named the rule (my grounding check was also too strict), and they
inferred a CPT→line-id pairing the fields didn't state. I fixed them at the source — prompt v2
names the rule and forbids pairing unstated lists, and the UNB-01 flag now carries an explicit
`component_map` — rather than loosening the eval to hit a number (014). The eval changing the
system is the point.

**Why authored synthetic data instead of Synthea?** Synthea generates realistic *patient*
records but no payment-integrity defects and no labels, and drags in a Java dependency. An
authored deterministic generator gives full control of the label mix and the near-misses, which
is what makes precision/recall meaningful (005).

**Why FastAPI + SQLite + HTMX?** One developer, short timeline, must demo reliably and reset in
one command. SQLite makes repeatable demos trivial; HTMX gives a real queue/dashboard without a
build step (001). Revisit to Postgres + a JS framework if multi-user concurrency is needed.

**Is the dollars figure real?** No — it's an explicit **estimate** computed from documented
assumptions in `data/roi_assumptions.md` (duplicate = 100% of the redundant line; unbundling =
components − panel, once per group; OON = 35% pricing delta), shown as *Identified* vs
reviewer-*Confirmed* with an "ESTIMATE — not recovered dollars" badge (006). Overstating ROI is
both dishonest and easy to puncture; showing the method is more credible.

**Could the model id or temperature bite you?** The explainer sends only `model`, `max_tokens`,
`system`, `messages` — no `temperature`/`top_p`/`thinking`, which 400 on Opus 4.x, and pinning a
temperature wouldn't make the step deterministic anyway; the recorded `prompt_version` is the
reproducibility anchor (011). Default model `claude-opus-4-8`, overridable via `ANTHROPIC_MODEL`.

**Compliance posture?** Synthetic claims only, no PHI; detection is transparent and offline; the
reviewer UI deliberately hides the ground-truth label so the human isn't handed the answer key;
decisions are append-only labels (004, 012); and on managed machines TLS uses the OS trust store
via `truststore` so verification stays *on* (014).

**Self-check:** for any decision a skeptic names, state the alternative you rejected, the real
number or command, and the honest caveat — without getting defensive.

---

### How to use this doc

Read it once end to end, then drill the **self-checks** at the bottom of each section. You own
the project when you can do all five cold — explain, draw, rebuild, extend, defend — citing real
files, commands, and numbers without opening the repo.

## Mastery checklist
```
- [ ] 1. Explain it in 60 seconds (domain + the anchor property), no notes
- [ ] 2. Draw the architecture from a blank board (stages, splits, external calls, guardrails)
- [ ] 3. Name the modules in build order, state each contract, write the happy path cold
- [ ] 4. List the swap-layer files, say what stays untouched and why
- [ ] 5. Defend any decision a skeptic names — alternative rejected + real numbers + caveats
```
