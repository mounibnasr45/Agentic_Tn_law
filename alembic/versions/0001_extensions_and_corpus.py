"""extensions, french text search config, documents and chunks

Revision ID: 0001
Revises:
"""
import pgvector.sqlalchemy  # noqa: F401  (Vector() below resolves through this)
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

EMBEDDING_DIMENSIONS = 384


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent")
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")  # gen_random_uuid()

    # Postgres' stock 'french' config stems but does NOT strip accents, so a search for
    # "francais" would not match "français" and "peine" would not match "peiné". In a
    # French legal corpus typed by users without accents, that is most queries. This
    # config unaccents first, then stems.
    op.execute("""
        CREATE TEXT SEARCH CONFIGURATION french_unaccent (COPY = french);
        ALTER TEXT SEARCH CONFIGURATION french_unaccent
          ALTER MAPPING FOR hword, hword_part, word
          WITH unaccent, french_stem;
    """)

    op.create_table(
        "documents",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("storage_key", sa.String(1024), nullable=True),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("corpus_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("sha256", name="uq_documents_sha256"),
    )

    op.create_table(
        "chunks",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("article_number", sa.String(64), nullable=True),
        sa.Column("part_index", sa.Integer(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding_model", sa.String(128), nullable=False),
        sa.Column(
            "embedding",
            pgvector.sqlalchemy.Vector(EMBEDDING_DIMENSIONS),
            nullable=False,
        ),
        # The lexical arm, generated and stored by Postgres. Durable, transactional,
        # instantly consistent with INSERTs, shared by every worker, zero RAM per
        # process. The BM25Okapi index this replaces lived in memory and was never
        # written to disk — which is why a restarted container silently stopped doing
        # hybrid search (bug 1).
        sa.Column(
            "tsv",
            postgresql.TSVECTOR(),
            sa.Computed("to_tsvector('french_unaccent', content)", persisted=True),
            nullable=False,
        ),
        sa.UniqueConstraint("document_id", "chunk_index", name="uq_chunks_document_index"),
    )

    op.create_index("ix_chunks_tsv", "chunks", ["tsv"], postgresql_using="gin")
    op.create_index("ix_chunks_article_number", "chunks", ["article_number"])

    # No vector index. At ~5k chunks an exact scan over 384-dim float4 is a few
    # milliseconds with perfect recall. HNSW gets added in a later migration only when a
    # benchmark says it is needed — and IVFFlat never, since it must be trained on data
    # present at build time and silently loses recall when the corpus is rebuilt.


def downgrade() -> None:
    op.drop_index("ix_chunks_article_number", table_name="chunks")
    op.drop_index("ix_chunks_tsv", table_name="chunks")
    op.drop_table("chunks")
    op.drop_table("documents")
    op.execute("DROP TEXT SEARCH CONFIGURATION IF EXISTS french_unaccent")
