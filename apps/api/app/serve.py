"""Entry point: `python -m app.serve`.

psycopg's async driver cannot run on Windows' default Proactor event loop, so we start uvicorn on
a selector loop explicitly. On Linux/macOS this is equivalent to `uvicorn app.main:app`.
"""

from __future__ import annotations

import asyncio
import os
import sys

import uvicorn


def main() -> None:
    config = uvicorn.Config(
        "app.main:app",
        host=os.getenv("API_HOST", "127.0.0.1"),
        port=int(os.getenv("API_PORT", "8100")),
        proxy_headers=True,
        log_level=os.getenv("LOG_LEVEL", "info").lower(),
    )
    server = uvicorn.Server(config)
    if sys.platform == "win32":
        asyncio.run(server.serve(), loop_factory=asyncio.SelectorEventLoop)
    else:
        asyncio.run(server.serve())


if __name__ == "__main__":
    main()
