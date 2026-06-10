"""Synthetic claims generator WITH authored ground-truth labels.

Deterministic (fixed seed) so the demo and the eval are repeatable. Produces one
row per claim line and covers the three target issues — duplicates, unbundling,
out-of-network mismatch — plus clean claims and deliberate near-misses that look
like an issue but are legitimate, so detector precision/recall is actually tested.

Labeling convention (recorded in DECISIONS.md 008):
- A true duplicate is two identical same-day lines; the *earlier* submission is
  the legitimate one (label 'clean') and the *later* redundant line is the
  overpayment (label 'duplicate'). The rules flag the redundant line.
- Each unbundled component line is labeled 'unbundling' (the whole panel was
  improperly split); ROI is computed once per claim group, not per line.
- An OON mismatch is a line from an out-of-network provider adjudicated as
  in-network with no authorization/emergency on file.

No real claims, no PHI. All identifiers, dates, and amounts are invented.
"""
from __future__ import annotations

import json
import random
from datetime import date, timedelta

from app import reference as ref
from app.models import connect, init_db

# Fixed anchor + seed → identical output every run.
SEED = 20260609
ANCHOR = date(2026, 1, 6)  # a Monday; all service dates offset from here
DIAGNOSES = ["E78.5", "I10", "E11.9", "Z00.00", "R73.09"]


class Builder:
    """Accumulates claim-line dicts with running, stable identifiers."""

    def __init__(self) -> None:
        self.rng = random.Random(SEED)
        self.rows: list[dict] = []
        self._claim_seq = 0

    # -- id / value helpers (deterministic via self.rng) ----------------------
    def next_claim_id(self) -> str:
        self._claim_seq += 1
        return f"clm_{self._claim_seq:04d}"

    def member(self) -> str:
        return f"mbr_{self.rng.randint(1000, 9999)}"

    def provider(self) -> tuple[str, str]:
        n = self.rng.randint(100, 999)
        return f"prv_{n}", f"{self.rng.randint(1000000000, 1999999999)}"

    def service_date(self) -> date:
        return ANCHOR + timedelta(days=self.rng.randint(0, 120))

    def dx(self) -> list[str]:
        return self.rng.sample(DIAGNOSES, k=self.rng.randint(1, 2))

    def billed_for(self, cpt: str) -> tuple[float, float]:
        """Return (billed, allowed): billed is a markup over the reference allowed."""
        allowed = ref.CPT_ALLOWED[cpt]
        billed = round(allowed * self.rng.uniform(1.4, 2.2), 2)
        return billed, allowed

    # -- the core row factory -------------------------------------------------
    def line(
        self,
        *,
        claim_id: str,
        line_no: int,
        member: str,
        provider: tuple[str, str],
        cpt: str,
        dos: date,
        submitted: date,
        label: str,
        modifiers: list[str] | None = None,
        provider_network: str = ref.NETWORK_IN,
        paid_as: str | None = None,
        auth_or_emergency: bool = False,
        units: int = 1,
        is_near_miss: bool = False,
    ) -> dict:
        billed, allowed = self.billed_for(cpt)
        prov_id, npi = provider
        row = {
            "claim_id": claim_id,
            "line_id": f"{claim_id}-{line_no}",
            "member_id": member,
            "provider_id": prov_id,
            "provider_npi": npi,
            "provider_network_status": provider_network,
            "paid_as_network": paid_as or provider_network,
            "auth_or_emergency": int(auth_or_emergency),
            "date_of_service": dos.isoformat(),
            "submitted_date": submitted.isoformat(),
            "place_of_service": "11",  # office
            "cpt_code": cpt,
            "modifiers": json.dumps(modifiers or []),
            "units": units,
            "billed_amount": billed,
            "allowed_amount": allowed,
            "diagnosis_codes": json.dumps(self.dx()),
            "label": label,
            "is_near_miss": int(is_near_miss),
            "created_at": submitted.isoformat(),
        }
        self.rows.append(row)
        return row

    # -- scenario generators --------------------------------------------------
    def clean_claims(self, n: int) -> None:
        """Plain, single-line, in-network visits/labs with no issue."""
        cpts = ["99213", "99214", "80061", "80053"]
        for _ in range(n):
            cid = self.next_claim_id()
            dos = self.service_date()
            self.line(
                claim_id=cid, line_no=1, member=self.member(),
                provider=self.provider(), cpt=self.rng.choice(cpts),
                dos=dos, submitted=dos + timedelta(days=self.rng.randint(1, 7)),
                label="clean",
            )

    def duplicates(self, n_positive: int, n_near_miss: int) -> None:
        """Identical same-day lines on two separate claims (different claim_id).

        Positive: later line is the redundant overpayment -> 'duplicate'.
        Near-miss: later line carries a distinct-service modifier -> legitimate.
        """
        cpts = ["99214", "80061", "99213"]
        for i in range(n_positive + n_near_miss):
            near = i >= n_positive
            member, provider = self.member(), self.provider()
            cpt = self.rng.choice(cpts)
            dos = self.service_date()
            # original (legitimate) submission
            c1 = self.next_claim_id()
            self.line(
                claim_id=c1, line_no=1, member=member, provider=provider,
                cpt=cpt, dos=dos, submitted=dos + timedelta(days=2), label="clean",
            )
            # second, same-day, same code submission
            c2 = self.next_claim_id()
            self.line(
                claim_id=c2, line_no=1, member=member, provider=provider,
                cpt=cpt, dos=dos, submitted=dos + timedelta(days=5),
                modifiers=["76"] if near else None,
                label="clean" if near else "duplicate",
                is_near_miss=near,
            )

    def unbundling(self, n_positive: int, n_near_miss: int) -> None:
        """Panel components billed separately on one claim instead of the panel.

        Positive: components with no distinct-service modifier -> 'unbundling'.
        Near-miss: each component carries modifier 59 -> legitimately separate.
        """
        panels = list(ref.BUNDLES.keys())
        for i in range(n_positive + n_near_miss):
            near = i >= n_positive
            panel = panels[i % len(panels)]
            components = ref.BUNDLES[panel]["components"]
            cid = self.next_claim_id()
            member, provider = self.member(), self.provider()
            dos = self.service_date()
            submitted = dos + timedelta(days=3)
            for line_no, comp in enumerate(components, start=1):
                self.line(
                    claim_id=cid, line_no=line_no, member=member, provider=provider,
                    cpt=comp, dos=dos, submitted=submitted,
                    modifiers=["59"] if near else None,
                    label="clean" if near else "unbundling",
                    is_near_miss=near,
                )

    def oon_mismatch(self, n_positive: int, n_near_miss: int, n_clean_oon: int) -> None:
        """Out-of-network provider lines.

        Positive: adjudicated as in-network with no auth/emergency -> mismatch.
        Near-miss: adjudicated as in-network but authorized/emergency -> legit.
        Clean: adjudicated correctly as out-of-network -> no issue.
        """
        cpts = ["99214", "99213", "80053"]
        for _ in range(n_positive):
            cid = self.next_claim_id()
            dos = self.service_date()
            self.line(
                claim_id=cid, line_no=1, member=self.member(), provider=self.provider(),
                cpt=self.rng.choice(cpts), dos=dos, submitted=dos + timedelta(days=4),
                provider_network=ref.NETWORK_OUT, paid_as=ref.NETWORK_IN,
                auth_or_emergency=False, label="oon_mismatch",
            )
        for _ in range(n_near_miss):
            cid = self.next_claim_id()
            dos = self.service_date()
            self.line(
                claim_id=cid, line_no=1, member=self.member(), provider=self.provider(),
                cpt=self.rng.choice(cpts), dos=dos, submitted=dos + timedelta(days=4),
                provider_network=ref.NETWORK_OUT, paid_as=ref.NETWORK_IN,
                auth_or_emergency=True, label="clean", is_near_miss=True,
            )
        for _ in range(n_clean_oon):
            cid = self.next_claim_id()
            dos = self.service_date()
            self.line(
                claim_id=cid, line_no=1, member=self.member(), provider=self.provider(),
                cpt=self.rng.choice(cpts), dos=dos, submitted=dos + timedelta(days=4),
                provider_network=ref.NETWORK_OUT, paid_as=ref.NETWORK_OUT,
                auth_or_emergency=False, label="clean",
            )


