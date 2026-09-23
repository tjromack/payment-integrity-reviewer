# DEPLOY.md — hosting the demo

The point of a hosted instance is a try-it link: a reader clicks and sees the reviewer queue, the flags, the triggering
fields, and the AI rationale — without cloning anything.

## Architecture: detection offline, explanations cached, no key on the host

- **Detection** is deterministic Python over the synthetic seed — no external calls.
- **Explanations** are LLM-generated once, offline, and **shipped as a pre-explained fixture** (`data/demo.db`, tracked
  in the repo). The running app reads them from that DB and makes **no model call** — so the public URL needs **no API
  key** and cannot run up a bill through traffic.

`scripts/start.sh` copies `data/demo.db` into place on first boot and serves it. The seed is fixed, so the demo is the
same known-good state every time.

## Run it locally (Docker)

```bash
docker build -t pir .
docker run -p 8000:8000 pir      # no key, no config
```
Open http://localhost:8000.

## Render (recommended — free, keyless)

1. New **Web Service** → build from this repo (Docker). Render detects the `Dockerfile`.
2. **No environment variables, no disk.** The image already carries the pre-explained demo DB.
3. Deploy. That's it. (Render's free tier spins the service down after inactivity and back up on the next request — a
   ~30s cold start, same as any free demo; fine for a portfolio link.)

**Cost: $0/mo.** No API key on the host, no per-request model calls, no persistent disk.

## Refreshing the demo data

The fixture is generated, not hand-edited. To regenerate it (e.g. after a rules change or a new prompt version):

```bash
make reset                 # re-seed + re-detect  (Windows: python -m app.seed; python -m app.detect)
make explain               # cache fresh rationales   (needs ANTHROPIC_API_KEY in .env, one-time)
cp data/claims.db data/demo.db
git add data/demo.db && git commit -m "Refresh demo fixture"
```
Redeploy and the new state ships.

## If you ever want live explanations instead

Set `ANTHROPIC_API_KEY` as a Render env var and add a **Disk** mounted at `/app/data`. With no committed fixture in
play, `start.sh` builds the DB and caches explanations once on first boot (idempotent), and the disk keeps that cache
across restarts. This trades $0/keyless for the ability to regenerate rationales on the host — unnecessary for a fixed
synthetic demo, but documented for completeness.
