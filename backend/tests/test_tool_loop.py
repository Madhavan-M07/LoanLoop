import json

from app.agents.tool_loop import ToolError, ToolSpec, run_tool_agent
from app.domain.models import Principal, Scope
from app.llm.client import LLMError
from app.llm.fake import ScriptedLLM, text, tool_call
from pydantic import BaseModel

PROC = Principal(subject="proc", scope=Scope.PROCESSOR, org_id="acme")
BORR = Principal(subject="bor", scope=Scope.BORROWER, org_id="acme", loan_id="L-1001")


class Args(BaseModel):
    loan_id: str


calls: list[tuple[str, str]] = []


async def handler(a: Args, p: Principal):
    calls.append((a.loan_id, p.subject))
    if a.loan_id == "L-404":
        raise ToolError("loan L-404 not found")
    if a.loan_id == "L-500":
        raise RuntimeError("db password=hunter2")  # must never reach the model
    return {"loan_id": a.loan_id, "stage": "collecting_documents"}


TOOL = ToolSpec("get_loan", "Get a loan", Args, handler, frozenset({Scope.PROCESSOR}))
audit_log: list[tuple[str, str]] = []


def audit(action, p, status):
    audit_log.append((action, status))


def tool_messages(llm):
    return [m for m in llm.calls[-1]["messages"] if m["role"] == "tool"]


async def run(llm, principal=PROC, **kw):
    return await run_tool_agent(
        llm, system="s", user_message="q", tools=[TOOL], principal=principal, audit=audit, **kw
    )


async def test_happy_path_tool_then_answer():
    llm = ScriptedLLM(
        [tool_call("get_loan", {"loan_id": "L-1001"}), text("It is collecting docs.")]
    )
    r = await run(llm)
    assert r.answer == "It is collecting docs." and r.steps == [
        {"tool": "get_loan", "status": "ok"}
    ]
    assert ("L-1001", "proc") in calls
    assert json.loads(tool_messages(llm)[0]["content"])["stage"] == "collecting_documents"


async def test_unknown_tool_is_rejected_and_model_can_recover():
    r = await run(ScriptedLLM([tool_call("approve_loan", {}), text("I can't do that.")]))
    assert r.steps[0]["status"] == "unknown_tool" and r.stopped == "answered"


async def test_invalid_arguments_are_rejected():
    r = await run(ScriptedLLM([tool_call("get_loan", '{"loan": 1}'), text("sorry")]))
    assert r.steps[0]["status"] == "invalid_args"


async def test_tool_not_offered_outside_scope():
    llm = ScriptedLLM([tool_call("get_loan", {"loan_id": "L-1001"}), text("no")])
    r = await run(llm, principal=BORR)
    assert llm.calls[0]["tools"] is None  # borrower is never shown processor tools
    assert r.steps[0]["status"] == "unknown_tool"


async def test_internal_errors_do_not_leak():
    llm = ScriptedLLM([tool_call("get_loan", {"loan_id": "L-500"}), text("error")])
    r = await run(llm)
    assert r.steps[0]["status"] == "internal_error"
    assert "hunter2" not in tool_messages(llm)[0]["content"]


async def test_expected_tool_error_is_returned_to_model():
    llm = ScriptedLLM([tool_call("get_loan", {"loan_id": "L-404"}), text("not found")])
    await run(llm)
    assert "not found" in tool_messages(llm)[0]["content"]


async def test_max_steps_stops_a_looping_model():
    r = await run(ScriptedLLM([tool_call("get_loan", {"loan_id": "L-1"})] * 3), max_steps=3)
    assert r.stopped == "max_steps"


async def test_llm_outage_returns_safe_message():
    r = await run(ScriptedLLM([LLMError("down")]))
    assert r.stopped == "llm_error" and "unavailable" in r.answer


async def test_every_call_is_audited():
    audit_log.clear()
    await run(ScriptedLLM([tool_call("get_loan", {"loan_id": "L-1"}), text("ok")]))
    assert audit_log == [("tool:get_loan", "ok")]
