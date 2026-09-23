# Payment-Integrity Claims Reviewer — container image.
#
# Detection is deterministic and offline. Explanations are LLM-generated but CACHED in the SQLite
# DB: they are produced once (at first boot, if a key is present) and served from cache thereafter,
# so the running app makes NO model call per request. Mount the DB on a persistent volume
# (see DEPLOY.md) and that "once" is truly once — restarts reuse the cache.
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
RUN chmod +x scripts/start.sh

ENV PORT=8000
EXPOSE 8000
CMD ["scripts/start.sh"]
