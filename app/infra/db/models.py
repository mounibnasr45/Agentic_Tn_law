"""SQLAlchemy 2.0 ORM models for every table: users, documents, chunks,
conversations, messages, citations."""
import uuid
from datetime import UTC, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    Computed,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import TSVECTOR, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# The encoder's output dimension. Vector(n) is fixed-width, so this is schema, not
# configuration: it must equal Settings.embedding_dimensions, and changing either one
# requires a migration AND a full re-embed (migration 0005 did exactly that going from the
# 384-dim local e5 encoder to Gemini truncated at 768).
#
# It was 384 through migrations 0001-0004, which is why both local encoders considered so
# far — multilingual-e5-small and paraphrase-multilingual-MiniLM-L12-v2 — could be swapped
# for one another during the bug-13 ablation without touching the schema at all.
EMBEDDING_DIMENSIONS = 768


class Base(DeclarativeBase):
    pass


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    title: Mapped[str] = mapped_column(String(512))
    # Object-storage key. NULL until documents move to MinIO in P6; corpus files are
    # read from disk before that.
    storage_key: Mapped[str | None] = mapped_column(String(1024))
    sha256: Mapped[str] = mapped_column(String(64))
    # server_default, not default. A Python-side `default=` is applied by SQLAlchemy on
    # INSERT and never reaches the DDL, so the column ends up with NO database default —
    # and metadata.create_all() then produces a schema that silently DISAGREES with the
    # migration. Anything inserting outside the ORM (psql, a data fix, a bulk load) hits
    # a NOT NULL violation on a column that was supposed to have a default.
    # pending -> processing -> indexed | failed. The admin screen renders this directly,
    # so "failed" must be a real terminal state rather than a row that silently stays
    # "processing" forever after a crash.
    status: Mapped[str] = mapped_column(String(32), server_default="pending")
    # Bumped on every reindex. The response cache keys on it, so a reindex cannot serve
    # answers grounded in a corpus that no longer exists.
    corpus_version: Mapped[int] = mapped_column(Integer, server_default="1")

    # LIVE PROGRESS, IN THE DATABASE AND NOT IN MEMORY.
    #
    # The obvious implementation is a module-level dict of {document_id: progress}. It is
    # wrong here for three reasons that all bite on a free host: a dyno that spins down
    # mid-ingest loses the progress of work that is still half-committed; a second worker
    # cannot see the first worker's dict, so the admin screen shows progress only if the
    # poll happens to land on the right process; and a module-level mutable is the exact
    # shape of bug 2. Two integers on the row cost nothing and have none of those problems.
    chunks_total: Mapped[int] = mapped_column(Integer, server_default="0")
    chunks_done: Mapped[int] = mapped_column(Integer, server_default="0")
    # Populated only when status == "failed". Shown to the admin, so it must be the reason
    # ("no text extracted from PDF"), never a raw traceback.
    error: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    chunks: Mapped[list["Chunk"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )

    # Re-uploading the same bytes must be a no-op, not a duplicated corpus.
    __table_args__ = (UniqueConstraint("sha256", name="uq_documents_sha256"),)


class Chunk(Base):
    __tablename__ = "chunks"

    # BigInteger, not the bare `Mapped[int]` that SQLAlchemy maps to INTEGER. The migration
    # declares BIGINT, so a plain Mapped[int] silently DISAGREES with the database — the
    # exact ORM/migration drift that `alembic check` exists to catch, and that our own
    # hand-rolled drift test missed because it compared nullability and defaults but not
    # types. Two billion chunks is not a real ceiling; a schema that lies about itself is.
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE")
    )
    chunk_index: Mapped[int] = mapped_column(Integer)
    # "Article 264". Nullable: preambles and tables of contents are retrievable but not
    # citable as an article. This column is what makes the golden set's expected_article
    # checkable at all.
    article_number: Mapped[str | None] = mapped_column(String(64))
    part_index: Mapped[int | None] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)

    # Recorded per row so that a model swap is detectable rather than silent. Mixing
    # embeddings from two encoders in one index produces confident nonsense.
    embedding_model: Mapped[str] = mapped_column(String(128))
    # Unit-normalised at encode time, so cosine distance is cheap and well-behaved.
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIMENSIONS))

    # THE LEXICAL ARM. Generated and stored by Postgres, so it is durable, transactional
    # and instantly consistent with INSERTs. This is what kills bug 1: the old BM25Okapi
    # index lived in process memory, was never persisted, and vanished on restart. There
    # is no longer an in-memory index to lose, no global to mutate, and no lock to forget.
    tsv: Mapped[str] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('french_unaccent', content)", persisted=True),
    )

    document: Mapped[Document] = relationship(back_populates="chunks")

    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index", name="uq_chunks_document_index"),
        Index("ix_chunks_tsv", "tsv", postgresql_using="gin"),
        Index("ix_chunks_article_number", "article_number"),
        # NO vector index yet, on purpose. ~5k chunks x 384 float4 is about 7.5MB; an
        # exact scan is a few milliseconds and gives 100% recall. HNSW is added in a
        # later migration only once a benchmark shows the crossover — "I measured it"
        # beats "I added the index everyone adds".
    )


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(256))  # argon2id
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="true")
    # Corpus ingestion is destructive: uploading a document re-chunks and re-embeds, and
    # replacing the corpus changes every future answer the system gives. That is not a
    # thing any registered account should be able to do on a public URL.
    #
    # server_default="false" so the column is false in the DDL too — a Python-side default
    # would leave the migration with no default at all, and any INSERT outside the ORM
    # (psql, a data fix) would then hit a NOT NULL violation. The same trap documented on
    # Document.status.
    #
    # Granted only by `python -m app.cli grant-admin <email>`. There is deliberately no
    # "first user becomes admin" rule and no self-service path: on a public deployment the
    # first registration is whoever finds the URL first.
    is_admin: Mapped[bool] = mapped_column(Boolean, server_default="false")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class RefreshToken(Base):
    """One row per issued refresh token, forming a rotation chain.

    Rotation: every refresh issues a NEW token and marks the old one revoked, with
    replaced_by pointing at its successor. Without rotation a "refresh token" is just an
    access token with a 14-day expiry, and an interviewer will say so.

    The chain is what makes REPLAY DETECTION possible. If an already-revoked token is
    presented, either the user is replaying an old request or an attacker stole the token
    before the legitimate client rotated it — and we cannot tell which. So we revoke the
    entire chain and force re-authentication. Storing only the newest token would make
    this undetectable: the stolen token would simply look unknown.
    """

    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    # sha256 of the raw token. The raw value NEVER touches the database: a leaked table of
    # raw refresh tokens is a leaked table of live sessions.
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    replaced_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("refresh_tokens.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped[User] = relationship(back_populates="refresh_tokens")

    @property
    def is_usable(self) -> bool:
        return self.revoked_at is None and self.expires_at > datetime.now(UTC)


class Conversation(Base):
    """A chat thread, owned by exactly one user.

    WHY THIS EXISTS ALONGSIDE THE LANGGRAPH CHECKPOINTER — an interviewer will ask.

    The checkpointer stores an opaque, versioned graph-state blob whose job is RESUMING
    EXECUTION. It is not a queryable read model. You cannot answer "list this user's last
    20 conversations with titles" or "which articles does the corpus cite most" from it,
    and coupling the product's read model to LangGraph's internal serialisation format is
    one library upgrade away from breaking.

    So: checkpointer = execution state. conversations/messages/citations = product read
    model. The duplication is deliberate.
    """

    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    # == the LangGraph thread_id. Ownership is enforced HERE, in our schema — LangGraph
    # will happily hand any caller any thread_id it is given. Bug 2 (every visitor sharing
    # one memory buffer) becomes impossible only because memory is keyed by a row that has
    # a user_id on it.
    thread_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    title: Mapped[str | None] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.created_at",
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(16))  # user | assistant
    content: Mapped[str] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(String(128))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    conversation: Mapped[Conversation] = relationship(back_populates="messages")
    citations: Mapped[list["Citation"]] = relationship(
        back_populates="message", cascade="all, delete-orphan", order_by="Citation.rank"
    )


class Citation(Base):
    """THE STRUCTURAL FIX FOR BUG 4.

    `sources` used to be a hardcoded placeholder string, because the retrieval tool
    flattened its results into truncated text before the agent ever saw them — so chunk
    ids, scores and article numbers could not survive the round trip.

    A citation row can only exist if a chunk was actually retrieved: chunk_id is a foreign
    key. The API therefore cannot return a citation it did not retrieve, which is a much
    stronger guarantee than "the LLM was told to cite its sources".
    """

    __tablename__ = "citations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    message_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("messages.id", ondelete="CASCADE"), index=True
    )
    # SET NULL, not CASCADE: re-indexing the corpus deletes chunks, and a past answer's
    # citations must not silently vanish from the record because the corpus moved on.
    chunk_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("chunks.id", ondelete="SET NULL")
    )
    source: Mapped[str] = mapped_column(String(512))
    article_number: Mapped[str | None] = mapped_column(String(64))
    excerpt: Mapped[str] = mapped_column(Text)
    score: Mapped[float] = mapped_column(Float)
    rank: Mapped[int] = mapped_column(Integer)

    message: Mapped[Message] = relationship(back_populates="citations")
