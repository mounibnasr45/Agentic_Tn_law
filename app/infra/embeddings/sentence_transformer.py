"""SentenceTransformer embedder.

ONE model. The old retriever loaded two copies of the same weights — a
SentenceTransformer for its manual cosine path and a HuggingFaceEmbeddings purely to
satisfy Chroma — doubling memory for no benefit (bug 5). Chroma is gone, so the second
copy goes with it.

Encoding is CPU-bound and blocking. Under an async server, calling it directly would
stall the event loop for every other in-flight request, so it is offloaded with
asyncio.to_thread — the same pattern already used correctly in the Whisper project.
"""
import asyncio
from collections.abc import Sequence

import numpy as np

from app.core.logging import get_logger

log = get_logger(__name__)

# Models whose input is a query vs a passage need different prefixes; e5 is the common
# case. Getting this wrong costs several points of recall silently.
E5_QUERY_PREFIX = "query: "
E5_PASSAGE_PREFIX = "passage: "


class SentenceTransformerEmbedder:
    def __init__(self, model_name: str) -> None:
        from sentence_transformers import SentenceTransformer

        self._model_name = model_name
        self._model = SentenceTransformer(model_name)
        self._is_e5 = "e5" in model_name.lower()

        max_tokens = self._model.max_seq_length
        log.info(
            "embedding_model_loaded",
            model=model_name,
            max_seq_length=max_tokens,
            dimensions=self.dimensions,
        )

        # BUG 13. The default encoder (paraphrase-multilingual-MiniLM-L12-v2) accepts
        # 128 tokens, while chunks are sized in CHARACTERS — 700 chars is roughly
        # 200-250 French tokens. Every chunk has therefore been truncated at encode
        # time, and the back half of each one has never been embedded at all. No error,
        # no warning: the model just stops reading. Nobody noticed because there was no
        # eval harness. Now it says so.
        if max_tokens <= 128:
            log.warning(
                "encoder_truncates_chunks",
                model=model_name,
                max_seq_length=max_tokens,
                impact="text beyond this many tokens is silently dropped before encoding",
                remedy="intfloat/multilingual-e5-small (512 tokens, also 384-dim)",
                bug="13",
            )

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimensions(self) -> int:
        # get_sentence_embedding_dimension() is deprecated in sentence-transformers 5.x;
        # get_embedding_dimension() is the replacement. Support both so the app runs on
        # either version rather than warning on every startup.
        getter = getattr(self._model, "get_embedding_dimension", None) or (
            self._model.get_sentence_embedding_dimension
        )
        return int(getter())

    def _encode(self, texts: Sequence[str]) -> np.ndarray:
        # Unit-normalise here so cosine distance in Postgres is well-behaved and the
        # dot product is the cosine similarity.
        return self._model.encode(
            list(texts),
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )

    async def embed_query(self, text: str) -> np.ndarray:
        prefixed = f"{E5_QUERY_PREFIX}{text}" if self._is_e5 else text
        vectors = await asyncio.to_thread(self._encode, [prefixed])
        return vectors[0]

    async def embed_documents(self, texts: Sequence[str]) -> np.ndarray:
        if not texts:
            return np.empty((0, self.dimensions))

        prefixed = [f"{E5_PASSAGE_PREFIX}{t}" for t in texts] if self._is_e5 else list(texts)
        return await asyncio.to_thread(self._encode, prefixed)
