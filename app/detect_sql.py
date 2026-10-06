"""The rules, re-expressed in SQL — and the two recall gaps closed.

The Python engine in `app/detect.py` is the reference implementation. This module
expresses the *same* three rules as SQL over the *same* SQLite `claim` table, proves
the two agree (`agreement()` — a bidirectional `EXCEPT`, SQLite's set-based stand-in
for `EXCEPT ALL`; see note below), and then adds two SQL-only rules that close the
holdout gaps named in EVAL.md:

  DUP-01  duplicate        (parity with Python) same member+provider+CPT+date, later
                           submission, no distinct-service modifier.
  UNB-01  unbundling       (parity) a whole panel's components billed separately.
  OON-01  oon_mismatch     (parity) out-of-network paid in-network, no auth/emergency.
  DUP-02  duplicate        (NEW — gap) date-drift: the same service on *adjacent* days.
  UNB-02  unbundling       (NEW — gap) partial unbundling: *some* of a panel's
                           components billed separately.

Why SQL. Payment-integrity edits are written and reviewed as SQL far more often than
as application code; expressing the rules relationally makes them portable to a
warehouse and reviewable by an analyst, and the parity check proves the translation is
faithful rather than merely plausible.

`EXCEPT ALL` note. SQLite has only set-based `EXCEPT` (distinct), not `EXCEPT ALL`.
Every rule emits at most one row per (claim_line_id, rule_id), so a flag set has no
duplicate tuples; bidirectional `EXCEPT` returning no rows, together with equal row
counts, is therefore exactly the `EXCEPT ALL`-both-ways-is-empty guarantee. Both are
asserted (see `agreement()`), on a warehouse that supports it the same check is one
`EXCEPT ALL` each way.

Reference data (the distinct-service modifiers, the panel/component map) is read from
`app/reference.py` so the SQL and the Python rules reason over one source of truth and
can never drift apart. `make sql-dump` renders the live SQL to `sql/` for inspection.
"""

from __future__ import annotations

import sqlite3

from app import reference as ref
from app.detect import RULE_TO_ISSUE, detect_flags
from app.models import SCHEMA, init_db

# Issue mapping for every SQL rule, including the two gap-closers.
SQL_RULE_TO_ISSUE: dict[str, str] = {
    **RULE_TO_ISSUE,
    "DUP-02": "duplicate",
    "UNB-02": "unbundling",
}

# The three rules that have a Python twin — the parity set.
PARITY_RULES = ("DUP-01", "UNB-01", "OON-01")
# The SQL-only additions that close the named holdout gaps.
GAP_RULES = ("DUP-02", "UNB-02")


# --- SQL fragments built from the shared reference data ----------------------
def _modifier_list() -> str:
    """The distinct-service modifier set as a SQL IN-list, from reference.py."""
    return ", ".join(f"'{m}'" for m in sorted(ref.DISTINCT_SERVICE_MODIFIERS))


def _has_distinct_mod(col: str) -> str:
    """A scalar subquery: 1 if the JSON modifier array holds a distinct-service modifier."""
    return (
        f"(SELECT COUNT(*) FROM json_each({col}) "
        f"WHERE value IN ({_modifier_list()}))"
    )


def _bundle_values() -> str:
    """The panel -> component map as SQL VALUES rows, from reference.py BUNDLES."""
    rows = [
        f"('{panel}', '{comp}')"
        for panel, spec in ref.BUNDLES.items()
        for comp in spec["components"]
    ]
    return ", ".join(rows)


# --- the rules in SQL (each returns: claim_line_id, rule_id, confidence) ------
def dup01_sql() -> str:
    """DUP-01 parity: a later same-day repeat of an identical service, no distinct modifier.

    The earliest submission in each (member, provider, CPT, date) group is the
    legitimate one (FIRST_VALUE over the submission order); every later line without a
    distinct-service modifier is the redundant overpayment. Confidence mirrors the
    Python rule: 0.95 when the redundant line matches the original on allowed_amount and
    units, else 0.85.
    """
    return f"""
    WITH g AS (
        SELECT
            line_id, allowed_amount, units,
            {_has_distinct_mod('claim.modifiers')} AS n_distinct,
            ROW_NUMBER()          OVER w AS rn,
            FIRST_VALUE(allowed_amount) OVER w AS orig_allowed,
            FIRST_VALUE(units)          OVER w AS orig_units
        FROM claim
        WINDOW w AS (
            PARTITION BY member_id, provider_id, cpt_code, date_of_service
            ORDER BY submitted_date, line_id
        )
    )
    SELECT
        line_id AS claim_line_id,
        'DUP-01' AS rule_id,
        CASE WHEN allowed_amount = orig_allowed AND units = orig_units
             THEN 0.95 ELSE 0.85 END AS confidence
    FROM g
    WHERE rn > 1 AND n_distinct = 0
    """


