# Payment-Integrity Claims Reviewer — container image.
#
# Detection is deterministic and offline. Explanations are LLM-generated but CACHED: the image
# ships a pre-explained demo DB (data/demo.db), so the running app makes NO model call — and needs
# NO API key. On first boot start.sh copies the fixture into place and serves it. See DEPLOY.md.
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
