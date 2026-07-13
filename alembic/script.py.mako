"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
"""
# Alembic autogenerate emits pgvector.sqlalchemy.Vector(dim=384) into migration files
# but does NOT add this import, so the migration dies with NameError on upgrade.
# Importing it here, in the template, means every generated migration is born working.
import pgvector.sqlalchemy  # noqa: F401
import sqlalchemy as sa
from alembic import op
${imports if imports else ""}

revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
