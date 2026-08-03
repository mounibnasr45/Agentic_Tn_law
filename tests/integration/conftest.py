"""Integration-suite guards: a destructive-database check, and optional-dependency stubs.

THE DATABASE GUARD EXISTS BECAUSE THIS SUITE DESTROYED A LIVE DATABASE.

Every fixture in here begins with

    TRUNCATE users, refresh_tokens, conversations, messages, citations, documents, chunks

which is correct for a test database and catastrophic for any other one. docker-compose
publishes the `db` service on 5432, so `localhost:5432` from a developer shell is not a
local sandbox — it IS the container's Postgres, the same database the running app uses.
Pointing DATABASE_URL there and running pytest deleted a real user account and the whole
indexed corpus, and nothing warned beforehand: the truncate succeeded exactly as written.

`_refuse_non_test_database` below makes that failure impossible rather than merely
discouraged. The database name must look like a test database, so the destructive default
is opt-in by naming rather than by remembering.

WHY THE STUBS EXIST, AND THE BUG THEY FIX.

`app.agent.graph` imports langgraph.checkpoint.postgres.aio, psycopg and psycopg_pool at
MODULE LOAD. On a machine without those installed, merely importing the app to build a
test client raises ImportError — so each integration module grew its own copy of a
sys.modules stubbing block to make collection possible.

Those copies used:

    sys.modules.setdefault("psycopg", _stub)

which is subtly wrong. `sys.modules` holds what has been IMPORTED, not what is INSTALLED.
At collection time psycopg usually has not been imported yet, so setdefault installs the
stub even on a machine where the real package is present — and the stub then shadows it
permanently. The failure is spectacular and confusing:

    ModuleNotFoundError: No module named 'psycopg.pq'; 'psycopg' is not a package

raised from inside SQLAlchemy, on a machine where psycopg is definitely installed. It only
appears once DATABASE_URL is set (integration tests are skipped otherwise), which is why
it survived: CI has no psycopg, developers had no DATABASE_URL, and the two configurations
that would each have passed never overlapped.

The fix is to ask whether the package is INSTALLABLE — importlib.util.find_spec — and stub
only what is genuinely absent. A conftest is the right home because pytest imports it
before any test module in this directory, which is exactly the ordering the stubs need.
"""
import importlib.util
import os
import sys
import types

import pytest

# A database this suite is allowed to TRUNCATE must say so in its name. Substring, not
# exact match, so `legal_test`, `test_legal` and `agentic_tn_law_test_ci` all qualify while
# the production `legal` does not.
_TEST_DB_MARKERS = ("test", "_ci")


def _database_name(url: str) -> str:
    """The database name from a SQLAlchemy URL, without importing SQLAlchemy.

    Everything after the last '/', minus any ?query string. Deliberately dumb: this runs
    before anything else and must not fail on an unusual URL — an unparseable one yields a
    name that matches no marker and is therefore refused, which is the safe direction.
    """
    return url.rsplit("/", 1)[-1].split("?")[0].strip().lower()


def pytest_collection_modifyitems(config, items):  # noqa: ARG001 - pytest hook signature
    """Refuse to run the destructive suite against a database not named as a test one.

    A collection hook rather than a fixture: fixtures run per test, and by the time the
    first one executes pytest has already reported the run as started. Failing here stops
    everything before a single TRUNCATE is issued.
    """
    url = os.getenv("DATABASE_URL")
    if not url:
        return  # integration tests are already skipped; nothing destructive can run

    name = _database_name(url)
    if any(marker in name for marker in _TEST_DB_MARKERS):
        return

    pytest.exit(
        f"\n\nREFUSING TO RUN: DATABASE_URL points at database {name!r}, which is not "
        f"named as a test database.\n"
        f"This suite TRUNCATEs users, conversations, documents and chunks on every "
        f"fixture.\n"
        f"docker-compose publishes the app's Postgres on localhost:5432 — pointing here "
        f"deletes real data.\n\n"
        f"Create a dedicated database and point DATABASE_URL at it:\n"
        f'  docker compose exec -T db psql -U legal -d postgres -c "CREATE DATABASE '
        f'legal_test OWNER legal;"\n'
        f'  docker compose exec -T db psql -U legal -d legal_test -c "CREATE EXTENSION '
        f'IF NOT EXISTS vector; CREATE EXTENSION IF NOT EXISTS unaccent;"\n'
        f"  DATABASE_URL=postgresql+psycopg://legal:legal@localhost:5432/legal_test "
        f"python -m alembic upgrade head\n",
        returncode=1,
    )


def _is_installed(name: str) -> bool:
    """True if the package can actually be imported.

    find_spec raises ModuleNotFoundError rather than returning None when a PARENT package
    is missing (looking up "a.b" when "a" is absent), so the exception is part of the
    answer, not an error.
    """
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


class _DummyAsyncPostgresSaver:
    def __init__(self, pool):
        self.pool = pool

    async def setup(self):
        return None


class _DummyAsyncConnectionPool:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs

    async def open(self):
        return None

    async def close(self):
        return None


def _stub_langgraph_postgres() -> None:
    postgres = types.ModuleType("langgraph.checkpoint.postgres")
    aio = types.ModuleType("langgraph.checkpoint.postgres.aio")
    aio.AsyncPostgresSaver = _DummyAsyncPostgresSaver
    postgres.aio = aio
    sys.modules["langgraph.checkpoint.postgres"] = postgres
    sys.modules["langgraph.checkpoint.postgres.aio"] = aio


def _stub_psycopg() -> None:
    psycopg = types.ModuleType("psycopg")
    rows = types.ModuleType("psycopg.rows")
    rows.dict_row = object()
    psycopg.rows = rows
    sys.modules["psycopg"] = psycopg
    sys.modules["psycopg.rows"] = rows


def _stub_psycopg_pool() -> None:
    pool = types.ModuleType("psycopg_pool")
    pool.AsyncConnectionPool = _DummyAsyncConnectionPool
    sys.modules["psycopg_pool"] = pool


# Executed at conftest import — before pytest imports any test module in this package,
# which is the whole point. Each dependency is checked independently: a machine can have
# psycopg (SQLAlchemy needs it) without langgraph-checkpoint-postgres.
if not _is_installed("langgraph.checkpoint.postgres"):
    _stub_langgraph_postgres()

if not _is_installed("psycopg"):
    _stub_psycopg()

if not _is_installed("psycopg_pool"):
    _stub_psycopg_pool()