def unb01_sql() -> str:
    """UNB-01 parity: a whole panel billed as its separate components, same member/provider/date."""
    return f"""
    WITH comp(panel, component) AS (VALUES {_bundle_values()}),
    psize AS (SELECT panel, COUNT(*) AS n FROM comp GROUP BY panel),
    cl AS (
        SELECT c.line_id, c.member_id, c.provider_id, c.date_of_service, c.cpt_code,
               comp.panel,
               {_has_distinct_mod('c.modifiers')} AS n_distinct
        FROM claim c JOIN comp ON c.cpt_code = comp.component
    ),
    grp AS (
        SELECT member_id, provider_id, date_of_service, panel,
               COUNT(DISTINCT cpt_code) AS distinct_comps,
               SUM(CASE WHEN n_distinct = 0 THEN 1 ELSE 0 END) AS n_nondistinct
        FROM cl
        GROUP BY member_id, provider_id, date_of_service, panel
    )
    SELECT cl.line_id AS claim_line_id, 'UNB-01' AS rule_id, 0.90 AS confidence
    FROM cl
    JOIN grp   USING (member_id, provider_id, date_of_service, panel)
    JOIN psize USING (panel)
    WHERE grp.distinct_comps = psize.n   -- the whole panel is present
      AND grp.n_nondistinct > 0          -- not every component asserts a distinct service
    """


def oon01_sql() -> str:
    """OON-01 parity: out-of-network paid as in-network with no auth/emergency.

    NULL policy (explicit): a NULL `provider_network_status` or `paid_as_network` means
    *unknown*, and an unknown never fires OON-01 — `= 'out'` / `= 'in'` are NULL under
    SQL three-valued logic, so the row is not flagged. Missing network data is a
    data-quality exception to surface upstream, never an accusation of a mispaid claim;
    this matches the precision-first, no-provider-abrasion posture in EVAL.md. (The
    current schema enforces NOT NULL on these columns, so NULLs cannot occur today; the
    rule is written for the real feeds where they can.)
    """
    return """
    SELECT line_id AS claim_line_id, 'OON-01' AS rule_id, 0.92 AS confidence
    FROM claim
    WHERE provider_network_status = 'out'
      AND paid_as_network = 'in'
      AND auth_or_emergency = 0
    """


def dup02_selfjoin_sql() -> str:
    """DUP-02 (gap) date-drift via a SELF-JOIN: the same service on adjacent days.

    DUP-01 groups on an exact `date_of_service`, so a true duplicate billed one day
    later slips through. This flags a line when an earlier-submitted line for the same
    member+provider+CPT sits exactly one day away in service date, and the flagged line
    carries no distinct-service modifier. Confidence 0.80 — a strong but slightly weaker
    signal than an exact same-day repeat.

    Scaling: the self-join is O(k^2) within each (member, provider, CPT) group because
    every candidate pair is tested; clear to read, and flexible (it matches *any* earlier
    line in the window, not just the immediately preceding one). The LAG form below is
    cheaper. See `dup02_lag_sql`.
    """
    return f"""
    SELECT a.line_id AS claim_line_id, 'DUP-02' AS rule_id, 0.80 AS confidence
    FROM claim a
    WHERE {_has_distinct_mod('a.modifiers')} = 0
      AND EXISTS (
          SELECT 1 FROM claim b
          WHERE b.member_id = a.member_id
            AND b.provider_id = a.provider_id
            AND b.cpt_code = a.cpt_code
            AND b.line_id <> a.line_id
            AND ABS(julianday(a.date_of_service) - julianday(b.date_of_service)) = 1
            AND (b.submitted_date < a.submitted_date
                 OR (b.submitted_date = a.submitted_date AND b.line_id < a.line_id))
      )
    """


