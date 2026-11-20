"""Provider-agnostic LLM client (OpenAI-compatible chat completions).

Gemini, Groq, OpenRouter and Ollama all expose an OpenAI-compatible endpoint, so one client
covers every free tier. Agents depend on the `LLM` protocol only, never on a vendor SDK.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from app.core.config import ProviderConfig


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: str  # raw JSON string exactly as the model produced it (untrusted)


@dataclass
class ChatResult:
    content: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)
    model: str = ""
    usage: dict[str, int] = field(default_factory=dict)

    def as_message(self) -> dict[str, Any]:
        msg: dict[str, Any] = {"role": "assistant", "content": self.content}
        if self.tool_calls:
            msg["tool_calls"] = [
                {
                    "id": c.id,
                    "type": "function",
                    "function": {"name": c.name, "arguments": c.arguments},
                }
                for c in self.tool_calls
            ]
        return msg


class LLMError(Exception):
    """Provider failure (timeout, rate limit, 5xx, malformed response)."""


class LLM(Protocol):
    async def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        json_mode: bool = False,
    ) -> ChatResult: ...


class OpenAICompatLLM:
    def __init__(
        self, cfg: ProviderConfig, timeout_s: float = 30.0, http: httpx.AsyncClient | None = None
    ) -> None:
        self.cfg = cfg
        self.timeout_s = timeout_s
        self._http = http

    async def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        json_mode: bool = False,
    ) -> ChatResult:
        body: dict[str, Any] = {"model": self.cfg.model, "messages": messages, "temperature": 0}
        if tools:
            body["tools"] = tools
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        headers = {}
        if self.cfg.api_key_env:
            key = os.environ.get(self.cfg.api_key_env, "")
            if not key:
                raise LLMError(f"{self.cfg.name}: env var {self.cfg.api_key_env} not set")
            headers["Authorization"] = f"Bearer {key}"
        url = self.cfg.base_url.rstrip("/") + "/chat/completions"
        try:
            if self._http:
                r = await self._http.post(url, json=body, headers=headers, timeout=self.timeout_s)
            else:
                async with httpx.AsyncClient() as http:
                    r = await http.post(url, json=body, headers=headers, timeout=self.timeout_s)
        except httpx.HTTPError as e:
            raise LLMError(f"{self.cfg.name}: {type(e).__name__}") from e
        if r.status_code >= 400:
            raise LLMError(f"{self.cfg.name}: HTTP {r.status_code}")
        try:
            data = r.json()
            msg = data["choices"][0]["message"]
            calls = [
                ToolCall(
                    id=c["id"],
                    name=c["function"]["name"],
                    arguments=c["function"].get("arguments") or "{}",
                )
                for c in (msg.get("tool_calls") or [])
            ]
            return ChatResult(
                content=msg.get("content"),
                tool_calls=calls,
                model=data.get("model", self.cfg.model),
                usage=data.get("usage") or {},
            )
        except (KeyError, IndexError, ValueError, TypeError) as e:
            raise LLMError(f"{self.cfg.name}: malformed response") from e


class FallbackLLM:
    """Try providers in order; move on when one is rate-limited, down or misconfigured."""

    def __init__(self, providers: list[LLM]) -> None:
        if not providers:
            raise ValueError("FallbackLLM needs at least one provider")
        self.providers = providers

    async def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        json_mode: bool = False,
    ) -> ChatResult:
        errors: list[str] = []
        for p in self.providers:
            try:
                return await p.chat(messages, tools=tools, json_mode=json_mode)
            except LLMError as e:
                errors.append(str(e))
        raise LLMError("all providers failed: " + "; ".join(errors))


def parse_json_object(text: str | None) -> dict[str, Any]:
    """Parse a model's JSON reply, tolerating ```json fences. Raises ValueError."""
    if not text:
        raise ValueError("empty response")
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`")
        t = t[t.find("{") :]
    obj = json.loads(t[t.find("{") : t.rfind("}") + 1])
    if not isinstance(obj, dict):
        raise ValueError("not a JSON object")
    return obj