def build_rows() -> list[dict]:
    """Assemble the full, deterministic synthetic seed."""
    b = Builder()
    b.clean_claims(30)
    b.duplicates(n_positive=8, n_near_miss=4)
    b.unbundling(n_positive=6, n_near_miss=3)
    b.oon_mismatch(n_positive=8, n_near_miss=4, n_clean_oon=4)
    return b.rows


def _insert(conn, rows: list[dict]) -> None:
    cols = list(rows[0].keys())
    placeholders = ", ".join(f":{c}" for c in cols)
    conn.executemany(
        f"INSERT INTO claim ({', '.join(cols)}) VALUES ({placeholders})", rows
    )
    conn.commit()


def seed() -> dict[str, int]:
    """Create the schema, clear prior data, and load the labeled seed."""
    conn = connect()
    init_db(conn)
    # idempotent: wipe rows + dependent tables so re-seeding is clean
    conn.execute("DELETE FROM decision")
    conn.execute("DELETE FROM flag")
    conn.execute("DELETE FROM claim")
    conn.commit()

    rows = build_rows()
    _insert(conn, rows)

    counts: dict[str, int] = {"total": len(rows), "near_miss": 0}
    for r in rows:
        counts[r["label"]] = counts.get(r["label"], 0) + 1
        counts["near_miss"] += r["is_near_miss"]
    conn.close()
    return counts


def main() -> None:
    counts = seed()
    print(f"Seeded {counts['total']} claim lines into the database.")
    for label in ("clean", "duplicate", "unbundling", "oon_mismatch"):
        print(f"  {label:<14} {counts.get(label, 0)}")
    print(f"  (near-miss      {counts['near_miss']} lines, labeled clean but issue-like)")


if __name__ == "__main__":
    main()
