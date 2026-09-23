"""A SEPARATELY-WRITTEN holdout set — to test the rules, not confirm them.

The demo seed (`app/seed.py`) was authored alongside the rules: its positives are the exact patterns the rules look
for, and its near-misses use exactly the modifiers the rules know. So `make eval` on it returns a perfect 1.00 — which
proves the rules *behave as designed*, not that they *catch what a payer needs caught*.

This holdout is written from the payer's side instead: realistic claim shapes the rules were NOT tuned on, with
ground-truth labels for what a competent integrity system SHOULD flag. It is expected to score BELOW 1.0 — the misses
are the point, and they are published (see EVAL.md and `make holdout`). Different seed, different author's intent; it
reuses only the row *schema* from the seed builder, never its scenarios.

Blind spots probed (each maps to a real-world overpayment pattern):
  - **Date-drift duplicates** — the same service billed on adjacent days. DUP-01 groups by exact date_of_service, so it
    never compares them.
  - **Modifier-59 abuse** — a true duplicate carrying modifier 59 ("distinct service") it does not earn. The rule trusts
    59 unconditionally; unbundling via 59 is the single most-cited abuse pattern in payment integrity.
  - **Partial unbundling** — some, not all, of a panel's components billed separately. UNB-01 requires the *whole*
    panel present, so a partial split escapes.
  - **Cross-date unbundling** — a panel split across adjacent days. Same date-grouping blind spot.
  - **Bilateral (modifier 50)** — a legitimately distinct same-day repeat whose modifier is not in the rule's
    distinct-service set, so the rule flags it (a false positive that tests precision, not just recall).

Run: `make holdout` (python -m app.holdout).
"""
from __future__ import annotations

import random
from datetime import timedelta

from app import eval as evalmod
from app.detect import detect_flags
from app.seed import ANCHOR, Builder

HOLDOUT_SEED = 20260923  # deliberately different from the demo seed


class Holdout(Builder):
    """Reuses Builder's row factory (schema only); its own adversarial scenarios + seed."""

    def __init__(self) -> None:
        super().__init__()
        self.rng = random.Random(HOLDOUT_SEED)
        self.scenario: dict[str, str] = {}  # line_id -> scenario name (for the miss breakdown)

    def _tag(self, row: dict, scenario: str) -> None:
        self.scenario[row["line_id"]] = scenario

    # -- caught-by-design positives (so recall isn't trivially 0) --------------
    def exact_duplicates(self, n: int) -> None:
        for _ in range(n):
            m, p, cpt = self.member(), self.provider(), self.rng.choice(["99214", "80061"])
            dos = self.service_date()
            self._tag(self.line(claim_id=self.next_claim_id(), line_no=1, member=m, provider=p,
                                 cpt=cpt, dos=dos, submitted=dos + timedelta(days=2), label="clean"), "exact_dup")
            self._tag(self.line(claim_id=self.next_claim_id(), line_no=1, member=m, provider=p,
                                 cpt=cpt, dos=dos, submitted=dos + timedelta(days=6), label="duplicate"), "exact_dup")

    def full_unbundle(self, n: int) -> None:
        panels = ["80061", "80053"]
        for i in range(n):
            comps = ["82465", "83718", "84478"] if panels[i % 2] == "80061" else ["82040", "84075", "84450"]
            m, p, dos, cid = self.member(), self.provider(), self.service_date(), self.next_claim_id()
            for ln, c in enumerate(comps, start=1):
                self._tag(self.line(claim_id=cid, line_no=ln, member=m, provider=p, cpt=c, dos=dos,
                                    submitted=dos + timedelta(days=3), label="unbundling"), "full_unbundle")

    def oon(self, n: int) -> None:
        import app.reference as ref
        for _ in range(n):
            dos = self.service_date()
            self._tag(self.line(claim_id=self.next_claim_id(), line_no=1, member=self.member(),
                                provider=self.provider(), cpt=self.rng.choice(["99213", "99214"]), dos=dos,
                                submitted=dos + timedelta(days=4), provider_network=ref.NETWORK_OUT,
                                paid_as=ref.NETWORK_IN, auth_or_emergency=False, label="oon_mismatch"), "oon")

    # -- blind-spot misses (the point of the holdout) --------------------------
    def date_drift_duplicates(self, n: int) -> None:
        for _ in range(n):
            m, p, cpt = self.member(), self.provider(), self.rng.choice(["99214", "99213"])
            dos = self.service_date()
            self._tag(self.line(claim_id=self.next_claim_id(), line_no=1, member=m, provider=p, cpt=cpt,
                                dos=dos, submitted=dos + timedelta(days=2), label="clean"), "date_drift_dup")
            # same service, next day — a real duplicate the exact-date rule can't see
            self._tag(self.line(claim_id=self.next_claim_id(), line_no=1, member=m, provider=p, cpt=cpt,
                                dos=dos + timedelta(days=1), submitted=dos + timedelta(days=3),
                                label="duplicate", is_near_miss=False), "date_drift_dup")

    def modifier_59_abuse(self, n: int) -> None:
        for _ in range(n):
            m, p, cpt = self.member(), self.provider(), self.rng.choice(["99214", "80061"])
            dos = self.service_date()
            self._tag(self.line(claim_id=self.next_claim_id(), line_no=1, member=m, provider=p, cpt=cpt,
                                dos=dos, submitted=dos + timedelta(days=2), label="clean"), "mod59_abuse")
            # identical same-day repeat, but stamped with 59 it doesn't earn -> a true duplicate the rule waves through
            self._tag(self.line(claim_id=self.next_claim_id(), line_no=1, member=m, provider=p, cpt=cpt,
                                dos=dos, submitted=dos + timedelta(days=5), modifiers=["59"],
                                label="duplicate"), "mod59_abuse")

    def partial_unbundle(self, n: int) -> None:
        for _ in range(n):
            comps = ["82465", "83718"]  # 2 of the 3 lipid-panel components (missing 84478)
            m, p, dos, cid = self.member(), self.provider(), self.service_date(), self.next_claim_id()
            for ln, c in enumerate(comps, start=1):
                self._tag(self.line(claim_id=cid, line_no=ln, member=m, provider=p, cpt=c, dos=dos,
                                    submitted=dos + timedelta(days=3), label="unbundling"), "partial_unbundle")

    def cross_date_unbundle(self, n: int) -> None:
        for _ in range(n):
            comps = ["82040", "84075", "84450"]  # full CMP, but split across two days
            m, p, dos, cid = self.member(), self.provider(), self.service_date(), self.next_claim_id()
            for ln, c in enumerate(comps, start=1):
                day = dos if ln < 3 else dos + timedelta(days=1)  # last component drifts a day
                self._tag(self.line(claim_id=cid, line_no=ln, member=m, provider=p, cpt=c, dos=day,
                                    submitted=dos + timedelta(days=3), label="unbundling"), "cross_date_unbundle")

    def bilateral_false_positive(self, n: int) -> None:
        for _ in range(n):
            m, p, cpt = self.member(), self.provider(), "99214"
            dos = self.service_date()
            self._tag(self.line(claim_id=self.next_claim_id(), line_no=1, member=m, provider=p, cpt=cpt,
                                dos=dos, submitted=dos + timedelta(days=2), label="clean"), "bilateral_fp")
            # legitimately distinct bilateral repeat — modifier 50 is NOT in the rule's distinct set, so it fires (FP)
            self._tag(self.line(claim_id=self.next_claim_id(), line_no=1, member=m, provider=p, cpt=cpt,
                                dos=dos, submitted=dos + timedelta(days=5), modifiers=["50"],
                                label="clean", is_near_miss=True), "bilateral_fp")

    def clean(self, n: int) -> None:
        cpts = ["99213", "99214", "80061", "80053"]
        for _ in range(n):
            dos = self.service_date()
            self._tag(self.line(claim_id=self.next_claim_id(), line_no=1, member=self.member(),
                                provider=self.provider(), cpt=self.rng.choice(cpts), dos=dos,
                                submitted=dos + timedelta(days=self.rng.randint(1, 7)), label="clean"), "clean")


