"""SQLAlchemy 2.0 ORM models.

Deliberately separate from app/domain/models.py. The domain must not import
SQLAlchemy — the moment it does, the ranking logic cannot be tested without a
database, which is the situation P2 exists to escape.
"""
import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Computed,
    DateTime,
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

# The encoder's output dimension. multilingual-e5-small and paraphrase-multilingual-
# MiniLM-L12-v2 are both 384-dim, which is what lets the encoder swap in the bug-13
# ablation happen without a schema migration.
EMBEDDING_DIMENSIONS = 384


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
    status: Mapped[str] = mapped_column(String(32), server_default="pending")
    # Bumped on every reindex. The response cache keys on it, so a reindex cannot serve
    # answers grounded in a corpus that no longer exists.
    corpus_version: Mapped[int] = mapped_column(Integer, server_default="1")
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

    id: Mapped[int] = mapped_column(primary_key=True)
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
