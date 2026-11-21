"""Outbound borrower messages. Only called after a human approved the draft."""

from __future__ import annotations

from typing import Protocol

import httpx

from app.data.repository import Repository
from app.domain.models import Loan


class Notifier(Protocol):
    async def send(self, loan: Loan, body: str) -> bool: ...


class OutboxNotifier:
    """Dev/demo: records the message instead of sending it."""

    def __init__(self, repo: Repository) -> None:
        self.repo = repo

    async def send(self, loan: Loan, body: str) -> bool:
        async with self.repo.session() as s:
            await s.add_outbox(loan.id, "outbox", body)
        return True


class TelegramNotifier:
    """Sends via the Telegram Bot API to the borrower's linked chat (falls back to outbox)."""

    def __init__(self, repo: Repository, bot_token: str, timeout_s: float) -> None:
        self.bot_token = bot_token
        self.timeout_s = timeout_s
        self.fallback = OutboxNotifier(repo)

    async def send(self, loan: Loan, body: str) -> bool:
        if not loan.telegram_chat_id:
            return await self.fallback.send(loan, body)
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        try:
            async with httpx.AsyncClient(timeout=self.timeout_s) as http:
                r = await http.post(url, json={"chat_id": loan.telegram_chat_id, "text": body})
            return r.status_code == 200
        except httpx.HTTPError:
            return False  # draft stays APPROVED (not SENT); visible for retry
