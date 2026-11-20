from __future__ import annotations

from app.core.config import Settings
from app.llm.client import LLM, FallbackLLM, OpenAICompatLLM
from app.llm.fake import OfflineLLM


def build_llm(settings: Settings) -> LLM:
    if settings.llm_mode == "offline":
        return OfflineLLM()
    providers = settings.providers
    if not providers:
        raise RuntimeError("LOANLOOP_LLM_MODE=providers but LOANLOOP_LLM_PROVIDERS_JSON is empty")
    return FallbackLLM(
        [
            OpenAICompatLLM(
                p, api_key=settings.provider_api_key(p), timeout_s=settings.llm_timeout_s
            )
            for p in providers
        ]
    )
