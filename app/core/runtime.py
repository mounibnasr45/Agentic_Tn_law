"""Event-loop setup for async entrypoints.

Python on Windows defaults to ProactorEventLoop, which psycopg's async mode cannot use:

    psycopg.InterfaceError: Psycopg cannot use the 'ProactorEventLoop' to run in
    async mode.

Every async entrypoint must call configure_event_loop() before touching the database.
No-op on Linux and macOS, so CI and the container are unaffected — which is exactly why
this is easy to miss until a developer on Windows tries to run a migration.
"""
import asyncio
import sys


def configure_event_loop() -> None:
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
