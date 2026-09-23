# DEPLOY.md — hosting the demo

The point of a hosted instance is a try-it link: a reader clicks and sees the reviewer queue, the flags, the triggering
fields, and the cached AI rationale — without cloning anything.

## Architecture: detection offline, explanations cached

- **Detection** is deterministic Python over the synthetic seed. It makes no external calls and runs at container boot.
- **Explanations** are LLM-generated but **cached in the SQLite DB**. They are produced once — at first boot, if a key
  is present — and served from that cache. The running app makes **no model call per request**, so a public URL cannot
  run up an API bill through traffic.

`scripts/start.sh` enforces this: it seeds + detects + explains only when the DB has no flags yet, and otherwise serves
the existing data untouched. Put the DB on a **persistent volume** and "once" is once — restarts reuse the cache.

## Run it locally (Docker)

```bash
docker build -t pir .
# with cached explanations (key used once, at boot, then never again):
docker run -p 8000:8000 -e ANTHROPIC_API_KEY=sk-ant-... pir
# or rules-only (no key, no rationales — still a working demo):
docker run -p 8000:8000 pir
```
Open http://localhost:8000.

## Render (like the Suver demo)

1. New **Web Service** → build from this repo (Docker).
2. **Environment:** `ANTHROPIC_API_KEY` (used once at first boot to cache rationales). Render sets `PORT`; the image
   honours it.
3. **Add a Disk** mounted at `/app/data` (1 GB is plenty). This persists `claims.db`, so explanations are generated
   once for the life of the disk — a restart or redeploy reuses the cache and spends nothing.
4. Deploy. First boot runs seed + detect + explain (~34 short calls, one time); every boot after serves from the disk.

**Cost:** the only spend is that one-time explanation pass (~34 short completions). With the disk in place it does not
recur. Without a disk, each cold start regenerates the cache — add the disk to avoid that.

## Alternative: zero key on the host

If you would rather the host never hold a key: run `make explain` locally, copy the resulting `data/claims.db` into
the image at build (drop the `data/*.db` line from `.dockerignore` and `COPY data/claims.db /app/data/claims.db`), and
the container serves fully pre-cached. `start.sh` will see the flags and skip the rebuild.

## 🙋 Manual (Trevor)

- The actual Render deploy (account, env var, disk) is yours to run — the image + this doc are ready.
- Pick the explanation strategy: **key-at-boot + disk** (recommended, above) or **committed pre-explained DB** (zero
  key on host). Say which and I'll wire the `.dockerignore`/`COPY` for the second if you want it.
