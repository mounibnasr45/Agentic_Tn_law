FROM python:3.11-slim AS base

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Copy runtime source BEFORE the pre-download step below: unlike the old
# sentence-transformers one-liner (which needed nothing from this repo), baking in the
# ONNX weights now imports app.infra.embeddings.onnx_embedder and app.core.config, so
# app/ must exist first. The vector index itself is still rebuilt into Postgres at
# runtime — only the model weights and tokenizer are baked in here.
COPY alembic/ ./alembic/
COPY alembic.ini ./
COPY app/ ./app/
COPY documents/ ./documents/
# eval/ ships because /api/evaluation SERVES baseline.json and golden_set.json — the page
# reads the same artefacts CI gates against, so it cannot drift from the measurement. Two
# small JSON files and a few pure-Python modules; without them the endpoint 503s in the
# container while working perfectly on a developer's machine.
COPY eval/ ./eval/

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


# `api` must remain the LAST stage. Render's Docker runtime cannot select a build target
# (no --target flag, no equivalent field in render.yaml) — it always builds whichever stage
# is last in the file. The frontend is not built here at all: it has its own toolchain and
# its own image, web/Dockerfile.
FROM base AS api

EXPOSE 8000
CMD ["python", "-m", "app.run"]