"""The storage contract (app/data/repository.py), tested through the interface only.

Written against `repo` so the same tests run against PostgreSQL once it implements the
interface (step 3b). Today `repo` is the in-memory store from conftest.
"""

import asyncio

import pytest

from app.domain.models import DraftStatus, MessageDraft, Principal, Scope
from app.services import loans
from app.services.access import Forbidden


@pytest.fixture
def repo(store):
    return store


PROC = Principal(subject="proc-1", scope=Scope.PROCESSOR, org_id="acme")


async def test_reads_return_copies_so_unsaved_changes_are_lost(repo):
    async with repo.session() as s:
        loan = await s.get_loan("L-1001")
        loan.borrower_name = "CHANGED"  # not saved
    async with repo.session() as s:
        assert (await s.get_loan("L-1001")).borrower_name != "CHANGED"


async def test_saved_changes_are_visible_to_later_sessions(repo):
    async with repo.session() as s:
        loan = await s.get_loan("L-1001")
        loan.loan_officer = "lo-new"
        await s.save_loan(loan)
    async with repo.session() as s:
        assert (await s.get_loan("L-1001")).loan_officer == "lo-new"


async def test_lock_serializes_work_on_one_loan(repo):
    order: list[str] = []

    async def worker(name: str) -> None:
        async with repo.session() as s:
            await s.lock_loan("L-1001")
            order.append(f"{name}-start")
            await asyncio.sleep(0.02)  # yield: the other worker must still wait
            order.append(f"{name}-end")

    await asyncio.gather(worker("a"), worker("b"))
    assert order in (
        ["a-start", "a-end", "b-start", "b-end"],
        ["b-start", "b-end", "a-start", "a-end"],
    )


async def test_lock_is_released_when_the_session_fails(repo):
    with pytest.raises(RuntimeError):
        async with repo.session() as s:
            await s.lock_loan("L-1001")
            raise RuntimeError("boom")
    async with asyncio.timeout(1):  # would hang forever if the lock leaked
        async with repo.session() as s:
            assert await s.lock_loan("L-1001") is not None


async def test_lists_only_return_the_requested_organization(repo):
    async with repo.session() as s:
        acme = await s.list_loans("acme")
        assert acme and all(ln.org_id == "acme" for ln in acme)
        assert all(ln.org_id != "acme" for ln in await s.list_loans("beta"))


class SlowNotifier:
    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send(self, loan, body: str) -> bool:
        await asyncio.sleep(0.02)
        self.sent.append(body)
        return True


async def test_simultaneous_approvals_send_the_message_only_once(repo):
    """Two processors (or a double click) approving the same draft: exactly one send.

    NOTE: against the in-memory store this passes even WITHOUT the lock, because memory reads
    never yield between "still open?" and "mark approved" (checked by disabling the lock). It
    only proves the lock against Postgres, where every query yields: run it there in step 3b.
    """
    draft = MessageDraft(
        id="M-race",
        loan_id="L-1001",
        body="Please upload your latest paystub.",
        created_by="proc-1",
        created_at=repo.now(),
    )
    async with repo.session() as s:
        await s.save_draft(draft)
    notifier = SlowNotifier()

    outcomes = await asyncio.gather(
        loans.approve_draft(repo, PROC, "M-race", notifier),
        loans.approve_draft(repo, PROC, "M-race", notifier),
        return_exceptions=True,
    )

    assert len(notifier.sent) == 1
    assert sum(isinstance(o, Forbidden) for o in outcomes) == 1
    async with repo.session() as s:
        assert (await s.get_draft("M-race")).status == DraftStatus.SENT