def dup02_lag_sql() -> str:
    """DUP-02 (gap) date-drift via LAG: same rule, window-function form.

    Orders each (member, provider, CPT) group by submission and compares each line's
    service date to the immediately preceding line's via LAG. One partitioned sort,
    O(n log n) — it scales better than the self-join. It compares only to the immediate
    predecessor, so it coincides with the self-join when adjacent-day duplicates arrive
    as simple pairs (the holdout and seed case, asserted by `dup02_implementations_agree`);
    on 3+-line groups where a match is two rows back, the self-join can catch a pair the
    LAG form misses. For adjacent-day duplicate *pairs* they are identical.
    """
    return f"""
    WITH o AS (
        SELECT line_id, date_of_service, modifiers,
               LAG(date_of_service) OVER w AS prev_dos
        FROM claim
        WINDOW w AS (
            PARTITION BY member_id, provider_id, cpt_code
            ORDER BY submitted_date, line_id
        )
    )
    SELECT line_id AS claim_line_id, 'DUP-02' AS rule_id, 0.80 AS confidence
    FROM o
    WHERE prev_dos IS NOT NULL
      AND ABS(julianday(date_of_service) - julianday(prev_dos)) = 1
      AND {_has_distinct_mod('o.modifiers')} = 0
    """


def unb02_sql() -> str:
    """UNB-02 (gap) partial unbundling: *some* (>=2, not all) of a panel's components.

    UNB-01 requires the whole panel present, so a 2-of-3 split escapes. This fires when
    at least two distinct components of a panel — but fewer than the full set — are
    billed separately on the same member+provider+date with no distinct-service modifier.
    Confidence 0.75: a partial split is real but weaker evidence than a complete panel
    billed as components. As a side effect it catches the same-day portion of a panel
    split across adjacent days (each day looks like a partial panel), which is correct —
    those lines are unbundling too.
    """
    return f"""
    WITH comp(panel, component) AS (VALUES {_bundle_values()}),
    psize AS (SELECT panel, COUNT(*) AS n FROM comp GROUP BY panel),
    cl AS (
        SELECT c.line_id, c.member_id, c.provider_id, c.date_of_service, c.cpt_code,
               comp.panel,
               {_has_distinct_mod('c.modifiers')} AS n_distinct
        FROM claim c JOIN comp ON c.cpt_code = comp.component
    ),
    grp AS (
        SELECT member_id, provider_id, date_of_service, panel,
               COUNT(DISTINCT cpt_code) AS distinct_comps,
               SUM(CASE WHEN n_distinct = 0 THEN 1 ELSE 0 END) AS n_nondistinct
        FROM cl
        GROUP BY member_id, provider_id, date_of_service, panel
    )
    SELECT cl.line_id AS claim_line_id, 'UNB-02' AS rule_id, 0.75 AS confidence
    FROM cl
    JOIN grp   USING (member_id, provider_id, date_of_service, panel)
    JOIN psize USING (panel)
    WHERE grp.distinct_comps >= 2
      AND grp.distinct_comps < psize.n    -- partial, not the whole panel (that is UNB-01)
      AND grp.n_nondistinct > 0
    """


# The parity rule set (DUP-02 uses the LAG form as the canonical implementation).
PARITY_SQL = {"DUP-01": dup01_sql, "UNB-01": unb01_sql, "OON-01": oon01_sql}
GAP_SQL = {"DUP-02": dup02_lag_sql, "UNB-02": unb02_sql}


# --- running the SQL rules ---------------------------------------------------
def run_sql_rules(
    conn: sqlite3.Connection, *, include_gap_closers: bool = False
) -> list[dict]:
    """Run the SQL rule set over `conn`'s claim table; return flag dicts.

    Each flag is {claim_line_id, rule_id, confidence} — the detection decision and its
    rule-derived severity, the fields the parity check compares.
    """
    builders = dict(PARITY_SQL)
    if include_gap_closers:
        builders.update(GAP_SQL)
    flags: list[dict] = []
    for build in builders.values():
        for row in conn.execute(build()):
            flags.append(
                {
                    "claim_line_id": row[0],
                    "rule_id": row[1],
                    "confidence": round(row[2], 2),
                }
            )
    return flags


def rows_to_conn(rows: list[dict], *, relaxed: bool = False) -> sqlite3.Connection:
    """Load claim-line dicts into a fresh in-memory SQLite db and return the connection.

    `relaxed` drops the NOT NULL constraints on the network columns so the OON NULL
    policy can be exercised (the production schema forbids those NULLs).
    """
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    if relaxed:
        conn.executescript(SCHEMA.replace("TEXT NOT NULL", "TEXT"))
    else:
        init_db(conn)
    if rows:
        cols = [c for c in rows[0].keys()]
        placeholders = ", ".join(f":{c}" for c in cols)
        conn.executemany(
            f"INSERT INTO claim ({', '.join(cols)}) VALUES ({placeholders})", rows
        )
    conn.commit()
    return conn


