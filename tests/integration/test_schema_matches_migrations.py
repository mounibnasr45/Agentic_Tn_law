"""The ORM models and the Alembic migrations must not drift apart.

They are two independent descriptions of the same schema, and nothing forces them to
agree. When they disagree, the failure is nasty: tests build their tables from the ORM
and pass, while production builds them from migrations and behaves differently.

This actually happened here. The ORM declared `status: Mapped[str] = mapped_column(
String(32), default="pending")`. A Python-side `default=` is applied by SQLAlchemy on
INSERT and never reaches the DDL — so `metadata.create_all()` produced a column with NO
database default, while the migration's `server_default="pending"` produced one with a
default. Any insert outside the ORM hit a NOT NULL violation on a column that was
supposed to default.

This test compares the migrated database against the ORM metadata and fails on drift.
"""
import os

import pytest
import pytest_asyncio
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import create_async_engine

from app.infra.db.models import Base

pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"), reason="no DATABASE_URL; integration tests need Postgres"
)


def _reflect(sync_conn) -> dict:
    """Reflect the whole schema in one pass, inside run_sync().

    An Inspector must not escape the run_sync() callback. Yielding it and calling
    .get_columns() later attempts synchronous I/O on an async connection, which raises
    MissingGreenlet — the same failure mode that expire_on_commit=False guards against
    in app/infra/db/session.py. So: gather plain data here, assert on it outside.
    """
    inspector = inspect(sync_conn)
    return {
        "tables": set(inspector.get_table_names()),
        "columns": {
            table.name: {c["name"]: c for c in inspector.get_columns(table.name)}
            for table in Base.metadata.sorted_tables
            if table.name in inspector.get_table_names()
        },
        "indexes": {
            table.name: {ix["name"] for ix in inspector.get_indexes(table.name)}
            for table in Base.metadata.sorted_tables
            if table.name in inspector.get_table_names()
        },
    }


@pytest_asyncio.fixture
async def schema() -> dict:
    engine = create_async_engine(os.environ["DATABASE_URL"])
    async with engine.connect() as conn:
        reflected = await conn.run_sync(_reflect)
    await engine.dispose()
    return reflected


async def test_every_orm_table_exists_in_the_migrated_database(schema):
    declared = {table.name for table in Base.metadata.sorted_tables}

    assert declared <= schema["tables"], (
        f"declared in the ORM but never migrated: {declared - schema['tables']}"
    )


async def test_every_orm_column_exists_with_the_same_nullability(schema):
    drift = []

    for table in Base.metadata.sorted_tables:
        migrated = schema["columns"].get(table.name, {})

        for column in table.columns:
            if column.name not in migrated:
                drift.append(f"{table.name}.{column.name}: in the ORM, not in the migration")
            elif column.nullable != migrated[column.name]["nullable"]:
                drift.append(
                    f"{table.name}.{column.name}: nullable={column.nullable} in the ORM, "
                    f"nullable={migrated[column.name]['nullable']} in the migration"
                )

    assert not drift, "ORM/migration drift:\n  " + "\n  ".join(drift)


async def test_columns_with_an_orm_server_default_have_one_in_the_database(schema):
    """The exact drift that bit us: a default in the ORM that never reached the DDL."""
    drift = []

    for table in Base.metadata.sorted_tables:
        migrated = schema["columns"].get(table.name, {})

        for column in table.columns:
            if column.name not in migrated:
                continue
            # A Computed (GENERATED ALWAYS AS) column is modelled by SQLAlchemy as a kind
            # of server default, but Postgres reports its expression under `computed`,
            # not `default`. Checking `default` on chunks.tsv would flag a healthy
            # generated column as drift. Its presence is asserted separately below.
            if column.computed is not None:
                continue
            if column.server_default is None:
                continue

            if migrated[column.name]["default"] is None:
                drift.append(
                    f"{table.name}.{column.name}: the ORM declares a server_default, "
                    f"the migrated column has none"
                )

    assert not drift, "missing database defaults:\n  " + "\n  ".join(drift)


async def test_the_tsv_column_is_generated_by_postgres(schema):
    """The lexical arm must be a STORED GENERATED column, not something the app writes.

    If tsv were merely a normal column that ingestion populated, it could drift out of
    sync with `content` on any code path that forgot to update it — and the lexical arm
    would silently rot. GENERATED ALWAYS makes that impossible: Postgres recomputes it
    from content on every write, inside the same transaction.
    """
    tsv = schema["columns"]["chunks"]["tsv"]

    assert tsv["computed"] is not None, "tsv is not a generated column"
    assert "to_tsvector" in tsv["computed"]["sqltext"]
    assert "french_unaccent" in tsv["computed"]["sqltext"]
    assert tsv["computed"]["persisted"] is True, "tsv must be STORED, not VIRTUAL"


async def test_the_lexical_index_exists(schema):
    """The GIN index on tsv IS the lexical arm. Without it every query sequential-scans."""
    assert "ix_chunks_tsv" in schema["indexes"]["chunks"]
