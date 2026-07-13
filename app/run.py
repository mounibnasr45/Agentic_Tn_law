"""Dev server entrypoint.

    python -m app.run

Why this exists rather than `uvicorn app.main:app`:

psycopg's async mode cannot run on Windows' ProactorEventLoop. Every database call fails
with `psycopg.InterfaceError: Psycopg cannot use the 'ProactorEventLoop'`, while /health
cheerfully reports the model as loaded — because loading a model needs no database. So the
service looks up and is completely broken.

The usual fix, `asyncio.set_event_loop_policy(WindowsSelectorEventLoopPolicy())`, DOES NOT
WORK under uvicorn. As of 0.36 uvicorn stopped consulting the policy and builds its loop
from a factory instead (uvicorn/loops/asyncio.py):

    def asyncio_loop_factory(use_subprocess=False):
        if sys.platform == "win32" and not use_subprocess:
            return asyncio.ProactorEventLoop      # <- ignores the policy entirely
        return asyncio.SelectorEventLoop

So we drive the Server ourselves and hand it a loop we control. asyncio.run() honours the
policy, so the loop is a SelectorEventLoop and psycopg works.

None of this affects Linux, which is what the container and CI run — which is exactly why
it is easy to ship broken and only discover it on a developer's laptop.
"""
import asyncio
import os

from uvicorn import Config, Server

from app.core.config import get_settings
from app.core.runtime import configure_event_loop


def main() -> None:
    configure_event_loop()  # WindowsSelectorEventLoopPolicy on win32, no-op elsewhere
    settings = get_settings()

    config = Config(
        "app.main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
        # ONE worker. Each uvicorn worker is a separate process holding its own copy of
        # the ~450MB embedding model: --workers 4 on a 512MB tier is an instant OOM, and
        # the work is I/O-bound against Postgres and an LLM anyway. Scale with replicas
        # behind a reverse proxy. Knowing WHY this is 1 beats setting it to 4.
        workers=1,
        log_config=None,  # structlog owns logging; uvicorn's dictConfig would clobber it
        reload=settings.log_level.upper() == "DEBUG",
    )

    # NOT uvicorn.run(): that calls asyncio.run(..., loop_factory=...) with the factory
    # above, which forces a ProactorEventLoop on Windows regardless of the policy. Calling
    # asyncio.run() ourselves means the policy we just set is the one that applies.
    asyncio.run(Server(config).serve())


if __name__ == "__main__":
    main()
