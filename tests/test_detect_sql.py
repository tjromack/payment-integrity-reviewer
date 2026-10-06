"""The SQL rules are faithful to the Python engine, and the gap-closers help.

Covers the A1 add-on's verification contract:
  - parity: SQL DUP-01/UNB-01/OON-01 equal the Python twins (bidirectional EXCEPT is
    empty) on both the demo seed and the holdout;
  - the two implementations of date-drift (self-join, LAG) return the same flags;
  - SQL scoring (conditional aggregation) reproduces `make holdout`'s per-issue numbers
    for the unchanged rules;
  - the gap-closers raise recall without lowering precision;
  - the OON NULL-network policy: an unknown network status never fires OON-01;
  - DUP-01 and DUP-02 never double-flag the same line.
"""

from __future__ import annotations

from datetime import date

import pytest

from app import eval as evalmod
from app import holdout, seed
from app.detect import detect_flags
from app.detect_sql import (
    agreement,
    dup01_sql,
    dup02_implementations_agree,
    oon01_sql,
    rows_to_conn,
    run_sql_rules,
    score_sql,
)
from app.seed import Builder

ISSUES = ("duplicate", "unbundling", "oon_mismatch")


@pytest.fixture(scope="module")
def seed_rows():
    return seed.build_rows()


@pytest.fixture(scope="module")
def holdout_rows():
    return holdout.build_rows()[0]


# --- parity: SQL == Python ----------------------------------------------------
def test_parity_on_demo_seed(seed_rows):
    a = agreement(seed_rows)
    assert a["agree"], a
    assert a["py_minus_sql"] == [] and a["sql_minus_py"] == []
    assert a["n_python"] == a["n_sql"] > 0


def test_parity_on_holdout(holdout_rows):
    a = agreement(holdout_rows)
    assert a["agree"], a
    assert a["py_minus_sql"] == [] and a["sql_minus_py"] == []


# --- date-drift: two implementations agree -----------------------------------
def test_dup02_selfjoin_equals_lag(seed_rows, holdout_rows):
    for rows in (seed_rows, holdout_rows):
        d = dup02_implementations_agree(rows)
        assert d["agree"], d
    # and the holdout actually exercises it (non-trivial)
    assert dup02_implementations_agree(holdout_rows)["n_lag"] == 4


# --- SQL scoring reproduces the Python holdout numbers for the parity rules ---
def test_sql_scoring_matches_make_holdout(holdout_rows):
    sql = score_sql(holdout_rows, include_gap_closers=False)
    py = evalmod.detector_metrics(
        holdout_rows, [f for f in detect_flags([dict(r) for r in holdout_rows])]
    )["per_issue"]
    for issue in ISSUES:
        for metric in ("precision", "recall", "f1"):
            assert sql[issue][metric] == py[issue][metric], (
                issue,
                metric,
                sql[issue],
                py[issue],
            )


# --- gap-closers raise recall without costing precision ----------------------
def test_gap_closers_raise_recall_holding_precision(holdout_rows):
    before = score_sql(holdout_rows, include_gap_closers=False)
    after = score_sql(holdout_rows, include_gap_closers=True)
    for issue in ("duplicate", "unbundling"):
        assert after[issue]["recall"] > before[issue]["recall"], issue
        assert after[issue]["precision"] >= before[issue]["precision"], issue
    # oon is untouched by the gap-closers
    assert after["oon_mismatch"] == before["oon_mismatch"]
    # the specific published lift
    assert after["duplicate"]["recall"] == pytest.approx(0.727, abs=0.001)
    assert after["unbundling"]["recall"] == pytest.approx(0.905, abs=0.001)


# --- OON NULL-network policy: unknown never fires ----------------------------
def test_oon_null_network_status_not_flagged():
    b = Builder()
    common = dict(
        line_no=1,
        member="mbr_1",
        provider=("prv_1", "1000000001"),
        cpt="99213",
        dos=date(2026, 1, 6),
        submitted=date(2026, 1, 10),
        label="oon_mismatch",
    )
    valid = b.line(
        claim_id="clm_a",
        provider_network="out",
        paid_as="in",
        auth_or_emergency=False,
        **common,
    )
    null_net = b.line(
        claim_id="clm_b",
        provider_network="out",
        paid_as="in",
        auth_or_emergency=False,
        **common,
    )
    null_paid = b.line(
        claim_id="clm_c",
        provider_network="out",
        paid_as="in",
        auth_or_emergency=False,
        **common,
    )
    null_net["provider_network_status"] = None  # unknown network status
    null_paid["paid_as_network"] = None  # unknown adjudicated network

    conn = rows_to_conn([valid, null_net, null_paid], relaxed=True)
    flagged = {r[0] for r in conn.execute(oon01_sql())}
    conn.close()
    assert flagged == {valid["line_id"]}  # only the fully-known mismatch fires


# --- DUP-01 and DUP-02 are disjoint (no double-flag) -------------------------
def test_dup01_and_dup02_never_double_flag(holdout_rows):
    conn = rows_to_conn(holdout_rows)
    dup01 = {r[0] for r in conn.execute(dup01_sql())}
    from app.detect_sql import dup02_lag_sql

    dup02 = {r[0] for r in conn.execute(dup02_lag_sql())}
    conn.close()
    assert dup01.isdisjoint(dup02), dup01 & dup02


# --- the full SQL rule set stays one-flag-per-line-per-rule (EXCEPT ALL basis) -
def test_one_flag_per_line_per_rule(holdout_rows):
    conn = rows_to_conn(holdout_rows)
    flags = run_sql_rules(conn, include_gap_closers=True)
    conn.close()
    keys = [(f["claim_line_id"], f["rule_id"]) for f in flags]
    assert len(keys) == len(
        set(keys)
    )  # no duplicate tuples -> EXCEPT == EXCEPT ALL here
