#!/usr/bin/env sh
# Container entrypoint. Build the demo data ONCE, then serve with no per-request model calls.
set -e

# If the DB already holds flags (e.g. on a persistent volume), skip the rebuild — re-seeding wipes
# claims -> flags -> cached explanations, so we must not run it over a warm cache.
HAS_DATA=$(python -c "from app.models import connect, init_db; c=connect(); init_db(c); print(c.execute('SELECT COUNT(*) FROM flag').fetchone()[0]); c.close()" 2>/dev/null || echo 0)

if [ "${HAS_DATA:-0}" = "0" ]; then
  echo "[start] empty DB -> seeding + detecting (offline, deterministic)"
  python -m app.seed
  python -m app.detect
  if [ -n "${ANTHROPIC_API_KEY:-}" ]; then
    echo "[start] caching LLM explanations once (idempotent; only missing flags)"
    python -m app.explain || echo "[start] explain failed -> serving rules + triggers without rationales"
  else
    echo "[start] no ANTHROPIC_API_KEY -> serving rules + triggers without LLM rationales"
  fi
else
  echo "[start] existing DB ($HAS_DATA flags) -> serving cached data, no rebuild, no model calls"
fi

exec python -m uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
