FROM python:3.11-slim AS base

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Install CPU-only torch first so `-r requirements.txt` does not pull CUDA wheels.
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -r requirements.txt

# Pre-download embedding model during image build
# This avoids HuggingFace download during container startup.
RUN python -c "\
from sentence_transformers import SentenceTransformer; \
SentenceTransformer('intfloat/multilingual-e5-small') \
"

# Copy only runtime source. The vector index is rebuilt into Postgres at runtime.
COPY alembic/ ./alembic/
COPY alembic.ini ./
COPY app/ ./app/
COPY documents/ ./documents/


# `api` must remain the LAST stage. Render's Docker runtime cannot select a build target
# (no --target flag, no equivalent field in render.yaml) — it always builds whichever stage
# is last in the file. The frontend is not built here at all: it has its own toolchain and
# its own image, web/Dockerfile.
FROM base AS api

EXPOSE 8000
CMD ["python", "-m", "app.run"]