# --- parity: SQL agrees with the Python twin (bidirectional EXCEPT) ----------
def agreement(rows: list[dict]) -> dict:
    """Prove the SQL parity rules equal the Python rules on `rows`, both directions.

    Loads the Python flags and the SQL flags into two temp tables and runs EXCEPT each
    way. Agreement = both differences empty AND equal row counts (together, exactly
    `EXCEPT ALL`-both-ways-empty for single-tuple-per-(line,rule) flag sets).
    """
    conn = rows_to_conn(rows)

    py = [
        {
            "claim_line_id": f["claim_line_id"],
            "rule_id": f["rule_id"],
            "confidence": round(f["confidence"], 2),
        }
        for f in detect_flags([dict(r) for r in rows])
        if f["rule_id"] in PARITY_RULES
    ]
    sql = run_sql_rules(conn, include_gap_closers=False)

    conn.executescript(
        "CREATE TEMP TABLE py (claim_line_id TEXT, rule_id TEXT, confidence REAL);"
        "CREATE TEMP TABLE sq (claim_line_id TEXT, rule_id TEXT, confidence REAL);"
    )
    conn.executemany("INSERT INTO py VALUES (:claim_line_id,:rule_id,:confidence)", py)
    conn.executemany("INSERT INTO sq VALUES (:claim_line_id,:rule_id,:confidence)", sql)

    cols = "claim_line_id, rule_id, confidence"
    py_minus_sql = conn.execute(
        f"SELECT {cols} FROM py EXCEPT SELECT {cols} FROM sq"
    ).fetchall()
    sql_minus_py = conn.execute(
        f"SELECT {cols} FROM sq EXCEPT SELECT {cols} FROM py"
    ).fetchall()
    conn.close()

    return {
        "n_python": len(py),
        "n_sql": len(sql),
        "py_minus_sql": [tuple(r) for r in py_minus_sql],
        "sql_minus_py": [tuple(r) for r in sql_minus_py],
        "agree": not py_minus_sql and not sql_minus_py and len(py) == len(sql),
    }


def dup02_implementations_agree(rows: list[dict]) -> dict:
    """Prove the self-join and LAG forms of DUP-02 return the same flags on `rows`."""
    conn = rows_to_conn(rows)
    sj = {(r[0],) for r in conn.execute(dup02_selfjoin_sql())}
    lg = {(r[0],) for r in conn.execute(dup02_lag_sql())}
    conn.close()
    return {
        "n_selfjoin": len(sj),
        "n_lag": len(lg),
        "selfjoin_minus_lag": sorted(sj - lg),
        "lag_minus_selfjoin": sorted(lg - sj),
        "agree": sj == lg,
    }


# --- scoring in SQL (precision / recall / F1 by conditional aggregation) -----
_SCORE_SQL = """
WITH issues(issue) AS (VALUES ('duplicate'), ('unbundling'), ('oon_mismatch')),
pred AS (SELECT DISTINCT claim_line_id, issue FROM flag_issue),
joined AS (
    SELECT
        i.issue,
        CASE WHEN c.label = i.issue THEN 1 ELSE 0 END AS is_actual,
        CASE WHEN EXISTS (
            SELECT 1 FROM pred p
            WHERE p.claim_line_id = c.line_id AND p.issue = i.issue
        ) THEN 1 ELSE 0 END AS is_pred
    FROM claim c CROSS JOIN issues i
)
SELECT
    issue,
    SUM(CASE WHEN is_actual = 1 AND is_pred = 1 THEN 1 ELSE 0 END) AS tp,
    SUM(CASE WHEN is_actual = 0 AND is_pred = 1 THEN 1 ELSE 0 END) AS fp,
    SUM(CASE WHEN is_actual = 1 AND is_pred = 0 THEN 1 ELSE 0 END) AS fn
FROM joined
GROUP BY issue
"""


def _prf(tp: int, fp: int, fn: int) -> dict:
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "f1": round(f1, 3),
        "tp": tp,
        "fp": fp,
        "fn": fn,
    }


