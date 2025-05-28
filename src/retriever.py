import os
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer
from rank_bm25 import BM25Okapi
from sklearn.metrics.pairwise import cosine_similarity
from langchain_community.vectorstores import Chroma
from langchain_core.documents import Document
from langchain_community.embeddings import HuggingFaceEmbeddings
from typing import List, Dict, Any

import config

# Initialize embedding model globally (or pass as argument)
print("Loading embedding model for retriever...")
embedding_function_transformers = SentenceTransformer(config.EMBEDDING_MODEL_NAME)
# Langchain compatible embedding function
lc_embedding_function = HuggingFaceEmbeddings(model_name=config.EMBEDDING_MODEL_NAME)
print("Embedding model loaded.")


class HybridRetriever:
    def __init__(self, documents: List[Document] = None, persist: bool = True):
        self.documents: List[Document] = []
        self.document_texts: List[str] = []
        self.document_metadatas: List[Dict[str, Any]] = []
        
        self.bm25: BM25Okapi = None
        self.semantic_embeddings: np.ndarray = None
        self.faiss_index: faiss.Index = None # Optional FAISS
        self.chroma_store: Chroma = None

        self.chroma_path = config.CHROMA_DB_DIR
        self.faiss_index_path = config.FAISS_INDEX_PATH # Optional

        self.is_initialized = False

        if documents:
            self.build_indices(documents, persist=persist)
        elif persist: # Try to load if persist is True and no documents given
            self.load_indices()


    def _check_and_create_dirs(self):
        os.makedirs(self.chroma_path, exist_ok=True)
        if self.faiss_index_path:
            os.makedirs(os.path.dirname(self.faiss_index_path), exist_ok=True)

    def build_indices(self, documents: List[Document], persist: bool = True):
        if not documents:
            print("No documents provided to build indices.")
            return

        self._check_and_create_dirs()
        self.documents = documents
        self.document_texts = [doc.page_content for doc in documents]
        self.document_metadatas = [doc.metadata for doc in documents]

        print("Building BM25 index...")
        tokenized_corpus = [text.lower().split() for text in self.document_texts]
        self.bm25 = BM25Okapi(tokenized_corpus)

        print("Encoding document embeddings for semantic search...")
        self.semantic_embeddings = embedding_function_transformers.encode(
            self.document_texts, convert_to_tensor=False, show_progress_bar=True
        ) # convert_to_numpy=True is default

        # Optional: FAISS Index (can be large, Chroma might be enough)
        # self._build_faiss_index(persist)

        print("Building Chroma vectorstore...")
        self.chroma_store = Chroma.from_documents(
            documents=self.documents,
            embedding=lc_embedding_function, # Use LangChain compatible embeddings
            persist_directory=self.chroma_path if persist else None
        )
        if persist:
            self.chroma_store.persist()
            print(f"Chroma vectorstore persisted to {self.chroma_path}")
        
        self.is_initialized = True
        print("HybridRetriever initialized and indices built.")

    def _build_faiss_index(self, persist: bool = True):
        if self.semantic_embeddings is None or self.semantic_embeddings.shape[0] == 0:
            print("No embeddings to build FAISS index.")
            return
        print("Building FAISS index...")
        d = self.semantic_embeddings.shape[1]
        self.faiss_index = faiss.IndexFlatL2(d)
        self.faiss_index.add(self.semantic_embeddings)
        if persist and self.faiss_index_path:
            faiss.write_index(self.faiss_index, self.faiss_index_path)
            print(f"FAISS index saved to {self.faiss_index_path}")

    def load_indices(self):
        self._check_and_create_dirs()
        loaded_something = False
        # Chroma is primary, so it must load.
        # We need document texts for BM25 and manual semantic if Chroma fails or for metadata.
        # This part is tricky: Chroma stores docs, but BM25 and manual semantic need texts/embeddings separately.
        # For simplicity, if Chroma loads, we assume it's the source of truth for documents.
        # If not, this retriever won't work without rebuilding.
        
        print(f"Attempting to load Chroma vectorstore from {self.chroma_path}...")
        if os.path.exists(self.chroma_path) and os.listdir(self.chroma_path):
            try:
                self.chroma_store = Chroma(
                    persist_directory=self.chroma_path,
                    embedding_function=lc_embedding_function
                )
                # To re-populate self.documents, self.document_texts, self.document_metadatas
                # This can be slow for large stores.
                # A more efficient way would be to save/load these separately.
                # For now, we'll rely on Chroma's get() or similarity search.
                # Let's assume if Chroma is loaded, it's the main retriever.
                # The hybrid search below uses self.document_texts, so we need them.
                # A better approach: Store document texts and metadata alongside indices or retrieve from Chroma.
                # For now, let's require rebuilding if these are not available or create a simplified load.
                print("Chroma vectorstore loaded.")
                
                # Try to get all documents from Chroma to rebuild other indices (less efficient)
                # This is not ideal. Better to save/load these components separately or rely fully on Chroma's retriever.
                # For hybrid search to work as originally designed, we need self.document_texts etc.
                # Simplification: if loading, only Chroma is used unless we also save/load BM25 and embeddings.
                # For now, let's make loading just load Chroma. The hybrid search might not work as intended without a rebuild.
                
                # A better load would involve saving/loading self.documents, self.bm25, self.semantic_embeddings
                # For now, if Chroma loads, we set is_initialized. The search might need adjustment
                # if only Chroma is available after loading.
                
                # To fully enable hybrid search on load, you'd need to persist and load:
                # 1. self.documents (or at least texts and metadatas)
                # 2. self.bm25 object (can be pickled)
                # 3. self.semantic_embeddings (numpy save/load)
                # This makes loading more complex.
                # Current load focuses on Chroma.
                
                self.is_initialized = True # Assume Chroma is enough for basic retrieval
                loaded_something = True
                print("Chroma loaded. For full hybrid search capabilities, ensure BM25 and semantic embeddings are also available or rebuild.")

            except Exception as e:
                print(f"Could not load Chroma: {e}. Indices may need to be rebuilt.")
        else:
            print(f"Chroma persistence directory not found or empty at {self.chroma_path}.")

        # Optional: Load FAISS
        # if self.faiss_index_path and os.path.exists(self.faiss_index_path):
        #     print(f"Loading FAISS index from {self.faiss_index_path}...")
        #     self.faiss_index = faiss.read_index(self.faiss_index_path)
        #     loaded_something = True
        #     print("FAISS index loaded.")

        if loaded_something:
            print("Retriever loaded existing components.")
        else:
            print("No existing indices found or loaded. Retriever needs to be built with documents.")
        self.is_initialized = loaded_something


    def search(self, query: str, top_k: int = config.TOP_K_RETRIEVER, hybrid_weight_bm25: float = config.HYBRID_WEIGHT_BM25) -> List[Dict[str, Any]]:
        if not self.is_initialized:
            print("Retriever not initialized. Please build or load indices.")
            return []
        
        if not self.documents: # This means we loaded only Chroma and didn't re-populate self.documents
            print("Documents not populated in retriever, falling back to Chroma-only search.")
            return self.search_chroma_only(query, top_k)

        print(f"Performing hybrid search for query: '{query}'")
        query_embedding = embedding_function_transformers.encode([query])[0]

        # BM25 retrieval
        tokenized_query = query.lower().split()
        if self.bm25:
            bm25_scores = self.bm25.get_scores(tokenized_query)
            # Normalize BM25 scores (0 to 1)
            min_bm25, max_bm25 = np.min(bm25_scores), np.max(bm25_scores)
            if max_bm25 == min_bm25: # Avoid division by zero if all scores are same
                 normalized_bm25_scores = np.zeros_like(bm25_scores) if max_bm25 == 0 else np.ones_like(bm25_scores)
            else:
                normalized_bm25_scores = (bm25_scores - min_bm25) / (max_bm25 - min_bm25)
        else:
            print("BM25 index not available for hybrid search.")
            normalized_bm25_scores = np.zeros(len(self.document_texts))


        # Semantic retrieval (cosine similarity with pre-computed embeddings)
        if self.semantic_embeddings is not None and self.semantic_embeddings.shape[0] > 0:
            semantic_scores = cosine_similarity([query_embedding], self.semantic_embeddings)[0]
            # Cosine similarity is already in a good range (-1 to 1, typically 0 to 1 for positive correlations)
            # We can scale it to 0-1 if needed: (semantic_scores + 1) / 2
            # For simplicity, let's assume they are mostly positive and use as is or clip.
            normalized_semantic_scores = np.clip(semantic_scores, 0, 1)
        else:
            print("Semantic embeddings not available for hybrid search.")
            normalized_semantic_scores = np.zeros(len(self.document_texts))

        # Combine scores
        # Weight for semantic is (1 - hybrid_weight_bm25)
        hybrid_weight_semantic = 1.0 - hybrid_weight_bm25
        combined_scores = (hybrid_weight_bm25 * normalized_bm25_scores +
                           hybrid_weight_semantic * normalized_semantic_scores)

        # Get top-k indices and scores from combined scores
        # Ensure we don't request more items than available
        actual_top_k_hybrid = min(top_k, len(self.document_texts))
        if actual_top_k_hybrid == 0:
            results = []
        else:
            top_indices_hybrid = np.argsort(combined_scores)[-actual_top_k_hybrid:][::-1]
            results = [{
                "content": self.document_texts[idx],
                "metadata": self.document_metadatas[idx],
                "score": float(combined_scores[idx]),
                "retrieval_type": "hybrid"
            } for idx in top_indices_hybrid]

        # Additional retrieval from Chroma (can act as a fallback or complementary)
        if self.chroma_store:
            try:
                chroma_results_with_scores = self.chroma_store.similarity_search_with_relevance_scores(query, k=top_k)
                chroma_docs = [{
                    "content": doc.page_content,
                    "metadata": doc.metadata,
                    "score": score, # Chroma relevance is 0-1, higher is better
                    "retrieval_type": "chroma_semantic"
                } for doc, score in chroma_results_with_scores]

                # Merge results and de-duplicate based on content
                # This simple merge prefers hybrid results if content is identical.
                # A more sophisticated merge could re-rank all results.
                all_contents = {r["content"]: r for r in results}
                for c_doc in chroma_docs:
                    if c_doc["content"] not in all_contents:
                        all_contents[c_doc["content"]] = c_doc
                    # else: # If content exists, maybe update score if chroma's is higher?
                    #     if c_doc["score"] > all_contents[c_doc["content"]]["score"]:
                    #         all_contents[c_doc["content"]] = c_doc # Or average, or take max

                # Sort all collected unique documents by score (descending)
                merged_results = sorted(list(all_contents.values()), key=lambda x: x["score"], reverse=True)
                results = merged_results[:top_k]

            except Exception as e:
                print(f"Error during Chroma search: {e}")
        
        print(f"Retrieved {len(results)} documents.")
        return results

    def search_chroma_only(self, query: str, top_k: int = config.TOP_K_RETRIEVER) -> List[Dict[str, Any]]:
        if not self.chroma_store:
            print("Chroma store not available for chroma_only search.")
            return []
        try:
            chroma_results_with_scores = self.chroma_store.similarity_search_with_relevance_scores(query, k=top_k)
            results = [{
                "content": doc.page_content,
                "metadata": doc.metadata,
                "score": score,
                "retrieval_type": "chroma_semantic"
            } for doc, score in chroma_results_with_scores]
            print(f"Retrieved {len(results)} documents using Chroma only.")
            return results
        except Exception as e:
            print(f"Error during Chroma-only search: {e}")
            return []

    def get_langchain_retriever(self):
        """Returns a LangChain compatible retriever (from Chroma store)."""
        if not self.chroma_store:
            # Fallback: create an in-memory one if documents are available
            if self.documents:
                print("Chroma store not initialized, creating temporary in-memory store for LangChain retriever.")
                temp_chroma = Chroma.from_documents(self.documents, lc_embedding_function)
                return temp_chroma.as_retriever(search_kwargs={"k": config.TOP_K_RETRIEVER})
            print("Cannot create LangChain retriever: Chroma store not initialized and no documents available.")
            return None
        return self.chroma_store.as_retriever(search_kwargs={"k": config.TOP_K_RETRIEVER})


# Example of how you might add a re-ranker (optional, more advanced)
# from sentence_transformers import CrossEncoder
# reranker_model = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')
# def rerank_results(query, results, top_n=5):
#     if not results: return []
#     pairs = [[query, res['content']] for res in results]
#     scores = reranker_model.predict(pairs)
#     for idx, res in enumerate(results):
#         res['rerank_score'] = scores[idx]
#     return sorted(results, key=lambda x: x['rerank_score'], reverse=True)[:top_n]