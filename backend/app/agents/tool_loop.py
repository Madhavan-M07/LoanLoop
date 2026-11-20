"""Generic tool-calling agent loop.

The model never executes anything: it *requests* a tool call; this loop checks the request
(allowlist, scope, argument schema), runs our code with the caller's identity taken from
authentication, and returns the result. Every failure is returned to the model as a tool
result so it can recover, and every call is audited.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ValidationError

from app.domain.models import Principal, Scope
from app.llm.client import LLM, LLMError

Handler = Callable[[Any, Principal], Awaitable[Any]]
AuditFn = Callable[[str, Principal, str], None]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    args_model: type[BaseModel]
    handler: Handler
    scopes: frozenset[Scope]

    def schema(self) -> dict[str, Any]:
        params = self.args_model.model_json_schema()
        params.pop("title", None)
        return {
            "type": "function",
            "function": {"name": self.name, "description": self.description, "parameters": params},
        }


@dataclass
class AgentRun:
    answer: str
    steps: list[dict[str, str]] = field(default_factory=list)
    stopped: str = "answered"  # answered | max_steps | llm_error


class ToolError(Exception):
    """Expected, user-safe tool failure (e.g. not found, forbidden)."""


def _dump(result: Any) -> str:
    if isinstance(result, BaseModel):
        return result.model_dump_json()
    if isinstance(result, list):
        return json.dumps(
            [r.model_dump(mode="json") if isinstance(r, BaseModel) else r for r in result]
        )
    return json.dumps(result, default=str)


async def run_tool_agent(
    llm: LLM,
    *,
    system: str,
    user_message: str,
    tools: list[ToolSpec],
    principal: Principal,
    audit: AuditFn,
    max_steps: int = 5,
) -> AgentRun:
    allowed = {t.name: t for t in tools if principal.scope in t.scopes}  # least privilege
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_message},
    ]
    run = AgentRun(answer="")
    for _ in range(max_steps):
        try:
            res = await llm.chat(messages, tools=[t.schema() for t in allowed.values()] or None)
        except LLMError:
            run.stopped = "llm_error"
            run.answer = "Sorry, the assistant is unavailable right now. Please try again shortly."
            return run
        messages.append(res.as_message())
        if not res.tool_calls:
            run.answer = res.content or ""
            return run
        for call in res.tool_calls:
            status = "ok"
            spec = allowed.get(call.name)
            if spec is None:
                status, content = "unknown_tool", json.dumps({"error": f"unknown tool {call.name}"})
            else:
                try:
                    args = spec.args_model.model_validate_json(call.arguments or "{}")
                    content = _dump(await spec.handler(args, principal))
                except ValidationError as e:
                    status = "invalid_args"
                    content = json.dumps(
                        {
                            "error": "invalid arguments",
                            "details": e.errors(include_url=False, include_input=False)[:5],
                        },
                        default=str,
                    )
                except ToolError as e:
                    status, content = "tool_error", json.dumps({"error": str(e)})
                except Exception as e:  # never leak internals to the model
                    status = "internal_error"
                    content = json.dumps({"error": f"internal error ({type(e).__name__})"})
            audit(f"tool:{call.name}", principal, status)
            run.steps.append({"tool": call.name, "status": status})
            messages.append({"role": "tool", "tool_call_id": call.id, "content": content})
    run.stopped = "max_steps"
    run.answer = "I couldn't complete that. A processor will follow up."
    return run