def score_sql(rows: list[dict], *, include_gap_closers: bool = False) -> dict:
    """Per-issue precision/recall/F1 computed in SQL by conditional aggregation."""
    conn = rows_to_conn(rows)
    flags = run_sql_rules(conn, include_gap_closers=include_gap_closers)
    conn.execute("CREATE TEMP TABLE flag_issue (claim_line_id TEXT, issue TEXT)")
    conn.executemany(
        "INSERT INTO flag_issue VALUES (?, ?)",
        [(f["claim_line_id"], SQL_RULE_TO_ISSUE[f["rule_id"]]) for f in flags],
    )
    per_issue = {
        row["issue"]: _prf(row["tp"], row["fp"], row["fn"])
        for row in conn.execute(_SCORE_SQL)
    }
    conn.close()
    return per_issue


# --- rendered-SQL artifact (for review + the SQL drill lab) ------------------
def write_sql_dump(path: str = "sql/payment_integrity_rules.sql") -> str:
    """Render the live SQL (reference data already inlined) to a file for inspection.

    Generated from `app/detect_sql.py` + `app/reference.py`; never hand-edit it — it
    exists so a reviewer (or the SQL drill lab) can read the exact queries the parity
    check runs. Regenerate with `make sql-dump`.
    """
    from pathlib import Path

    blocks = [
        ("DUP-01  duplicate (parity with app/detect.py)", dup01_sql()),
        ("UNB-01  unbundling (parity)", unb01_sql()),
        ("OON-01  oon_mismatch (parity)", oon01_sql()),
        ("DUP-02  date-drift duplicate (gap) — self-join form", dup02_selfjoin_sql()),
        ("DUP-02  date-drift duplicate (gap) — LAG form (canonical)", dup02_lag_sql()),
        ("UNB-02  partial unbundling (gap)", unb02_sql()),
    ]
    header = (
        "-- Payment-Integrity rules, in SQL (SQLite dialect).\n"
        "-- GENERATED by `make sql-dump` from app/detect_sql.py + app/reference.py.\n"
        "-- Do not hand-edit: the reference data (distinct-service modifiers, panel map)\n"
        "-- is the single source of truth, so edit those and regenerate.\n"
        "-- Each query returns: claim_line_id, rule_id, confidence.\n"
    )
    body = "\n".join(f"\n-- {title} --{sql}" for title, sql in blocks)
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(header + body + "\n", encoding="utf-8")
    return str(out)


# --- CLI ---------------------------------------------------------------------
def _fmt(m: dict) -> str:
    return f"precision {m['precision']:.2f}  recall {m['recall']:.2f}  F1 {m['f1']:.2f}"


def main() -> None:
    import sys

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    from app import holdout, seed

    seed_rows = seed.build_rows()
    holdout_rows = holdout.build_rows()[0]

    print("SQL rules vs the Python engine — parity (DUP-01, UNB-01, OON-01)\n")
    for name, rows in (("demo seed", seed_rows), ("holdout", holdout_rows)):
        a = agreement(rows)
        verdict = "AGREE" if a["agree"] else "DIFFER"
        print(
            f"  {name:<10} {a['n_python']} python flags, {a['n_sql']} SQL flags  ->  {verdict}"
        )
        if not a["agree"]:
            print(f"    python-only: {a['py_minus_sql']}")
            print(f"    sql-only:    {a['sql_minus_py']}")

    print("\nDate-drift (DUP-02): self-join vs LAG return the same flags")
    for name, rows in (("demo seed", seed_rows), ("holdout", holdout_rows)):
        d = dup02_implementations_agree(rows)
        print(
            f"  {name:<10} self-join {d['n_selfjoin']}, LAG {d['n_lag']}  ->  "
            f"{'AGREE' if d['agree'] else 'DIFFER'}"
        )

    print("\nHoldout detector — SQL scoring, before vs after closing the two gaps")
    before = score_sql(holdout_rows, include_gap_closers=False)
    after = score_sql(holdout_rows, include_gap_closers=True)
    for issue in ("duplicate", "unbundling", "oon_mismatch"):
        print(f"  {issue:<13} before  {_fmt(before[issue])}")
        print(f"  {issue:<13} after   {_fmt(after[issue])}")
    print(
        "\n  Gaps closed: DUP-02 (date-drift duplicates), UNB-02 (partial unbundling)."
    )
    print(
        "  Still open (documented): modifier-59 abuse, the next-day tail of a cross-date"
    )
    print("  split, and the bilateral (modifier 50) false positive. See EVAL.md.")


if __name__ == "__main__":
    main()
