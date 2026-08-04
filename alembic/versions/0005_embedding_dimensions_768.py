"""widen chunks.embedding from 384 to 768 dimensions

Revision ID: 0005
Revises: 0004

The local 384-dim encoder was replaced by Gemini embeddings truncated to 768 (see
app/infra/embeddings/gemini_embedder.py for why: the local one peaked at 502MB RSS against
a 512MB hosting ceiling and could not be trimmed to fit).

THIS MIGRATION DELETES EVERY CHUNK. That is not incidental damage — it is the point:

  * pgvector's Vector(n) is fixed-width, so ALTER TYPE cannot succeed while rows hold
    384-dim values. There is nothing to convert them into; the two encoders' outputs are
    unrelated geometries, not the same vector at different precisions.
  * Keeping them would be worse than losing them. A mixed index answers queries with
    confident nonsense — cosine distance between a Gemini query vector and an e5 passage
    vector is a number, it is just a meaningless one.

Nothing irreplaceable is lost: chunks are derived data, rebuilt from documents/ by
`python -m app.cli ingest`, which the deployment runs at startup anyway
(AUTO_MIGRATE_ON_STARTUP). The `documents` rows survive, so their status is reset to
'pending' to match the now-empty index — leaving them 'indexed' would make
IngestionService.needs_processing() reason about an index that no longer exists.

Downgrade restores the 384-dim column, and likewise empties it.
"""
import pgvector.sqlalchemy
import sqlalchemy as sa

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

# Frozen at the values this migration moves between, NOT imported from models.py. A
# migration describes one historical step; importing a constant that later changes would
# silently rewrite what this step did.
OLD_DIMENSIONS = 384
NEW_DIMENSIONS = 768


def _reset(dimensions: int) -> None:
    # DELETE, not TRUNCATE: citations reference chunks, and ON DELETE cascades handle that
    # ordering for us. TRUNCATE would need CASCADE and would take a stronger lock.
    op.execute(sa.text("DELETE FROM chunks"))

    op.alter_column(
        "chunks",
        "embedding",
        existing_type=pgvector.sqlalchemy.Vector(),
        type_=pgvector.sqlalchemy.Vector(dimensions),
        existing_nullable=False,
        postgresql_using="NULL",
    )

    op.execute(
        sa.text(
            "UPDATE documents SET status = 'pending', chunks_done = 0, chunks_total = 0"
        )
    )


def upgrade() -> None:
    _reset(NEW_DIMENSIONS)


def downgrade() -> None:
    _reset(OLD_DIMENSIONS)
