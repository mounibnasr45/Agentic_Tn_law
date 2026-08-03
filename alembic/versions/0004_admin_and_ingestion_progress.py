"""admin flag and live ingestion progress

Revision ID: 0004
Revises: 0003

Two independent additions, in one migration because they ship as one feature (admin
corpus upload):

  users.is_admin        — who is allowed to replace the corpus
  documents.chunks_*    — how far along an in-flight ingest is
  documents.error       — why a failed ingest failed

All five columns are additive with server defaults, so this migration is safe on a
populated database: existing rows get false/0/NULL without a table rewrite of user data.

WHY PROGRESS IS COLUMNS AND NOT A CACHE. An in-memory {document_id: progress} dict is
invisible to a second worker and lost when a free-tier dyno spins down mid-ingest, which
is precisely when an admin is staring at the progress bar wondering what happened. Two
integers on the row are readable by every worker and survive a restart.
"""
import sqlalchemy as sa

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # server_default, not a Python-side default: the column must have a DEFAULT in the
    # DDL, or metadata.create_all() produces a schema that disagrees with this migration
    # and any INSERT outside the ORM hits a NOT NULL violation. The drift test in
    # tests/integration/test_schema_matches_migrations.py exists to catch exactly that.
    op.add_column(
        "users",
        sa.Column("is_admin", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )

    op.add_column(
        "documents",
        sa.Column("chunks_total", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )
    op.add_column(
        "documents",
        sa.Column("chunks_done", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )
    # Nullable: only a failed ingest has a reason. Text, not String(n) — an extraction
    # error message has no natural length limit and truncating the one field that explains
    # a failure would be a poor trade for a few bytes.
    op.add_column("documents", sa.Column("error", sa.Text(), nullable=True))

    # Backfill: every document that is ALREADY indexed has, by definition, finished all of
    # its chunks. Without this the admin screen would render the existing corpus as
    # "indexed, 0 / 0 chunks", which reads like data loss.
    op.execute(
        """
        UPDATE documents d
        SET chunks_total = c.n, chunks_done = c.n
        FROM (SELECT document_id, count(*) AS n FROM chunks GROUP BY document_id) c
        WHERE c.document_id = d.id
        """
    )


def downgrade() -> None:
    op.drop_column("documents", "error")
    op.drop_column("documents", "chunks_done")
    op.drop_column("documents", "chunks_total")
    op.drop_column("users", "is_admin")
