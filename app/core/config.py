"""Typed application settings.

Replaces the old module-level `config.py`, which read os.getenv at import time,
called os.makedirs three times at import, and stat'd the filesystem while
printing warnings. That made importing config a side effect, and made every
setting impossible to override in a test.

Settings are resolved once via get_settings() and cached. Tests override by
calling get_settings.cache_clear() after patching the environment.
"""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- LLM ---
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    agent_llm_model: str = "deepseek/deepseek-chat"
    summary_llm_model: str = "mistralai/mistral-7b-instruct-v0.2"
    llm_temperature: float = 0.1
    llm_max_tokens: int = 1024
    llm_max_retries: int = 3

    # --- Database ---
    # psycopg3, not asyncpg: LangGraph's Postgres checkpointer (P5) is built on psycopg3,
    # and one driver beats two pools with two sets of connection semantics.
    database_url: str = "postgresql+psycopg://legal:legal@localhost:5432/legal"
    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_echo: bool = False

    # --- Retrieval ---
    # Candidates pulled from EACH arm before fusion. Higher = less truncation bias in
    # align_candidates (a chunk absent from one arm is scored 0.0 there), wider SQL scan.
    candidate_limit: int = 50
    # BUG 13, FIXED AND MEASURED. The previous encoder
    # (paraphrase-multilingual-MiniLM-L12-v2) has max_seq_length=128 TOKENS, while
    # chunk_size is in CHARACTERS: 38% of penal-code chunks exceeded it, and 12% of the
    # corpus's tokens were silently dropped before ever being embedded. No error; just a
    # transformers warning nobody read. e5-small takes 512 tokens and is also 384-dim, so
    # the swap needed no schema migration. Measured on the 56-question golden set:
    #     hit@1  0.250 -> 0.679
    #     hit@5  0.500 -> 0.839
    #     MRR    0.364 -> 0.747
    # e5 requires "query: " / "passage: " prefixes; the embedder adds them.
    embedding_model_name: str = "intfloat/multilingual-e5-small"
    chunk_size: int = 700
    chunk_overlap: int = 150
    top_k_retriever: int = 20

    # 0.0 = dense only, 1.0 = lexical only, in between = weighted hybrid.
    #
    # DENSE-ONLY IS THE MEASURED BEST, and this default says so. Once the encoder was
    # fixed, EVERY hybrid weight scored worse than pure dense on the golden set: best
    # weighted hybrid hit@5 0.732, RRF 0.750, dense 0.839. We expected the lexical arm to
    # earn its keep on article-number lookups ("que dit l'article 258 ?") and tested that
    # class specifically — dense 5/6, lexical 1/6. It did not.
    #
    # The lexical arm and RRF stay in the codebase and in the ablation, because this
    # result is specific to THIS corpus (712 chunks) and THIS encoder and must be
    # re-measured before it is trusted anywhere else. Shipping "hybrid" anyway would be
    # choosing a worse system for a nicer word.
    hybrid_weight_bm25: float = 0.0

    # --- Agent ---
    agent_max_iterations: int = 10
    agent_request_timeout: int = 120
    agent_verbose: bool = False

    # --- Paths ---
    documents_dir: Path = Path("documents")
    vector_store_dir: Path = Path("vector_store")
    default_document_filenames: list[str] = ["Constitution_fr.pdf", "penal_code.pdf"]

    # --- Identity (sent to OpenRouter for attribution) ---
    app_title: str = "Agent Juridique Tunisien"
    app_referer: str = "https://agentic-tn-law.onrender.com"

    # --- Logging ---
    log_level: str = "INFO"
    log_json: bool = True

    @property
    def chroma_db_dir(self) -> Path:
        return self.vector_store_dir / "chroma_db"

    def missing_documents(self) -> list[str]:
        """Which of the expected corpus files are absent. No printing, no mkdir."""
        return [
            name
            for name in self.default_document_filenames
            if not (self.documents_dir / name).exists()
        ]


@lru_cache
def get_settings() -> Settings:
    return Settings()
