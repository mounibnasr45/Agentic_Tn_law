FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# CPU-only torch. `pip install torch` defaults to the CUDA build and drags in ~2GB of
# NVIDIA wheels that can never be used on a CPU-only host. Installing it first, from
# the CPU index, means the requirements.txt resolve below finds torch already
# satisfied. Multi-stage build follows in P7.
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY frontend/ ./frontend/
COPY documents/ ./documents/

EXPOSE 8501
ENV PYTHONUNBUFFERED=1

# Was `COPY . .`, which baked the committed vector_store/ (a stale 39MB Chroma DB)
# into every image. Only source and the corpus are copied now; indices are built at
# runtime, and move to Postgres in P2.
CMD ["streamlit", "run", "frontend/streamlit_app.py", \
     "--server.port=8501", "--server.address=0.0.0.0"]
