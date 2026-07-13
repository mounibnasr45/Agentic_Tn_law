"""Test-suite setup.

pytest-asyncio builds its own event loop, so the configure_event_loop() call in the
application entrypoints never reaches it. Setting the policy here — at conftest import,
before any loop is created — makes the async database tests runnable on Windows.
No-op on Linux, where CI runs.
"""
from app.core.runtime import configure_event_loop

configure_event_loop()
