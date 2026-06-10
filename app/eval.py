"""Evaluation harness (EVAL.md).

Two questions: is the detector any good, and are the LLM explanations faithful to
why a claim was flagged? Detection metrics are computed against the authored
ground-truth labels with no LLM involved. Faithfulness uses a deterministic
grounding check plus an LLM-as-judge for the "no invented reasons" part, with a
versioned rubric; the judge model + rubric version are recorded with the run.

Run: `make eval` (python -m app.eval).
"""
from __future__ import annotations

import json
import os

from app import explain
from app.detect import RULE_TO_ISSUE
from app.models import connect, init_db

ISSUES = ("duplicate", "unbundling", "oon_mismatch")

# Thresholds from EVAL.md (precision/recall are reported honestly, not gated hard).
FAITHFULNESS_MIN = 0.95
PRECISION_TARGET = 0.85

RUBRIC_VERSION = "faithful-judge-v1"
JUDGE_SYSTEM = (
    "You are given the RULE that fired, the TRIGGERING FIELDS, and an EXPLANATION. "
    "Score faithful=1 only if the explanation is fully supported by the rule and "
    "fields and adds no new reason; faithful=0 otherwise. Judge only against the "
    "rule and fields provided; use no outside knowledge. "
    'Output strict JSON: {"faithful": 0 or 1, "issues": [..]}.'
)
JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "faithful": {"type": "integer", "enum": [0, 1]},
        "issues": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["faithful", "issues"],
    "additionalProperties": False,
}


