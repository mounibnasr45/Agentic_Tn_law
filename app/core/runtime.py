"""Event-loop policy fix so psycopg's async mode works on Windows, where the
default ProactorEventLoop cannot run it."""
import asyncio
import sys


def configure_event_loop() -> None:
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
