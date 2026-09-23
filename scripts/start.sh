#!/usr/bin/env sh
# Container entrypoint. Serve the pre-built demo with no per-request model calls.
set -e

# Keyless demo: if there's no live DB yet, seed it from the committed, pre-explained fixture
# (data/demo.db carries the flags AND their cached LLM rationales). No key, no model call.
if [ ! -f data/claims.db ] && [ -f data/demo.db ]; then
  echo "[start] seeding from committed demo.db (pre-explained; no model calls)"
  cp data/demo.db data/claims.db
fi

# Safety net: if there's still no data (fixture missing too), build it offline.
HAS_DATA=$(python -c "from app.models import connect, init_db; c=connect(); init_db(c); print(c.execute('SELECT COUNT(*) FROM flag').fetchone()[0]); c.close()" 2>/dev/null || echo 0)
if [ "${HAS_DATA:-0}" = "0" ]; then
  echo "[start] no data -> building offline (seed + detect)"
  python -m app.seed
  python -m app.detect
  if [ -n "${ANTHROPIC_API_KEY:-}" ]; then
    echo "[start] caching LLM explanations once (idempotent)"
    python -m app.explain || echo "[start] explain failed -> serving without rationales"
  fi
fi

exec python -m uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
