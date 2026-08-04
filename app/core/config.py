"""Typed application settings.

Replaces the old module-level `config.py`, which read os.getenv at import time,
called os.makedirs three times at import, and stat'd the filesystem while
printing warnings. That made importing config a side effect, and made every
setting impossible to override in a test.

Settings are resolved once via get_settings() and cached. Tests override by
calling get_settings.cache_clear() after patching the environment.
"""
import os
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- LLM ---
    openrouter_api_key: str = os.environ.get("OPENROUTER_API_KEY", "")  
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    agent_llm_model: str = "deepseek/deepseek-chat"
    summary_llm_model: str = "mistralai/mistral-7b-instruct-v0.2"
    llm_temperature: float = 0.1
    llm_max_tokens: int = 1024
    llm_max_retries: int = 3

    # --- Auth ---
    # MUST be overridden in every real deployment: a secret committed to a public repo is
    # a backdoor, and whoever holds it can forge a token for ANY user. This default exists
    # only so the test suite and `docker compose up` work out of the box, and it names
    # itself so it cannot be mistaken for a real one.
    #
    # Length: >= 32 bytes. RFC 7518 §3.2 requires an HMAC key at least as long as the hash
    # output (32 bytes for SHA-256), and PyJWT emits InsecureKeyLengthWarning below that.
    # A short secret is brute-forceable offline from a single captured token.
    jwt_secret: str = "dev-tunisian-agentic-law-INSECURE-DEFAULT-do-not-deploy"
    # Short, because an access token cannot be revoked — the only thing limiting the
    # damage of a stolen one is how fast it expires.
    access_token_minutes: int = 15
    # Long, because it CAN be revoked, and rotation means a stolen one is detectable.
    refresh_token_days: int = 14

    # --- API ---
    environment: str = "development"  # "production" refuses to start on a dev secret
    cors_origins: str = "http://localhost:8501,http://localhost:3000"

    # --- Database ---
    # psycopg3, not asyncpg: LangGraph's Postgres checkpointer (P5) is built on psycopg3,
    # and one driver beats two pools with two sets of connection semantics.
    database_url: str = "postgresql+psycopg://legal:legal@localhost:5432/legal"
    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_echo: bool = False
    # render.yaml's preDeployCommand (`alembic upgrade head && python -m app.cli ingest`)
    # only exists on paid Render instance types — Free tier supports neither Pre-Deploy
    # Command nor SSH, so there is no way to run either step out of band. Set this on a
    # Free-tier deploy to run both at process startup instead, before the app accepts
    # traffic. Off by default: everywhere else (dev, CI, paid Render) already has the
    # real preDeployCommand or a developer running these by hand, and startup should not
    # silently take longer or touch the database in those cases.
    auto_migrate_on_startup: bool = False

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
    # Which embedder app/infra/embeddings/create_embedder() builds: "gemini" or "onnx".
    #
    # DEFAULTS TO THE REMOTE ONE, WHICH IS NOT THE ARCHITECTURALLY NICER CHOICE. The local
    # ONNX encoder needs no network, no API key and no quota — but it peaks at 502MB RSS
    # against the 512MB ceiling of the only free hosting available, and no amount of
    # trimming closed that gap (torch removal and a tokenizer swap each cut a large chunk
    # and it still OOM'd). Moving embeddings out of the process is what makes this
    # deployable at all. Set EMBEDDING_PROVIDER=onnx, and install onnxruntime + tokenizers,
    # to go back to embedding locally on a host with real memory.
    embedding_provider: str = "gemini"

    gemini_api_key: str = ""
    # Pinned, not "latest": gemini-embedding-2 returns ONE aggregated vector for a
    # multi-text request instead of one per text, which would quietly index a single
    # meaningless embedding per batch. See gemini_embedder.py's module docstring.
    gemini_embedding_model: str = "gemini-embedding-001"
    # 768 rather than the model's native 3072: Matryoshka truncation costs little quality
    # and keeps the pgvector column a quarter of the size. Changing this is a schema
    # change (Vector(n) is fixed-width) AND a full re-embed — see EMBEDDING_DIMENSIONS in
    # app/infra/db/models.py, which must agree with it.
    embedding_dimensions: int = 768

    # --- Local ONNX encoder (only when embedding_provider="onnx") ---
    embedding_model_name: str = "intfloat/multilingual-e5-small"
    # Which ONNX export of embedding_model_name to load — see the _ONNX_VARIANTS mapping
    # in app/infra/embeddings/onnx_embedder.py. "int8" (118MB) is the default and fits
    # Render's 512MB free tier; "o4" (235MB) is the documented fallback if int8's
    # quantization noise ever regresses eval/baseline.json's hit@5 beyond what
    # eval/ablation.py --gate tolerates.
    embedding_onnx_variant: str = "int8"
    chunk_size: int = 700
    chunk_overlap: int = 150
    top_k_retriever: int = 20

    # 0.0 = dense only, 1.0 = lexical only, in between = weighted hybrid.
    #
    # DENSE-ONLY IS THE MEASURED BEST, and this default says so. Every hybrid weight
    # scores worse than pure dense on the golden set, and the gap WIDENED when the encoder
    # moved to Gemini: dense hit@5 0.982, best weighted hybrid 0.929, RRF 0.804. We
    # expected the lexical arm to earn its keep on article-number lookups ("que dit
    # l'article 258 ?") and tested that class specifically. It did not.
    #
    # (Under the previous local e5 encoder the same ordering held at lower absolute
    # numbers — dense 0.821, hybrid 0.786, RRF 0.714 — so this is a property of the corpus
    # and the query mix, not of one encoder.)
    #
    # The lexical arm and RRF stay in the codebase and in the ablation, because this
    # result is specific to THIS corpus (834 chunks) and must be re-measured before it is
    # trusted anywhere else. Shipping "hybrid" anyway would be choosing a worse system for
    # a nicer word.
    hybrid_weight_bm25: float = 0.0

    # --- Agent ---
    agent_max_iterations: int = 10
    agent_request_timeout: int = 120
    agent_verbose: bool = False

    # --- Reflection checkpoint ---
    # After the agent drafts an answer, one extra LLM call asks whether the draft leans on a
    # legal term of art that the retrieved articles never defined ("préméditation" appears in
    # Article 201 but is defined elsewhere). Named terms are retrieved and folded in.
    #
    # A KILL SWITCH, not a constant. This costs +1 LLM call on every question and +2 plus a
    # retrieval when a gap is found. On a free-tier host that is the difference between a
    # slow answer and a timed-out one, and the fix must be an env var on a dashboard, not a
    # redeploy — if the upstream gets slow at 2am, someone needs to turn this off in seconds.
    reflection_enabled: bool = True
    # Bounds the fan-out per checkpoint. Two undefined terms in one legal answer is already
    # unusual; more than that and the reflection is almost certainly hallucinating terms to
    # look useful, which is a cost sink, not a quality gain.
    reflection_max_terms: int = 2
    # Deliberately much shorter than agent_request_timeout (120s). The draft already exists
    # by this point: this call is an ENHANCEMENT racing a deadline, and a user waiting on a
    # complete answer is better served by shipping it than by waiting two more minutes for a
    # gloss. On expiry, reflection.py fails open and returns the draft untouched.
    reflection_timeout: int = 30
    # Empty = reuse agent_llm_model. Set to a smaller model (e.g. the summary model) to trade
    # some term-detection recall for latency and cost. Worth measuring before assuming a 7B
    # model reads French legal prose well enough to spot an undefined term of art.
    reflection_llm_model: str = ""

    # --- Paths ---
    documents_dir: Path = Path("documents")

    # Where the built Angular bundle lives, when this process is also serving it.
    #
    # None here, but the Dockerfile sets STATIC_DIR=/app/web_dist because the image
    # genuinely contains the bundle. So: running from a source checkout serves no SPA
    # (`ng serve` or nginx does that), while any container built from this repo can serve
    # both the API and the SPA from one origin. That single-origin case is what makes the
    # Hugging Face Spaces deployment work at all — one process, one port — and it is
    # possible only because the frontend calls a relative "/api" (see api-base.ts) and so
    # does not care which topology is serving it.
    static_dir: Path | None = None
    vector_store_dir: Path = Path("vector_store")
    default_document_filenames: list[str] = [
        "Constitution_fr.pdf",
        "penal_code.pdf",
        "loi relatif à la liberté de la presse.pdf",
    ]

    # --- Identity (sent to OpenRouter for attribution) ---
    app_title: str = "Agent Juridique Tunisien"
    app_referer: str = "https://agentic-tn-law.onrender.com"

    # --- Logging ---
    log_level: str = "INFO"
    log_json: bool = True

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def resolved_reflection_model(self) -> str:
        """The reflection model, defaulting to the agent's own.

        A property rather than a validator default: `agent_llm_model` can itself be
        overridden by env, and a validator would freeze whatever was set at import time.
        """
        return self.reflection_llm_model or self.agent_llm_model

    @property
    def jwt_secret_is_the_insecure_default(self) -> bool:
        """The startup check that stops a dev secret reaching production.

        A default secret is the single most common way a portfolio project ships an
        authentication bypass: it is in the public repo, so anyone can mint a token for
        any user. main.py refuses to start on this in production and shouts in dev.
        """
        return "INSECURE-DEFAULT" in self.jwt_secret

    @field_validator("database_url")
    @classmethod
    def _coerce_driver(cls, value: str) -> str:
        """Accept a bare postgres DSN and add the psycopg3 driver marker.

        Render (and most managed-Postgres providers) hand out a connection string as
        `postgres://...` or `postgresql://...` — the wire protocol, not a SQLAlchemy URL.
        Without this, DATABASE_URL from `fromDatabase.connectionString` in render.yaml would
        need hand-editing on every provider switch. SQLAlchemy's psycopg3 dialect requires
        the `+psycopg` driver marker explicitly; it will not infer it.
        """
        if value.startswith(("postgres://", "postgresql://")) and "+psycopg" not in value:
            return value.replace("postgres://", "postgresql+psycopg://", 1).replace(
                "postgresql://", "postgresql+psycopg://", 1
            )
        return value

    @field_validator("jwt_secret")
    @classmethod
    def _reject_short_secrets(cls, value: str) -> str:
        # 32 bytes = the SHA-256 output length. Below it, HMAC gains no security from the
        # extra key material and the secret becomes brute-forceable offline from one
        # captured token. PyJWT warns; we refuse.
        if len(value.encode()) < 32:
            raise ValueError(
                f"jwt_secret must be at least 32 bytes (RFC 7518 §3.2), got {len(value.encode())}"
            )
        return value

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
