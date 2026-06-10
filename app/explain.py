"""LLM explanation layer — the LLM EXPLAINS, it never DECIDES.

Given a flag the rules already produced (rule id + the exact triggering fields),
this generates a short, plain-English rationale for a reviewer, grounded strictly
in those inputs. It cannot flag, clear, re-rank, or recommend an outcome, and it
must not introduce any reason not present in the rule + fields (CLAUDE.md §3, 7).

The model + prompt version are recorded with every explanation so each one is
reproducible and auditable (EVAL.md). Detection never reads anything written here.
"""
from __future__ import annotations

import json
import os

from app.models import connect, init_db

# Bump when the prompt changes so explanations stay traceable to how they were made.
PROMPT_VERSION = "explain-v1"
DEFAULT_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-opus-4-8")
MAX_TOKENS = 300

# Plain-language description of what each rule checks. This is the ONLY rule
# context the model gets — it grounds the explanation without leaking new reasons.
RULE_DESCRIPTIONS = {
    "DUP-01": (
        "Duplicate: the same service was submitted more than once for the same "
        "member, provider, CPT code, and date of service. This line is a later, "
        "redundant submission of an earlier claim, and it carries no distinct-"
        "service modifier (such as 76 or 59) that would make it separately payable."
    ),
    "UNB-01": (
        "Unbundling: the individual component codes of a single comprehensive "
        "panel were billed separately on the same date for the same member and "
        "provider, instead of the one comprehensive panel code, and without a "
        "distinct-service modifier that would justify billing them apart."
    ),
    "OON-01": (
        "Out-of-network mismatch: the rendering provider is out-of-network, but "
        "the line was adjudicated as in-network, and there is no authorization or "
        "emergency on file that would justify in-network handling."
    ),
}

SYSTEM_PROMPT = """You write a short, plain-English rationale that explains to a \
claims reviewer WHY a payment-integrity rule flagged a claim line. You are an \
explainer, not a decision-maker.

Strict rules:
- Use ONLY the rule description and the triggering field values you are given. \
Every statement must be supported by them.
- Do NOT introduce any reason, fact, code, amount, date, or assumption that is \
not present in the provided inputs.
- Do NOT judge or recommend an outcome. Never say the claim should be paid, \
denied, approved, dismissed, or recovered, and do not assert it is definitely \
fraud or an error. You explain why the rule fired; a human decides what to do.
- Refer to the concrete triggering values (ids, codes, dates, amounts) so the \
reviewer can see the basis for the flag.
- 1-3 sentences. Neutral, factual tone. Output only the rationale text, with no \
preamble, headings, or labels."""


def build_messages(flag: dict) -> tuple[str, str]:
    """Return (system, user_text) for a flag row. Pure — no network."""
    rule_id = flag["rule_id"]
    description = RULE_DESCRIPTIONS.get(rule_id, rule_id)
    triggering = flag["triggering_fields"]
    if isinstance(triggering, str):
        triggering = json.loads(triggering)
    pretty = json.dumps(triggering, indent=2)
    user_text = (
        f"RULE THAT FIRED: {rule_id} — {description}\n\n"
        f"TRIGGERING FIELDS (the exact claim values that caused the rule to fire):\n"
        f"{pretty}\n\n"
        "Write the rationale now."
    )
    return SYSTEM_PROMPT, user_text


def _client():
    """Construct the Anthropic client, loading .env first. Raises if no key."""
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:  # python-dotenv optional at runtime
        pass
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Copy .env.example to .env and add your "
            "key. Detection runs without it; only explanations need the API."
        )
    import anthropic

    return anthropic.Anthropic()


def explain_flag(flag: dict, client=None, model: str = DEFAULT_MODEL) -> dict:
    """Generate one rationale. Returns explanation + model + prompt version.

    `client` is injectable for testing. Note: no temperature / thinking params —
    they are unsupported on Opus 4.x and would 400.
    """
    if client is None:
        client = _client()
    system, user_text = build_messages(flag)
    resp = client.messages.create(
        model=model,
        max_tokens=MAX_TOKENS,
        system=system,
        messages=[{"role": "user", "content": user_text}],
    )
    text = next((b.text for b in resp.content if b.type == "text"), "").strip()
    return {
        "explanation": text,
        "explanation_model": getattr(resp, "model", model),
        "explanation_prompt_version": PROMPT_VERSION,
    }


# --- deterministic grounding check (reused/extended by the eval in Phase 5) ----
def referenced_values(explanation: str, triggering: dict) -> list[str]:
    """Triggering field values that literally appear in the explanation text."""
    found = []
    for value in triggering.values():
        if isinstance(value, (list, dict)):
            continue
        s = str(value)
        if s and s.lower() in explanation.lower():
            found.append(s)
    return found


def is_grounded(explanation: str, rule_id: str, triggering: dict) -> bool:
    """True if the explanation names the rule/issue and cites a triggering value."""
    text = explanation.lower()
    issue_word = {"DUP-01": "duplicat", "UNB-01": "unbundl", "OON-01": "network"}
    mentions_rule = rule_id.lower() in text or issue_word.get(rule_id, "") in text
    return bool(explanation) and mentions_rule and bool(referenced_values(explanation, triggering))


# --- persistence -------------------------------------------------------------
def _save(conn, flag_id: int, result: dict) -> None:
    conn.execute(
        """UPDATE flag SET explanation = :explanation,
               explanation_model = :explanation_model,
               explanation_prompt_version = :explanation_prompt_version
           WHERE id = :id""",
        {**result, "id": flag_id},
    )


def explain_all(only_missing: bool = True, limit: int | None = None) -> dict[str, int]:
    """Generate and persist explanations for flags. Idempotent on missing ones."""
    conn = connect()
    init_db(conn)
    where = "WHERE explanation IS NULL" if only_missing else ""
    rows = [dict(r) for r in conn.execute(f"SELECT * FROM flag {where} ORDER BY id")]
    if limit is not None:
        rows = rows[:limit]

    client = _client()
    done = 0
    for flag in rows:
        result = explain_flag(flag, client=client)
        _save(conn, flag["id"], result)
        conn.commit()
        done += 1
    conn.close()
    return {"explained": done, "considered": len(rows)}


def main() -> None:
    try:
        counts = explain_all(only_missing=True)
    except RuntimeError as e:
        print(f"Skipped: {e}")
        return
    print(f"Explained {counts['explained']} flag(s) ({DEFAULT_MODEL}, prompt {PROMPT_VERSION}).")


if __name__ == "__main__":
    main()
