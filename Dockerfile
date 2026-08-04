# ── frontend ─────────────────────────────────────────────────────────────────────────────
# Built here, not just in web/Dockerfile, because the single-container deployment (Hugging
# Face Spaces) serves the SPA from the SAME process as the API — see Settings.static_dir.
# The nginx-fronted topologies (docker compose, render.yaml) ignore the bundle copied
# below: they never set STATIC_DIR, so app/main.py mounts nothing and this is dead weight
# of a few hundred kB.
FROM node:22-alpine AS ui

WORKDIR /ui

# Before the source, so this layer survives every build that does not touch dependencies.
COPY web/package.json web/package-lock.json ./
# `npm ci` not `npm install`: installs exactly the lockfile and fails if it has drifted.
RUN npm ci

COPY web/ ./
RUN npm run build


# ── backend ──────────────────────────────────────────────────────────────────────────────
FROM python:3.11-slim AS base

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    # glibc gives each thread its own 64MB malloc arena by default. Loading the
    # tokenizer and the ONNX session is allocation-heavy across several threads, and
    # freed memory in one arena is never reused by another — so RSS ratchets up well
    # past what is actually live. Capping arenas costs a little allocator contention
    # (this process is I/O-bound, so effectively nothing) and buys headroom on a 512MB
    # instance, where the whole problem is peak RSS during startup.
    MALLOC_ARENA_MAX=2 \
    # Not the default ~/.cache/huggingface, which resolves against $HOME and so differs
    # between the build user and the runtime user. Pinning it under /app — owned by the
    # unprivileged user created below, which is the same user that runs the bake-in step —
    # means the cache written at build time is the cache found at boot. Get this wrong and
    # startup tries to re-download with HF_HUB_OFFLINE=1 set, and fails.
    HF_HOME=/app/.cache/huggingface

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# uid 1000 because Hugging Face Spaces runs every container as that user, and nothing
# else. Created before anything is copied so ownership can be set as files land, via
# COPY --chown: a recursive `chown -R /app` afterwards would instead re-write every file
# into a new layer, duplicating the ~118MB model and the SPA bundle in the image.
RUN useradd --create-home --uid 1000 appuser

# Dependencies install as root into system site-packages — they are read-only at runtime
# and shared, so they neither need nor should have the app user's ownership.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN chown appuser:appuser /app
USER appuser

# Copy runtime source BEFORE the pre-download step below: unlike the old
# sentence-transformers one-liner (which needed nothing from this repo), baking in the
# ONNX weights now imports app.infra.embeddings.onnx_embedder and app.core.config, so
# app/ must exist first. The vector index itself is still rebuilt into Postgres at
# runtime — only the model weights and tokenizer are baked in here.
COPY --chown=appuser:appuser alembic/ ./alembic/
COPY --chown=appuser:appuser alembic.ini ./
COPY --chown=appuser:appuser app/ ./app/
# Writable by the app user on purpose: IngestionService writes uploaded PDFs here.
COPY --chown=appuser:appuser documents/ ./documents/
# eval/ ships because /api/evaluation SERVES baseline.json and golden_set.json — the page
# reads the same artefacts CI gates against, so it cannot drift from the measurement. Two
# small JSON files and a few pure-Python modules; without them the endpoint 503s in the
# container while working perfectly on a developer's machine.
COPY --chown=appuser:appuser eval/ ./eval/

# Pre-download the ONNX weights + tokenizer during image build, at the SAME variant
# EMBEDDING_ONNX_VARIANT selects at runtime (app/core/config.py's default) — this avoids
# a HuggingFace download during container startup, and means a broken tokenizer/session
# fails the BUILD, not a live deploy.
RUN python -c "\
from app.core.config import get_settings; \
from app.infra.embeddings.onnx_embedder import OnnxEmbedder; \
s = get_settings(); \
OnnxEmbedder(s.embedding_model_name, s.embedding_onnx_variant) \
"

# AFTER the bake-in above, never before — this same variable would make that download
# fail. From here on the weights and tokenizer are in the image's HF cache, so runtime
# needs no network: without this, huggingface_hub still issues blocking HEAD requests to
# revalidate the cache on every boot, which is slow and fails hard if the container has
# no egress to huggingface.co.
ENV HF_HUB_OFFLINE=1

# Angular's application builder emits the browser bundle into dist/<project>/browser.
COPY --from=ui --chown=appuser:appuser /ui/dist/agentic-tn-law-web/browser ./web_dist

# Set HERE rather than left to the deployment, because it is a fact about this image: the
# bundle is at that path because the line above put it there. The single-container
# deployment therefore needs no extra configuration, and the nginx-fronted topologies are
# unaffected — nginx serves the SPA itself and only ever forwards /api to this process, so
# the catch-all route this enables is never reached there.
ENV STATIC_DIR=/app/web_dist


# `api` must remain the LAST stage. Render's Docker runtime cannot select a build target
# (no --target flag, no equivalent field in render.yaml) — it always builds whichever
# stage is last in the file.
FROM base AS api

EXPOSE 8000
CMD ["python", "-m", "app.run"]