# --- detection metrics (pure, no LLM) ----------------------------------------
def prf(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return round(precision, 3), round(recall, 3), round(f1, 3)


def detector_metrics(claims: list[dict], flags: list[dict]) -> dict:
    """Precision/recall/F1 overall (problematic vs clean) and per issue type."""
    gt = {c["line_id"]: c["label"] for c in claims}
    predicted: dict[str, set[str]] = {}
    for f in flags:
        issue = RULE_TO_ISSUE.get(f["rule_id"])
        predicted.setdefault(f["claim_line_id"], set()).add(issue)

    # Overall: any flag vs any non-clean label.
    pred_pos = set(predicted)
    gt_pos = {lid for lid, label in gt.items() if label != "clean"}
    tp, fp, fn = pred_pos & gt_pos, pred_pos - gt_pos, gt_pos - pred_pos
    overall = dict(zip(("precision", "recall", "f1"), prf(len(tp), len(fp), len(fn))))

    per_issue = {}
    for issue in ISSUES:
        i_tp = sum(1 for lid, lab in gt.items() if lab == issue and issue in predicted.get(lid, set()))
        i_fp = sum(1 for lid, iss in predicted.items() if issue in iss and gt.get(lid) != issue)
        i_fn = sum(1 for lid, lab in gt.items() if lab == issue and issue not in predicted.get(lid, set()))
        per_issue[issue] = dict(zip(("precision", "recall", "f1"), prf(i_tp, i_fp, i_fn)))

    near_miss_total = sum(1 for c in claims if c["is_near_miss"])
    near_miss_flagged = sum(1 for c in claims if c["is_near_miss"] and c["line_id"] in predicted)
    return {
        "overall": overall,
        "per_issue": per_issue,
        "false_positives": sorted(fp),
        "false_negatives": sorted(fn),
        "near_miss_total": near_miss_total,
        "near_miss_flagged": near_miss_flagged,
    }


# --- explanation faithfulness ------------------------------------------------
def judge_faithful(flag: dict, explanation: str, client, model: str) -> dict:
    """LLM-as-judge for the 'no invented reasons' check. Returns {faithful, issues}."""
    rule_id = flag["rule_id"]
    triggering = flag["triggering_fields"]
    if isinstance(triggering, str):
        triggering = json.loads(triggering)
    user = (
        f"RULE: {rule_id} — {explain.RULE_DESCRIPTIONS.get(rule_id, rule_id)}\n\n"
        f"TRIGGERING FIELDS:\n{json.dumps(triggering, indent=2)}\n\n"
        f"EXPLANATION:\n{explanation}"
    )
    resp = client.messages.create(
        model=model,
        max_tokens=300,
        system=JUDGE_SYSTEM,
        messages=[{"role": "user", "content": user}],
        output_config={"format": {"type": "json_schema", "schema": JUDGE_SCHEMA}},
    )
    text = next((b.text for b in resp.content if b.type == "text"), "{}")
    return json.loads(text)


def faithfulness_metrics(flags: list[dict], client=None, model: str | None = None) -> dict:
    """Score explanations: deterministic grounding + optional LLM-judge."""
    explained = [f for f in flags if f.get("explanation")]
    if not explained:
        return {"status": "no_explanations", "count": 0}

    model = model or explain.DEFAULT_MODEL
    results = []
    for f in explained:
        triggering = json.loads(f["triggering_fields"])
        grounded = explain.is_grounded(f["explanation"], f["rule_id"], triggering)
        verdict = {"line_id": f["claim_line_id"], "grounded": grounded, "issues": []}
        if not grounded:
            verdict["issues"].append("does not reference the rule and a triggering field")
        if client is not None:
            j = judge_faithful(f, f["explanation"], client, model)
            verdict["judge_faithful"] = bool(j.get("faithful", 0))
            verdict["issues"] += j.get("issues", [])
        # Faithful = grounded AND (judge says faithful, when a judge ran).
        verdict["faithful"] = grounded and verdict.get("judge_faithful", True)
        results.append(verdict)

    faithful = sum(1 for r in results if r["faithful"])
    return {
        "status": "ok",
        "count": len(results),
        "faithful": faithful,
        "score": round(faithful / len(results), 3),
        "judged_by_llm": client is not None,
        "judge_model": model if client is not None else None,
        "rubric_version": RUBRIC_VERSION,
        "unfaithful": [r for r in results if not r["faithful"]],
    }


# --- runner ------------------------------------------------------------------
def _maybe_client():
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass
    if not os.getenv("ANTHROPIC_API_KEY"):
        return None
    import anthropic

    return anthropic.Anthropic()


def run() -> dict:
    conn = connect()
    init_db(conn)
    claims = [dict(r) for r in conn.execute("SELECT * FROM claim")]
    flags = [dict(r) for r in conn.execute("SELECT * FROM flag")]
    conn.close()
    detection = detector_metrics(claims, flags)
    faithfulness = faithfulness_metrics(flags, client=_maybe_client())
    return {"detection": detection, "faithfulness": faithfulness}


def _fmt(m: dict) -> str:
    return f"precision {m['precision']:.2f}  recall {m['recall']:.2f}  F1 {m['f1']:.2f}"


def main() -> None:
    report = run()
    d = report["detection"]
    print("DETECTOR (overall)     " + _fmt(d["overall"]))
    for issue in ISSUES:
        print(f"  {issue:<20} " + _fmt(d["per_issue"][issue]))
    print(f"  false positives: {d['false_positives']}")
    print(f"  false negatives: {d['false_negatives']}")
    print(
        f"  near-misses correctly not flagged: "
        f"{d['near_miss_total'] - d['near_miss_flagged']}/{d['near_miss_total']}"
    )

    print()
    fa = report["faithfulness"]
    if fa["status"] == "no_explanations":
        print("EXPLANATION FAITHFULNESS   n/a - no explanations generated. Run `make explain`.")
    else:
        judge = f"LLM-judged by {fa['judge_model']}, rubric {fa['rubric_version']}" if fa[
            "judged_by_llm"
        ] else "deterministic grounding only (no API key; LLM judge skipped)"
        print(
            f"EXPLANATION FAITHFULNESS   {fa['score']:.2f}  "
            f"({fa['faithful']}/{fa['count']} faithful - {judge})"
        )
        for u in fa["unfaithful"]:
            print(f"  unfaithful {u['line_id']}: {'; '.join(u['issues']) or 'failed check'}")

    print()
    print("Thresholds (EVAL.md): "
          f"faithfulness >= {FAITHFULNESS_MIN:.2f}, precision >= {PRECISION_TARGET:.2f}; "
          "recall reported honestly. Synthetic seed - shows rules behave as designed.")


if __name__ == "__main__":
    main()
