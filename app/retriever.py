from typing import Any

import numpy as np
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_core.documents import Document
from rank_bm25 import BM25Okapi
from sklearn.metrics.pairwise import cosine_similarity

from app.core.config import get_settings
from app.core.logging import get_logger
from app.domain.scoring import (
    combine_scores,
    normalize_bm25,
    normalize_semantic,
    top_k_indices,
)

log = get_logger(__name__)

# FAISS used to be imported here and _build_faiss_index() lived below, but its only
# call site was commented out and no index file was ever written. Removed, along
# with faiss-cpu from requirements.

# Lazily-loaded, process-wide embedding models, mutated via `global` with no lock —
# two concurrent callers can both enter load_embedding_models() and each load a copy.
# Worse, TWO models are loaded for one job: SentenceTransformer for the manual cosine
# path, and HuggingFaceEmbeddings purely to satisfy Chroma. Both problems die in P2,
# when Chroma is replaced by pgvector and the embedder becomes an injected port.
embedding_function_transformers = None
lc_embedding_function = None


def load_embedding_models():
    global embedding_function_transformers, lc_embedding_function
    settings = get_settings()

    if embedding_function_transformers is None:
        from sentence_transformers import SentenceTransformer

        log.info("loading_embedding_model", model=settings.embedding_model_name)
        embedding_function_transformers = SentenceTransformer(settings.embedding_model_name)

    if lc_embedding_function is None:
        lc_embedding_function = HuggingFaceEmbeddings(model_name=settings.embedding_model_name)

    return embedding_function_transformers, lc_embedding_function


class HybridRetriever:
    def __init__(self, documents: list[Document] | None = None, persist: bool = True):
        load_embedding_models()
        settings = get_settings()

        self.documents: list[Document] = []
        self.document_texts: list[str] = []
        self.document_metadatas: list[dict[str, Any]] = []

        self.bm25: BM25Okapi | None = None
        self.semantic_embeddings: np.ndarray | None = None
        self.chroma_store: Chroma | None = None

        self.chroma_path = str(settings.chroma_db_dir)
        self.is_initialized = False

        if documents:
            self.build_indices(documents, persist=persist)
        elif persist:
            self.load_indices()

    def build_indices(self, documents: list[Document], persist: bool = True) -> None:
        if not documents:
            log.warning("build_indices_called_with_no_documents")
            return

        settings = get_settings()
        settings.chroma_db_dir.mkdir(parents=True, exist_ok=True)

        self.documents = documents
        self.document_texts = [doc.page_content for doc in documents]
        self.document_metadatas = [doc.metadata for doc in documents]

        self.bm25 = BM25Okapi([text.lower().split() for text in self.document_texts])

        self.semantic_embeddings = embedding_function_transformers.encode(
            self.document_texts, convert_to_tensor=False, show_progress_bar=False
        )

        self.chroma_store = Chroma.from_documents(
            documents=self.documents,
            embedding=lc_embedding_function,
            persist_directory=self.chroma_path if persist else None,
        )

        self.is_initialized = True
        log.info("indices_built", chunk_count=len(documents), persisted=persist)

    def load_indices(self) -> None:
        """Load persisted indices.

        BUG 1 LIVES HERE. Only Chroma is persisted — the BM25 index and the semantic
        embedding matrix are in-memory only and never written to disk. So on a cold
        process this restores Chroma, leaves self.documents empty, sets
        is_initialized = True anyway, and search() then silently degrades to
        Chroma-only dense search. The deployed app has never actually run hybrid
        retrieval.

        Fixed properly in P2 (Postgres FTS + pgvector, both durable). Until then the
        degradation is at least loud instead of silent.
        """
        settings = get_settings()
        chroma_dir = settings.chroma_db_dir

        if not (chroma_dir.exists() and any(chroma_dir.iterdir())):
            log.info("no_persisted_indices_found", path=str(chroma_dir))
            self.is_initialized = False
            return

        try:
            self.chroma_store = Chroma(
                persist_directory=self.chroma_path,
                embedding_function=lc_embedding_function,
            )
        except Exception:
            log.exception("chroma_load_failed", path=self.chroma_path)
            self.is_initialized = False
            return

        self.is_initialized = True
        log.warning(
            "retrieval_degraded_to_dense_only",
            reason="BM25 index and embedding matrix are not persisted; only Chroma was restored",
            impact="hybrid search unavailable until the corpus is re-indexed in this process",
            bug="1",
        )

    def search(
        self,
        query: str,
        top_k: int | None = None,
        hybrid_weight_bm25: float | None = None,
    ) -> list[dict[str, Any]]:
        settings = get_settings()
        top_k = settings.top_k_retriever if top_k is None else top_k
        hybrid_weight_bm25 = (
            settings.hybrid_weight_bm25 if hybrid_weight_bm25 is None else hybrid_weight_bm25
        )

        if not self.is_initialized:
            log.warning("search_on_uninitialised_retriever")
            return []

        if not self.documents:
            # See load_indices(): bug 1 surfacing at query time.
            log.warning("falling_back_to_dense_only", bug="1")
            return self.search_chroma_only(query, top_k)

        query_embedding = embedding_function_transformers.encode([query])[0]

        if self.bm25:
            lexical = normalize_bm25(self.bm25.get_scores(query.lower().split()))
        else:
            lexical = np.zeros(len(self.document_texts))

        if self.semantic_embeddings is not None and self.semantic_embeddings.shape[0] > 0:
            dense = normalize_semantic(
                cosine_similarity([query_embedding], self.semantic_embeddings)[0]
            )
        else:
            dense = np.zeros(len(self.document_texts))

        combined = combine_scores(lexical, dense, hybrid_weight_bm25)

        results = [
            {
                "content": self.document_texts[idx],
                "metadata": self.document_metadatas[idx],
                "score": float(combined[idx]),
                "retrieval_type": "hybrid",
            }
            for idx in top_k_indices(combined, top_k)
        ]

        if self.chroma_store:
            try:
                chroma_hits = self.chroma_store.similarity_search_with_relevance_scores(
                    query, k=top_k
                )
                by_content = {r["content"]: r for r in results}
                for doc, score in chroma_hits:
                    by_content.setdefault(
                        doc.page_content,
                        {
                            "content": doc.page_content,
                            "metadata": doc.metadata,
                            "score": score,
                            "retrieval_type": "chroma_semantic",
                        },
                    )
                results = sorted(
                    by_content.values(), key=lambda r: r["score"], reverse=True
                )[:top_k]
            except Exception:
                log.exception("chroma_search_failed")

        log.info("search_complete", result_count=len(results))
        return results

    def search_chroma_only(self, query: str, top_k: int | None = None) -> list[dict[str, Any]]:
        if not self.chroma_store:
            log.warning("chroma_store_unavailable")
            return []

        settings = get_settings()
        top_k = settings.top_k_retriever if top_k is None else top_k

        try:
            hits = self.chroma_store.similarity_search_with_relevance_scores(query, k=top_k)
        except Exception:
            log.exception("chroma_only_search_failed")
            return []

        return [
            {
                "content": doc.page_content,
                "metadata": doc.metadata,
                "score": score,
                "retrieval_type": "chroma_semantic",
            }
            for doc, score in hits
        ]

    def get_langchain_retriever(self):
        settings = get_settings()
        if not self.chroma_store:
            if self.documents:
                temp = Chroma.from_documents(self.documents, lc_embedding_function)
                return temp.as_retriever(search_kwargs={"k": settings.top_k_retriever})
            return None
        return self.chroma_store.as_retriever(search_kwargs={"k": settings.top_k_retriever})
