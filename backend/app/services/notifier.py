"""Outbound borrower messages. Only called after a human approved the draft."""

from __future__ import annotations

from typing import Protocol

import httpx

from app.domain.models import Loan
from app.services.store import Store


class Notifier(Protocol):
    async def send(self, loan: Loan, body: str) -> bool: ...


class OutboxNotifier:
    """Dev/demo: records the message instead of sending it."""

    def __init__(self, store: Store) -> None:
        self.store = store

    async def send(self, loan: Loan, body: str) -> bool:
        self.store.outbox.append({"loan_id": loan.id, "channel": "outbox", "body": body})
        return True


class TelegramNotifier:
    """Sends via the Telegram Bot API to the borrower's linked chat (falls back to outbox)."""

    def __init__(self, store: Store, bot_token: str) -> None:
        self.store = store
        self.bot_token = bot_token
        self.fallback = OutboxNotifier(store)

    async def send(self, loan: Loan, body: str) -> bool:
        if not loan.telegram_chat_id:
            return await self.fallback.send(loan, body)
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        try:
            async with httpx.AsyncClient(timeout=10) as http:
                r = await http.post(url, json={"chat_id": loan.telegram_chat_id, "text": body})
            return r.status_code == 200
        except httpx.HTTPError:
            return False  # draft stays APPROVED (not SENT); visible for retry
