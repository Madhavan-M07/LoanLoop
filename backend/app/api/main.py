"""LoanLoop REST API. Thin routes: auth -> use-case -> response. Domain errors map to HTTP once.

NOTE: no `from __future__ import annotations` here. FastAPI must resolve the locally defined
`P` dependency at definition time; string annotations made it a query param (bug found by tests).
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.core.config import Settings, get_settings
from app.data.db import Database
from app.data.postgres import PostgresRepository
from app.data.repository import Repository
from app.data.store import Store, load_loans, load_orgs, utc_now
from app.domain.models import (
    AuditEvent,
    Document,
    LenderPolicy,
    LoanStatus,
    MessageDraft,
    Principal,
)
from app.integrations.notifier import Notifier, OutboxNotifier, TelegramNotifier
from app.llm.client import LLM
from app.llm.factory import build_llm
from app.services import assistant, loans, policy
from app.services.access import Forbidden, NotFound, get_loan_for, require_processor
from app.services.pipeline import PipelineConfig, process_document


@dataclass
class AppState:
    settings: Settings
    store: Repository
    llm: LLM
    notifier: Notifier
    principals: dict[str, Principal]
    db: Database | None


class UploadIn(BaseModel):
    filename: str = Field(min_length=1, max_length=120)
    text: str = Field(
        min_length=1, max_length=50_000
    )  # Phase 1: OCR'd/plain text; files + OCR next


class DraftIn(BaseModel):
    loan_id: str
    body: str = Field(min_length=10, max_length=1500)


class AskIn(BaseModel):
    question: str = Field(min_length=2, max_length=1000)


class AskOut(BaseModel):
    answer: str
    steps: list[dict[str, str]]
    stopped: str


def create_app(
    *,
    settings: Settings | None = None,
    store: Repository | None = None,
    llm: LLM | None = None,
    notifier: Notifier | None = None,
) -> FastAPI:
    """Storage: an explicit `store` (tests) wins; else PostgreSQL when LOANLOOP_DATABASE_URL is
    set (data survives restarts; load demo data once with `python -m app.data.seed`); else an
    in-memory store with the demo file (dev only: prod refuses to start without a database)."""
    settings = settings or get_settings()
    db = (
        Database(settings.database_url.get_secret_value(), settings.database_timeout_s)
        if settings.database_url
        else None
    )
    if store is None:
        if db is not None:
            store = PostgresRepository(db.engine, utc_now)
        else:
            memory = Store()
            demo = settings.demo_data()  # None unless LOANLOOP_DEMO_DATA_PATH is set (dev/test)
            if demo:
                load_orgs(memory, demo.get("organizations", []))
                load_loans(memory, demo.get("loans", []))
            store = memory
    pipeline_cfg = PipelineConfig(
        min_classify_confidence=settings.classify_min_confidence,
        max_document_chars=settings.max_document_chars,
    )
    state = AppState(
        settings=settings,
        store=store,
        llm=llm or build_llm(settings),
        notifier=notifier
        or (
            TelegramNotifier(store, settings.telegram_bot_token, settings.notifier_timeout_s)
            if settings.telegram_bot_token
            else OutboxNotifier(store)
        ),
        principals=settings.principals(),
        db=db,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        if state.db is not None:
            await state.db.dispose()  # close pooled connections on shutdown

    app = FastAPI(title="LoanLoop API", version="0.1.0", lifespan=lifespan)

    @app.exception_handler(NotFound)
    async def _nf(_: Request, e: NotFound) -> JSONResponse:
        return JSONResponse({"detail": str(e)}, status_code=404)

    @app.exception_handler(Forbidden)
    async def _fb(_: Request, e: Forbidden) -> JSONResponse:
        return JSONResponse({"detail": str(e)}, status_code=403)

    def principal(authorization: Annotated[str | None, Header()] = None) -> Principal:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(401, "missing bearer token")
        p = state.principals.get(authorization.removeprefix("Bearer ").strip())
        if p is None:
            raise HTTPException(401, "invalid token")
        return p

    P = Annotated[Principal, Depends(principal)]

    @app.get("/health")
    async def health() -> dict[str, str]:
        db = "not_configured" if state.db is None else await state.db.ping()
        return {"status": "ok", "llm_mode": settings.llm_mode, "database": db}

    @app.get("/me")
    async def me(p: P) -> Principal:
        return p

    @app.get("/loans")
    async def list_loans(p: P) -> list[loans.LoanSummary]:
        return await loans.list_loans(store, p)

    @app.get("/loans/stuck")
    async def stuck(p: P, min_days: int | None = None) -> list[loans.LoanSummary]:
        return await loans.stuck_files(store, p, min_days or settings.stuck_after_days)

    @app.get("/loans/{loan_id}/status")
    async def status(p: P, loan_id: str) -> LoanStatus:
        return await loans.loan_status(store, p, loan_id)

    @app.get("/loans/{loan_id}")
    async def loan_file(p: P, loan_id: str) -> loans.LoanFile:
        return await loans.loan_file(store, p, loan_id)

    @app.post("/loans/{loan_id}/documents", status_code=201)
    async def upload(p: P, loan_id: str, body: UploadIn) -> Document:
        async with store.session() as s:
            loan = await get_loan_for(s, p, loan_id)
        doc = await process_document(
            store,
            state.llm,
            loan,
            filename=body.filename,
            text=body.text,
            uploaded_by=p.subject,
            cfg=pipeline_cfg,
        )
        assert doc is not None
        return doc.model_copy(update={"fields": None}) if p.via_agent else doc

    @app.get("/drafts")
    async def drafts(p: P) -> list[MessageDraft]:
        return await loans.pending_drafts(store, p)

    @app.post("/drafts", status_code=201)
    async def create_draft(p: P, body: DraftIn) -> MessageDraft:
        return await loans.create_draft(store, p, body.loan_id, body.body)

    @app.post("/drafts/{draft_id}/approve")
    async def approve(p: P, draft_id: str) -> MessageDraft:
        return await loans.approve_draft(store, p, draft_id, state.notifier)

    @app.post("/drafts/{draft_id}/reject")
    async def reject(p: P, draft_id: str) -> MessageDraft:
        return await loans.reject_draft(store, p, draft_id)

    @app.post("/assistant/ask")
    async def ask(p: P, body: AskIn) -> AskOut:
        require_processor(p)
        run = await assistant.ask(
            store,
            state.llm,
            p,
            body.question,
            max_steps=settings.agent_max_steps,
            stuck_after_days=settings.stuck_after_days,
        )
        return AskOut(answer=run.answer, steps=run.steps, stopped=run.stopped)

    @app.get("/audit")
    async def audit(p: P, loan_id: str | None = None) -> list[AuditEvent]:
        require_processor(p)
        async with store.session() as s:
            if loan_id:
                await get_loan_for(s, p, loan_id)  # tenant check before reading its history
            return await s.audit_events(p.org_id, loan_id)

    @app.get("/org/policy")
    async def read_policy(p: P) -> LenderPolicy:
        return await policy.get_policy(store, p)

    @app.put("/org/policy")
    async def replace_policy(p: P, body: LenderPolicy) -> LenderPolicy:
        return await policy.update_policy(store, state.llm, p, body)

    return app


def app_factory() -> FastAPI:  # uvicorn --factory app.api.main:app_factory
    return create_app()
