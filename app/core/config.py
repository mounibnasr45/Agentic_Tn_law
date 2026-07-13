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

    # --- Retrieval ---
    # NOTE: this encoder has max_seq_length=128 TOKENS, while chunk_size below is
    # in CHARACTERS (~700 chars is ~200-250 French tokens). Chunks are therefore
    # silently truncated at encode time. Tracked as bug 13; the ablation harness
    # quantifies the fix (multilingual-e5-small, 512 tokens, also 384-dim).
    embedding_model_name: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    chunk_size: int = 700
    chunk_overlap: int = 150
    top_k_retriever: int = 20
    hybrid_weight_bm25: float = 0.4

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
