# Copyright (c) Microsoft. All rights reserved.

"""Tests for request authentication in the M365 agent sample.

The M365 Agents SDK hosting packages come from the sample's PEP 723 header, not the
workspace, so these tests are skipped unless they are installed.
"""

import importlib.util
import time
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

pytest.importorskip("microsoft_agents.hosting.aiohttp")
pytest.importorskip("microsoft_agents.authentication.msal")

import jwt  # noqa: E402
from aiohttp import web  # noqa: E402
from aiohttp.test_utils import TestClient, TestServer  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: E402
from microsoft_agents.activity import load_configuration_from_env  # noqa: E402
from microsoft_agents.hosting.core.authorization.jwt import JwtTokenValidator  # noqa: E402

_APP_PATH = Path(__file__).parents[3] / "samples" / "05-end-to-end" / "m365-agent" / "m365_agent_demo" / "app.py"

_CLIENT_ID = "11111111-1111-1111-1111-111111111111"
_BOT_FRAMEWORK_ISSUER = "https://api.botframework.com"
_ACTIVITY = {"type": "message", "text": "What's the weather in Seattle?"}


def _load_app_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("m365_agent_demo_app", _APP_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sign(key: rsa.RSAPrivateKey, audience: str) -> str:
    now = int(time.time())
    claims = {"aud": audience, "iss": _BOT_FRAMEWORK_ISSUER, "iat": now, "nbf": now, "exp": now + 600}
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": "test-key"})


@pytest.fixture
def trusted_key(monkeypatch: pytest.MonkeyPatch) -> rsa.RSAPrivateKey:
    """Serve a local signing key instead of fetching the Bot Framework JWKS."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    signing_key = jwt.PyJWK.from_dict(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key(), as_dict=True))

    async def get_signing_key(_jwks_uri: str, _header: dict[str, Any]) -> jwt.PyJWK:
        return signing_key

    monkeypatch.setattr(JwtTokenValidator._jwk_client_manager, "get_signing_key", get_signing_key)
    return key


@pytest.fixture
def app_module(monkeypatch: pytest.MonkeyPatch) -> tuple[ModuleType, list[Any]]:
    """Load the sample with the agent and SDK turn processing replaced by recorders."""
    monkeypatch.setenv("FOUNDRY_PROJECT_ENDPOINT", "https://example.services.ai.azure.com/api/projects/test")
    monkeypatch.setenv("FOUNDRY_MODEL", "test-model")
    module = _load_app_module()
    processed: list[Any] = []

    async def start_agent_process(request: web.Request, _agent_app: Any, _adapter: Any) -> web.Response:
        processed.append(request["claims_identity"])
        return web.Response(status=202)

    monkeypatch.setattr(module, "build_agent", lambda: object())
    monkeypatch.setattr(module, "start_agent_process", start_agent_process)
    return module, processed


def _config(module: ModuleType, *, use_anonymous_mode: bool) -> Any:
    env = {
        "CONNECTIONS__SERVICE_CONNECTION__SETTINGS__CLIENTID": _CLIENT_ID,
        "CONNECTIONS__SERVICE_CONNECTION__SETTINGS__CLIENTSECRET": "secret",
        "CONNECTIONS__SERVICE_CONNECTION__SETTINGS__TENANTID": "22222222-2222-2222-2222-222222222222",
    }
    return module.AppConfig(
        use_anonymous_mode=use_anonymous_mode,
        port=0,
        agents_sdk_config=load_configuration_from_env(env),
    )


async def _post_activity(app: web.Application, headers: dict[str, str]) -> int:
    async with TestClient(TestServer(app)) as client:
        response = await client.post("/api/messages", json=_ACTIVITY, headers=headers)
        return response.status


@pytest.mark.parametrize(
    "headers",
    [
        pytest.param({}, id="missing"),
        pytest.param({"Authorization": "Basic dXNlcjpwYXNz"}, id="not-bearer"),
        pytest.param({"Authorization": "Bearer not-a-jwt"}, id="malformed"),
    ],
)
async def test_authenticated_mode_rejects_requests_without_a_valid_token(
    app_module: tuple[ModuleType, list[Any]], headers: dict[str, str]
) -> None:
    module, processed = app_module
    app = module.create_app(_config(module, use_anonymous_mode=False))

    assert await _post_activity(app, headers) == 401
    assert processed == []


async def test_authenticated_mode_rejects_token_signed_by_untrusted_key(
    app_module: tuple[ModuleType, list[Any]], trusted_key: rsa.RSAPrivateKey
) -> None:
    module, processed = app_module
    app = module.create_app(_config(module, use_anonymous_mode=False))
    untrusted_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    status = await _post_activity(app, {"Authorization": f"Bearer {_sign(untrusted_key, _CLIENT_ID)}"})

    assert status == 401
    assert processed == []


async def test_authenticated_mode_rejects_token_for_another_audience(
    app_module: tuple[ModuleType, list[Any]], trusted_key: rsa.RSAPrivateKey
) -> None:
    module, processed = app_module
    app = module.create_app(_config(module, use_anonymous_mode=False))

    status = await _post_activity(app, {"Authorization": f"Bearer {_sign(trusted_key, 'another-app')}"})

    assert status == 401
    assert processed == []


async def test_authenticated_mode_accepts_valid_token(
    app_module: tuple[ModuleType, list[Any]], trusted_key: rsa.RSAPrivateKey
) -> None:
    module, processed = app_module
    app = module.create_app(_config(module, use_anonymous_mode=False))

    status = await _post_activity(app, {"Authorization": f"Bearer {_sign(trusted_key, _CLIENT_ID)}"})

    assert status == 202
    assert [identity.get_claim_value("aud") for identity in processed] == [_CLIENT_ID]


async def test_anonymous_mode_accepts_requests_without_a_token(app_module: tuple[ModuleType, list[Any]]) -> None:
    module, processed = app_module
    app = module.create_app(_config(module, use_anonymous_mode=True))

    assert await _post_activity(app, {}) == 202
    assert len(processed) == 1
    assert processed[0].allow_anonymous


async def test_health_endpoint_does_not_require_a_token(app_module: tuple[ModuleType, list[Any]]) -> None:
    module, _ = app_module
    app = module.create_app(_config(module, use_anonymous_mode=False))

    async with TestClient(TestServer(app)) as client:
        response = await client.get("/api/health")

    assert response.status == 200
