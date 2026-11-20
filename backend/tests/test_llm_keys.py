"""Provider API keys: loaded from the environment or a local .env, resolved only by Settings,
required at startup, masked everywhere, and never leaked in errors.

Regression: keys in backend/.env used to be invisible to the LLM client (it read os.environ,
while pydantic-settings only loads .env into its own fields)."""

import json
import os

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from app.core.config import ProviderConfig, Settings, load_env_file
from app.llm.client import LLMError, OpenAICompatLLM

VAR = "LOANLOOP_TEST_PROVIDER_KEY"
PROVIDER = ProviderConfig(
    name="gemini", base_url="https://llm.example.test/v1", model="m", api_key_env=VAR
)
FAKE_KEY = "test-" + "k" * 24  # not a real key format; built so the secret scanner stays quiet


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    monkeypatch.delenv(VAR, raising=False)
    yield
    os.environ.pop(VAR, None)  # load_dotenv writes os.environ directly


def make_settings() -> Settings:
    return Settings(
        _env_file=None,
        env="dev",
        llm_mode="providers",
        llm_providers_json=json.dumps([PROVIDER.model_dump()]),
        principals_json="",
        demo_data_path="",
    )


def test_key_in_dotenv_file_reaches_settings(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(f"{VAR} = {FAKE_KEY}\n", encoding="utf-8")  # spaces around '=' are fine
    load_env_file(env_file)
    key = make_settings().provider_api_key(PROVIDER)
    assert key is not None and key.get_secret_value() == FAKE_KEY


def test_real_environment_variable_wins_over_dotenv(tmp_path, monkeypatch):
    monkeypatch.setenv(VAR, "from-real-env-" + "x" * 10)
    env_file = tmp_path / ".env"
    env_file.write_text(f"{VAR}={FAKE_KEY}\n", encoding="utf-8")
    load_env_file(env_file)
    assert make_settings().provider_api_key(PROVIDER).get_secret_value().startswith("from-real")


def test_missing_key_stops_startup_and_names_the_variable():
    with pytest.raises(ValidationError, match=f"{VAR} is not set"):
        make_settings()


def test_key_is_masked_when_printed(monkeypatch):
    monkeypatch.setenv(VAR, FAKE_KEY)
    s = make_settings()
    assert str(s.provider_api_key(PROVIDER)) == "**********"
    assert FAKE_KEY not in repr(s) and FAKE_KEY not in str(s.model_dump())


async def test_client_sends_key_and_never_leaks_it_in_errors():
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("Authorization", "")
        return httpx.Response(401, json={"error": "bad key"})

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = OpenAICompatLLM(PROVIDER, api_key=SecretStr(FAKE_KEY), timeout_s=5, http=http)
    with pytest.raises(LLMError) as err:
        await client.chat([{"role": "user", "content": "hi"}])
    assert seen["auth"] == f"Bearer {FAKE_KEY}"
    assert FAKE_KEY not in str(err.value)


async def test_keyless_provider_sends_no_authorization_header():
    seen: dict[str, bool] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["has_auth"] = "Authorization" in request.headers
        return httpx.Response(200, json={"model": "m", "choices": [{"message": {"content": "ok"}}]})

    local = ProviderConfig(name="ollama", base_url="http://localhost:11434/v1", model="m")
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    result = await OpenAICompatLLM(local, api_key=None, timeout_s=5, http=http).chat(
        [{"role": "user", "content": "hi"}]
    )
    assert result.content == "ok" and seen["has_auth"] is False