def build_rows() -> tuple[list[dict], dict]:
    h = Holdout()
    # caught-by-design (the rules should get these)
    h.exact_duplicates(4)
    h.full_unbundle(3)
    h.oon(4)
    # blind spots (the rules should miss these)
    h.date_drift_duplicates(4)
    h.modifier_59_abuse(3)
    h.partial_unbundle(3)
    h.cross_date_unbundle(2)
    h.bilateral_false_positive(3)
    # base rate of genuinely-clean claims
    h.clean(12)
    return h.rows, h.scenario


def run() -> dict:
    rows, scenario = build_rows()
    flags = detect_flags(rows)
    metrics = evalmod.detector_metrics(rows, flags)
    flagged = {f["claim_line_id"] for f in flags}

    # per-scenario: of the problematic lines in each scenario, how many were caught
    by_scenario: dict[str, dict] = {}
    for r in rows:
        s = scenario[r["line_id"]]
        b = by_scenario.setdefault(s, {"problem": 0, "caught": 0, "clean": 0, "false_pos": 0})
        if r["label"] != "clean":
            b["problem"] += 1
            b["caught"] += int(r["line_id"] in flagged)
        else:
            b["clean"] += 1
            b["false_pos"] += int(r["line_id"] in flagged)
    return {"metrics": metrics, "by_scenario": by_scenario, "n_rows": len(rows)}


def _fmt(m: dict) -> str:
    return f"precision {m['precision']:.2f}  recall {m['recall']:.2f}  F1 {m['f1']:.2f}"


def main() -> None:
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # Windows cp1252 console safety
    except Exception:
        pass
    report = run()
    m = report["metrics"]
    print(f"HOLDOUT — {report['n_rows']} claim lines, separately generated (seed {HOLDOUT_SEED})\n")
    print("DETECTOR (overall)     " + _fmt(m["overall"]))
    for issue in evalmod.ISSUES:
        print(f"  {issue:<20} " + _fmt(m["per_issue"][issue]))
    print(f"  false positives: {m['false_positives']}")
    print(f"  false negatives: {m['false_negatives']}")
    print(f"  near-misses correctly not flagged: "
          f"{m['near_miss_total'] - m['near_miss_flagged']}/{m['near_miss_total']}\n")

    print("By scenario (problematic lines caught / total, and any false positives):")
    order = ["exact_dup", "full_unbundle", "oon", "date_drift_dup", "mod59_abuse",
             "partial_unbundle", "cross_date_unbundle", "bilateral_fp", "clean"]
    for s in order:
        b = report["by_scenario"].get(s)
        if not b:
            continue
        if b["problem"]:
            print(f"  {s:<22} caught {b['caught']}/{b['problem']}")
        elif b["false_pos"]:
            print(f"  {s:<22} FALSE POSITIVES {b['false_pos']}/{b['clean']} clean lines wrongly flagged")
        else:
            print(f"  {s:<22} {b['clean']} clean, {b['false_pos']} wrongly flagged")

    print("\nThe demo seed scores 1.00 because it was authored alongside the rules; this holdout was authored to")
    print("probe cases they were not written for. The misses above are listed in EVAL.md.")


if __name__ == "__main__":
    main()
