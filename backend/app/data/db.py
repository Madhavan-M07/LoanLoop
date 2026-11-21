"""PostgreSQL connection (SQLAlchemy 2 async + asyncpg).

asyncpg rather than psycopg's async mode: psycopg async cannot run on Windows' default
(Proactor) event loop, and development happens on Windows.

Never put the URL, or a driver error message, into logs or responses: either may contain the
host or credentials. Callers get a plain status instead.
"""

from __future__ import annotations

import asyncio
from typing import Literal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

DbStatus = Literal["ok", "unavailable"]


class Database:
    def __init__(self, url: str, timeout_s: float) -> None:
        if not url.startswith("postgresql+asyncpg://"):
            # Checked here so a wrong driver fails at startup, without echoing the URL.
            raise ValueError("database URL must start with postgresql+asyncpg://")
        self.timeout_s = timeout_s
        # Creating the engine does not connect; connections open lazily on first use.
        self.engine: AsyncEngine = create_async_engine(
            url,
            pool_pre_ping=True,  # drop dead pooled connections (e.g. after a DB restart)
            connect_args={"timeout": timeout_s},  # asyncpg connect timeout, seconds
        )

    async def ping(self) -> DbStatus:
        """One round trip (`SELECT 1`), bounded by the timeout. Never raises."""
        try:
            async with asyncio.timeout(self.timeout_s):
                async with self.engine.connect() as conn:
                    await conn.execute(text("SELECT 1"))
            return "ok"
        except Exception:  # unreachable, refused, auth failure, timeout: all mean "unavailable"
            return "unavailable"

    async def dispose(self) -> None:
        await self.engine.dispose()
