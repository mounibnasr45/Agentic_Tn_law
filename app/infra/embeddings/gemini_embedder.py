"""Embedder backed by Google's Gemini API — no model resident in this process."""
import asyncio
from collections.abc import Sequence

import numpy as np

from app.core.logging import get_logger

log = get_logger(__name__)

# The API's own analogue of e5's "query: " / "passage: " prefixes: the same text embeds
# differently depending on which side of the retrieval it is on, so query and document
# text must never share an embed_* call.
_QUERY_TASK = "RETRIEVAL_QUERY"
_DOCUMENT_TASK = "RETRIEVAL_DOCUMENT"

# Batches of 100 succeed; ingestion sends 32 (IngestionService.EMBED_BATCH_SIZE) and the
# eval harness can send more, so requests are re-chunked here rather than trusting callers.
_MAX_BATCH = 100

_MAX_ATTEMPTS = 5
_BACKOFF_BASE_SECONDS = 2.0


class GeminiEmbedder:
    def __init__(
        self,
        api_key: str,
        model_name: str = "gemini-embedding-001",
        dimensions: int = 768,
    ) -> None:
        from google import genai

        if not api_key:
            raise ValueError(
                "GEMINI_API_KEY is empty. The Gemini embedding provider cannot start "
                "without it — set it, or set EMBEDDING_PROVIDER=onnx to embed locally."
            )

        self._client = genai.Client(api_key=api_key)
        self._model = model_name
        self._dimensions = dimensions

        # Carries the dimensionality, because 768 and 1536 of the same model are different
        # encoders as far as the index is concerned. ingestion_service.needs_processing()
        # compares this against each Chunk.embedding_model to decide whether a document
        # must be re-embedded; without the suffix, changing output_dimensionality would
        # leave the old vectors in place and mix two geometries in one index.
        self._model_name = f"{model_name}@{dimensions}"

        log.info("embedding_model_loaded", model=self._model_name, provider="gemini")

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimensions(self) -> int:
        return self._dimensions

    @staticmethod
    def _normalise(vectors: np.ndarray) -> np.ndarray:
        norms = np.clip(np.linalg.norm(vectors, axis=1, keepdims=True), a_min=1e-12, a_max=None)
        return (vectors / norms).astype(np.float32)

    async def _embed(self, texts: Sequence[str], task_type: str) -> np.ndarray:
        from google.genai import types

        out: list[list[float]] = []

        for start in range(0, len(texts), _MAX_BATCH):
            batch = list(texts[start : start + _MAX_BATCH])

            for attempt in range(_MAX_ATTEMPTS):
                try:
                    response = await self._client.aio.models.embed_content(
                        model=self._model,
                        contents=batch,
                        config=types.EmbedContentConfig(
                            task_type=task_type,
                            output_dimensionality=self._dimensions,
                        ),
                    )
                    break
                except Exception as exc:  # noqa: BLE001 - retried below, re-raised if fatal
                    # Rate limits and transient upstream failures are the expected case on
                    # a free tier; anything else (bad key, bad model) will exhaust the
                    # attempts and surface, which is correct — a silent empty index is far
                    # worse than a failed ingest.
                    if attempt == _MAX_ATTEMPTS - 1:
                        raise
                    delay = _BACKOFF_BASE_SECONDS * (2**attempt)
                    log.warning(
                        "embedding_request_retry",
                        attempt=attempt + 1,
                        delay_seconds=delay,
                        error=str(exc)[:200],
                    )
                    await asyncio.sleep(delay)

            # A short batch here would misalign embeddings with their chunks — chunk i
            # would be stored with chunk j's vector. Loudly refuse instead.
            if len(response.embeddings) != len(batch):
                raise RuntimeError(
                    f"Gemini returned {len(response.embeddings)} embeddings for "
                    f"{len(batch)} inputs; refusing to index misaligned vectors"
                )

            out.extend(e.values for e in response.embeddings)

        return self._normalise(np.array(out, dtype=np.float32))

    async def embed_query(self, text: str) -> np.ndarray:
        vectors = await self._embed([text], _QUERY_TASK)
        return vectors[0]

    async def embed_documents(self, texts: Sequence[str]) -> np.ndarray:
        if not texts:
            return np.empty((0, self.dimensions))
        return await self._embed(texts, _DOCUMENT_TASK)
