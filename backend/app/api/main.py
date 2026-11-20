"""LoanLoop REST API. Thin routes: auth -> use-case -> response. Domain errors map to HTTP once.

NOTE: no `from __future__ import annotations` here. FastAPI must resolve the locally defined
`P` dependency at definition time; string annotations made it a query param (bug found by tests).
"""

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.agents import assistant
from app.core.config import Settings, get_settings
from app.domain.models import (
    AuditEvent,
    Document,
    LenderPolicy,
    LoanStatus,
    MessageDraft,
    Principal,
)
from app.llm.client import LLM
from app.llm.factory import build_llm
from app.services import loans, policy
from app.services.access import Forbidden, NotFound, get_loan_for, require_processor
from app.services.notifier import Notifier, OutboxNotifier, TelegramNotifier
from app.services.pipeline import PipelineConfig, process_document
from app.services.store import Store, load_loans, load_orgs


@dataclass
class AppState:
    settings: Settings
    store: Store
    llm: LLM
    notifier: Notifier
    principals: dict[str, Principal]


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
    store: Store | None = None,
    llm: LLM | None = None,
    notifier: Notifier | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    if store is None:
        store = Store()
        demo = settings.demo_data()  # None unless LOANLOOP_DEMO_DATA_PATH is set (dev/test only)
        if demo:
            load_orgs(store, demo.get("organizations", []))
            load_loans(store, demo.get("loans", []))
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
    )

    app = FastAPI(title="LoanLoop API", version="0.1.0")
    app.state.ll = state

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
        return {"status": "ok", "llm_mode": settings.llm_mode}

    @app.get("/me")
    async def me(p: P) -> Principal:
        return p

    @app.get("/loans")
    async def list_loans(p: P) -> list[loans.LoanSummary]:
        return loans.list_loans(store, p)

    @app.get("/loans/stuck")
    async def stuck(p: P, min_days: int | None = None) -> list[loans.LoanSummary]:
        return loans.stuck_files(store, p, min_days or settings.stuck_after_days)

    @app.get("/loans/{loan_id}/status")
    async def status(p: P, loan_id: str) -> LoanStatus:
        return loans.loan_status(store, p, loan_id)

    @app.get("/loans/{loan_id}")
    async def loan_file(p: P, loan_id: str) -> loans.LoanFile:
        return loans.loan_file(store, p, loan_id)

    @app.post("/loans/{loan_id}/documents", status_code=201)
    async def upload(p: P, loan_id: str, body: UploadIn) -> Document:
        loan = get_loan_for(store, p, loan_id)
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
        return loans.pending_drafts(store, p)

    @app.post("/drafts", status_code=201)
    async def create_draft(p: P, body: DraftIn) -> MessageDraft:
        return loans.create_draft(store, p, body.loan_id, body.body)

    @app.post("/drafts/{draft_id}/approve")
    async def approve(p: P, draft_id: str) -> MessageDraft:
        return await loans.approve_draft(store, p, draft_id, state.notifier)

    @app.post("/drafts/{draft_id}/reject")
    async def reject(p: P, draft_id: str) -> MessageDraft:
        return loans.reject_draft(store, p, draft_id)

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
        if loan_id:
            get_loan_for(store, p, loan_id)
            return [e for e in store.audit_log if e.loan_id == loan_id]
        return [e for e in store.audit_log if e.org_id == p.org_id]

    @app.get("/org/policy")
    async def read_policy(p: P) -> LenderPolicy:
        return policy.get_policy(store, p)

    @app.put("/org/policy")
    async def replace_policy(p: P, body: LenderPolicy) -> LenderPolicy:
        return await policy.update_policy(store, state.llm, p, body)

    return app


def app_factory() -> FastAPI:  # uvicorn --factory app.api.main:app_factory
    return create_app()
