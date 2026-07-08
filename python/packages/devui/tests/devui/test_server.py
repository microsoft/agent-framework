# Copyright (c) Microsoft. All rights reserved.

"""Focused tests for server functionality."""

import asyncio
import inspect
import sys
import tempfile
from pathlib import Path
from typing import Any

import pytest
from conftest import MockAgent  # pyrefly: ignore[missing-import] # pyright: ignore[reportMissingImports]
from fastapi.testclient import TestClient

import agent_framework_devui
from agent_framework_devui import DevServer
from agent_framework_devui._utils import extract_executor_message_types, select_primary_input_type
from agent_framework_devui.models._openai_custom import AgentFrameworkRequest


class _StubExecutor:
    """Simple executor stub exposing handler metadata."""

    def __init__(self, *, input_types=None, handlers=None):
        if input_types is not None:
            self.input_types = list(input_types)
        if handlers is not None:
            self._handlers = dict(handlers)


# Note: test_entities_dir fixture is provided by conftest.py


async def test_server_health_endpoint(test_entities_dir):
    """Test /health endpoint."""
    server = DevServer(entities_dir=test_entities_dir)
    executor = await server._ensure_executor()

    # Test entity count
    entities = await executor.discover_entities()
    assert len(entities) > 0
    # Framework name is now hardcoded since we simplified to single framework


async def test_server_entities_endpoint(test_entities_dir):
    """Test /v1/entities endpoint."""
    server = DevServer(entities_dir=test_entities_dir)
    executor = await server._ensure_executor()

    entities = await executor.discover_entities()
    assert len(entities) >= 1
    # Should find at least one agent
    agent_entities = [e for e in entities if e.type == "agent"]
    assert len(agent_entities) >= 1, "Should discover at least one agent"
    # Verify agents have required properties
    for agent in agent_entities:
        assert agent.id, "Agent should have an ID"
        assert agent.name, "Agent should have a name"


async def test_server_execution_sync(test_entities_dir):
    """Test sync execution endpoint."""
    server = DevServer(entities_dir=test_entities_dir)
    executor = await server._ensure_executor()

    entities = await executor.discover_entities()
    agent_id = entities[0].id

    # Use metadata.entity_id for routing
    request = AgentFrameworkRequest(
        metadata={"entity_id": agent_id},
        input="San Francisco",
        stream=False,
    )

    response = await executor.execute_sync(request)
    assert response.model == "devui"  # Response model defaults to 'devui' when not specified
    assert len(response.output) > 0


async def test_server_execution_streaming(test_entities_dir):
    """Test streaming execution endpoint."""
    server = DevServer(entities_dir=test_entities_dir)
    executor = await server._ensure_executor()

    entities = await executor.discover_entities()
    agent_id = entities[0].id

    # Use metadata.entity_id for routing
    request = AgentFrameworkRequest(
        metadata={"entity_id": agent_id},
        input="New York",
        stream=True,
    )

    event_count = 0
    async for _event in executor.execute_streaming(request):
        event_count += 1
        if event_count > 5:  # Limit for testing
            break

    assert event_count > 0


def test_configuration():
    """Test basic configuration."""
    server = DevServer(entities_dir="test", port=9000, host="localhost", auth_enabled=False)
    assert server.port == 9000
    assert server.host == "localhost"
    assert server.entities_dir == "test"
    assert server.cors_origins == []
    assert server.ui_enabled


def test_extract_executor_message_types_prefers_input_types():
    """Input types property is used when available."""
    stub = _StubExecutor(input_types=[str, dict])

    types = extract_executor_message_types(stub)

    assert types == [str, dict]


def test_extract_executor_message_types_falls_back_to_handlers():
    """Handlers provide message metadata when input_types missing."""
    stub = _StubExecutor(handlers={str: object(), int: object()})

    types = extract_executor_message_types(stub)

    assert str in types
    assert int in types


def test_select_primary_input_type_prefers_string_and_dict():
    """Primary type selection prefers user-friendly primitives."""
    string_first = select_primary_input_type([dict[str, str], str])
    dict_first = select_primary_input_type([dict[str, str]])
    fallback = select_primary_input_type([int, float])

    assert string_first is str
    assert dict_first is dict
    assert fallback is int


@pytest.mark.asyncio
async def test_credential_cleanup() -> None:
    """Test that async credentials are properly closed during server cleanup."""
    from unittest.mock import AsyncMock, Mock

    from agent_framework import Agent

    # Create mock credential with async close
    mock_credential = AsyncMock()
    mock_credential.close = AsyncMock()

    # Create mock chat client with credential
    mock_client = Mock()
    mock_client.async_credential = mock_credential
    mock_client.model = "test-model"
    mock_client.function_invocation_configuration = None

    # Create agent with mock client
    agent = Agent(name="TestAgent", client=mock_client, instructions="Test agent")

    # Create DevUI server with agent
    server = DevServer()
    server._pending_entities = [agent]
    await server._ensure_executor()

    # Run cleanup
    await server._cleanup_entities()

    # Verify credential.close() was called
    assert mock_credential.close.called, "Async credential close should have been called"
    assert mock_credential.close.call_count == 1


@pytest.mark.asyncio
async def test_credential_cleanup_error_handling() -> None:
    """Test that credential cleanup errors are handled gracefully."""
    from unittest.mock import AsyncMock, Mock

    from agent_framework import Agent

    # Create mock credential that raises error on close
    mock_credential = AsyncMock()
    mock_credential.close = AsyncMock(side_effect=Exception("Close failed"))

    # Create mock chat client with credential
    mock_client = Mock()
    mock_client.async_credential = mock_credential
    mock_client.model = "test-model"
    mock_client.function_invocation_configuration = None

    # Create agent with mock client
    agent = Agent(name="TestAgent", client=mock_client, instructions="Test agent")

    # Create DevUI server with agent
    server = DevServer()
    server._pending_entities = [agent]
    await server._ensure_executor()

    # Run cleanup - should not raise despite credential error
    await server._cleanup_entities()

    # Verify close was attempted
    assert mock_credential.close.called


@pytest.mark.asyncio
async def test_multiple_credential_attributes() -> None:
    """Test that we check all common credential attribute names."""
    from unittest.mock import AsyncMock, Mock

    from agent_framework import Agent

    # Create mock credentials
    mock_cred1 = Mock()
    mock_cred1.close = Mock()
    mock_cred2 = AsyncMock()
    mock_cred2.close = AsyncMock()

    # Create mock chat client with multiple credential attributes
    mock_client = Mock()
    mock_client.credential = mock_cred1
    mock_client.async_credential = mock_cred2
    mock_client.model = "test-model"
    mock_client.function_invocation_configuration = None

    # Create agent with mock client
    agent = Agent(name="TestAgent", client=mock_client, instructions="Test agent")

    # Create DevUI server with agent
    server = DevServer()
    server._pending_entities = [agent]
    await server._ensure_executor()

    # Run cleanup
    await server._cleanup_entities()

    # Verify both credentials were closed
    assert mock_cred1.close.called, "Sync credential should be closed"
    assert mock_cred2.close.called, "Async credential should be closed"


def test_ui_mode_configuration():
    """Test UI mode configuration."""
    dev_server = DevServer(mode="developer")
    assert dev_server.mode == "developer"

    user_server = DevServer(mode="user")
    assert user_server.mode == "user"


@pytest.mark.asyncio
async def test_api_restrictions_in_user_mode():
    """Test that developer APIs are restricted in user mode."""
    from fastapi.testclient import TestClient

    # Create servers with different modes. auth_enabled=False isolates this test
    # to mode behavior — auth has its own dedicated suite.
    dev_server = DevServer(mode="developer", auth_enabled=False)
    user_server = DevServer(mode="user", auth_enabled=False)

    dev_app = dev_server.create_app()
    user_app = user_server.create_app()

    # base_url sets the Host header to a loopback alias so the loopback
    # host-header allowlist accepts the request.
    dev_client = TestClient(dev_app, base_url="http://127.0.0.1")
    user_client = TestClient(user_app, base_url="http://127.0.0.1")

    # Test 1: Health endpoint should work in both modes
    assert dev_client.get("/health").status_code == 200
    assert user_client.get("/health").status_code == 200

    # Test 2: Meta endpoint should reflect correct mode
    dev_meta = dev_client.get("/meta").json()
    assert dev_meta["ui_mode"] == "developer"

    user_meta = user_client.get("/meta").json()
    assert user_meta["ui_mode"] == "user"

    # Test 3: Entity listing should work in both modes
    assert dev_client.get("/v1/entities").status_code == 200
    assert user_client.get("/v1/entities").status_code == 200

    # Test 4: Entity info should be accessible in both modes (UI needs this)
    dev_response = dev_client.get("/v1/entities/test_agent/info")
    assert dev_response.status_code in [200, 404, 500]  # Not 403

    user_response = user_client.get("/v1/entities/test_agent/info")
    # Should return 404 (entity doesn't exist) or 500 (other error), but NOT 403 (forbidden)
    # User mode needs entity info to display workflows/agents in the UI
    assert user_response.status_code in [200, 404, 500]  # Not 403

    # Test 5: Hot reload should be restricted in user mode
    dev_response = dev_client.post("/v1/entities/test_agent/reload")
    assert dev_response.status_code in [200, 404, 500]  # Not 403

    user_response = user_client.post("/v1/entities/test_agent/reload")
    assert user_response.status_code == 403
    error_data = user_response.json()
    error = error_data.get("detail", {}).get("error") or error_data.get("error")
    assert "developer mode" in error["message"].lower()

    # Test 6: Deployment endpoints should be restricted in user mode
    # List deployments (simplest test - no payload needed)
    user_response = user_client.get("/v1/deployments")
    assert user_response.status_code == 403
    error_data = user_response.json()
    error = error_data.get("detail", {}).get("error") or error_data.get("error")
    assert "developer mode" in error["message"].lower()

    # Get deployment
    user_response = user_client.get("/v1/deployments/test-id")
    assert user_response.status_code == 403

    # Delete deployment
    user_response = user_client.delete("/v1/deployments/test-id")
    assert user_response.status_code == 403

    # Test 7: Conversation endpoints should work in both modes
    dev_response = dev_client.post("/v1/conversations", json={})
    assert dev_response.status_code == 200

    user_response = user_client.post("/v1/conversations", json={})
    assert user_response.status_code == 200

    # Test 8: Chat endpoint should work in both modes
    chat_payload = {"model": "test_agent", "input": "Hello"}
    dev_response = dev_client.post("/v1/responses", json=chat_payload)
    # 200=success, 400=missing entity_id in metadata, 404=entity not found
    assert dev_response.status_code in [200, 400, 404]

    user_response = user_client.post("/v1/responses", json=chat_payload)
    assert user_response.status_code in [200, 400, 404]


if __name__ == "__main__":
    # Simple test runner
    async def run_tests():
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create test agent
            agent_file = temp_path / "weather_agent.py"
            agent_file.write_text("""
class WeatherAgent:
    name = "Weather Agent"
    description = "Gets weather information"

    def run(self, input_str, *, stream: bool = False, thread=None, **kwargs):
        return f"Weather in {input_str} is sunny"
""")

            server = DevServer(entities_dir=str(temp_path))
            executor = await server._ensure_executor()

            entities = await executor.discover_entities()

            if entities:
                request = AgentFrameworkRequest(
                    metadata={"entity_id": entities[0].id},
                    input="test location",
                    stream=False,
                )

                await executor.execute_sync(request)

    asyncio.run(run_tests())


@pytest.mark.asyncio
async def test_checkpoint_api_endpoints(test_entities_dir):
    """Test checkpoint list and delete API endpoints."""
    from agent_framework._workflows._checkpoint import WorkflowCheckpoint

    server = DevServer(entities_dir=test_entities_dir)
    executor = await server._ensure_executor()

    # Create a conversation
    conversation = executor.conversation_store.create_conversation(metadata={"name": "Test Session"})
    conv_id = conversation.id

    # Get checkpoint storage and add a checkpoint
    storage = executor.checkpoint_manager.get_checkpoint_storage(conv_id)
    checkpoint = WorkflowCheckpoint(
        checkpoint_id="test_checkpoint_1",
        workflow_name="test_workflow",
        graph_signature_hash="test_graph_hash",
        state={"key": "value"},
        iteration_count=1,
    )
    await storage.save(checkpoint)

    # Test list checkpoints endpoint
    checkpoints = await storage.list_checkpoints(workflow_name="test_workflow")
    assert len(checkpoints) == 1
    assert checkpoints[0].checkpoint_id == "test_checkpoint_1"
    assert checkpoints[0].workflow_name == "test_workflow"

    # Test delete checkpoint endpoint
    deleted = await storage.delete("test_checkpoint_1")
    assert deleted is True

    # Verify checkpoint was deleted
    remaining = await storage.list_checkpoints(workflow_name="test_workflow")
    assert len(remaining) == 0

    # Test delete non-existent checkpoint
    deleted = await storage.delete("nonexistent")
    assert deleted is False


# =============================================================================
# Security posture: default CORS, auth, host-header, and streaming headers.
# =============================================================================


def _server_with_mock_agent(**kwargs) -> DevServer:
    """Build a DevServer with one in-memory mock agent registered."""
    server = DevServer(**kwargs)
    server.set_pending_entities([MockAgent(id="mock", name="Mock", response_text="hi")])
    return server


def test_streaming_response_does_not_hardcode_acao_header():
    """A streaming /v1/responses must not set Access-Control-Allow-Origin itself.

    The endpoint previously hardcoded `Access-Control-Allow-Origin: *` on the
    StreamingResponse, bypassing CORSMiddleware. With no Origin header on the
    request, CORSMiddleware never adds ACAO — so any ACAO we see proves the
    streaming handler is still setting it.
    """
    server = _server_with_mock_agent(auth_token="s3cret")
    app = server.get_app()

    with TestClient(app, base_url="http://127.0.0.1") as client:
        response = client.post(
            "/v1/responses",
            json={"metadata": {"entity_id": "mock"}, "input": "hello", "stream": True},
            headers={"Authorization": "Bearer s3cret"},
        )

        assert "access-control-allow-origin" not in {k.lower() for k in response.headers}, (
            "Streaming response sets ACAO directly, bypassing CORSMiddleware"
        )


def test_cors_default_does_not_allow_arbitrary_origin_even_on_localhost():
    """Default CORS must not echo Access-Control-Allow-Origin to arbitrary origins.

    Previous default was `["*"]` on localhost binds, which let any webpage the
    developer visited read DevUI's responses. Default is now `[]` — opt in by
    passing `cors_origins=[...]` explicitly.
    """
    server = _server_with_mock_agent(host="127.0.0.1", auth_token="s3cret")
    app = server.get_app()

    with TestClient(app, base_url="http://127.0.0.1") as client:
        preflight = client.options(
            "/v1/entities",
            headers={
                "Origin": "https://evil.example",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert preflight.headers.get("access-control-allow-origin") not in ("*", "https://evil.example")

        actual = client.get(
            "/v1/entities",
            headers={"Origin": "https://evil.example", "Authorization": "Bearer s3cret"},
        )
        assert actual.headers.get("access-control-allow-origin") not in ("*", "https://evil.example")


def test_devserver_requires_auth_by_default(monkeypatch):
    """A bare DevServer() must reject unauthenticated /v1/* requests.

    Previously auth was opt-in via DEVUI_AUTH_TOKEN env var; the new default is
    auth-on so a bare `devui ./agents` invocation does not expose an open API.
    """
    monkeypatch.delenv("DEVUI_AUTH_TOKEN", raising=False)

    server = DevServer()
    app = server.get_app()

    with TestClient(app, base_url="http://127.0.0.1") as client:
        response = client.get("/v1/entities")

    assert response.status_code == 401


def test_devserver_auth_can_be_explicitly_disabled(monkeypatch):
    """Callers can opt out of auth on loopback (escape hatch for tests / trusted local hosts)."""
    monkeypatch.delenv("DEVUI_AUTH_TOKEN", raising=False)

    server = _server_with_mock_agent(auth_enabled=False)
    app = server.get_app()

    with TestClient(app, base_url="http://127.0.0.1") as client:
        response = client.get("/v1/entities")

    assert response.status_code == 200


def test_devserver_rejects_non_loopback_no_auth(monkeypatch):
    """Non-loopback binds must not be network-reachable without authentication."""
    monkeypatch.delenv("DEVUI_AUTH_TOKEN", raising=False)

    with pytest.raises(ValueError, match="authentication cannot be disabled"):
        DevServer(host="0.0.0.0", auth_enabled=False)

    with pytest.raises(ValueError, match="authentication cannot be disabled"):
        DevServer(host="devui.example", auth_enabled=False)


def test_devserver_rejects_non_loopback_without_explicit_token(monkeypatch):
    """Network-reachable auth requires an operator-provided token, not a generated token."""
    monkeypatch.delenv("DEVUI_AUTH_TOKEN", raising=False)

    with pytest.raises(ValueError, match="DEVUI_AUTH_TOKEN or auth_token"):
        DevServer(host="0.0.0.0")


def test_devserver_allows_non_loopback_with_explicit_token(monkeypatch):
    """A network-reachable bind is allowed when auth has an explicit token."""
    monkeypatch.delenv("DEVUI_AUTH_TOKEN", raising=False)

    server = DevServer(host="0.0.0.0", auth_token="s3cret")

    assert server.auth_enabled is True
    assert server.auth_token == "s3cret"


def test_devserver_allows_non_loopback_with_env_token(monkeypatch):
    """A network-reachable bind is allowed when auth uses DEVUI_AUTH_TOKEN."""
    monkeypatch.setenv("DEVUI_AUTH_TOKEN", "env-s3cret")

    server = DevServer(host="0.0.0.0")

    assert server.auth_enabled is True
    assert server.auth_token == "env-s3cret"


def test_devserver_allows_loopback_no_auth(monkeypatch):
    """Unauthenticated DevUI remains available for local-only development and tests."""
    monkeypatch.delenv("DEVUI_AUTH_TOKEN", raising=False)

    for host in ("127.0.0.1", "localhost"):
        server = DevServer(host=host, auth_enabled=False)
        assert server.auth_enabled is False
        assert server.auth_token is None


def test_devserver_loopback_auth_auto_generates_token(monkeypatch):
    """Loopback auth-enabled usage may still use a generated development token."""
    monkeypatch.delenv("DEVUI_AUTH_TOKEN", raising=False)

    server = DevServer(host="127.0.0.1")

    assert server.auth_enabled is True
    assert server.auth_token


def test_serve_rejects_non_loopback_no_auth(monkeypatch):
    """The public serve() helper must inherit the DevServer network-auth invariant."""
    monkeypatch.delenv("DEVUI_AUTH_TOKEN", raising=False)

    with pytest.raises(ValueError, match="authentication cannot be disabled"):
        agent_framework_devui.serve(entities=[], host="0.0.0.0", auth_enabled=False, ui_enabled=False)


def test_serve_rejects_non_loopback_without_explicit_token(monkeypatch):
    """serve() must not maintain a weaker generated-token path for network binds."""
    monkeypatch.delenv("DEVUI_AUTH_TOKEN", raising=False)

    with pytest.raises(ValueError, match="DEVUI_AUTH_TOKEN or auth_token"):
        agent_framework_devui.serve(entities=[], host="0.0.0.0", ui_enabled=False)


def test_serve_allows_non_loopback_with_explicit_token(monkeypatch):
    """serve() accepts a network bind when an explicit token is provided."""
    import uvicorn

    monkeypatch.delenv("DEVUI_AUTH_TOKEN", raising=False)
    run_args: dict[str, int | str] = {}

    def fake_run(_app, *, host, port, **_kwargs):
        run_args["host"] = host
        run_args["port"] = port

    monkeypatch.setattr(uvicorn, "run", fake_run)

    agent_framework_devui.serve(
        entities=[],
        host="0.0.0.0",
        port=9090,
        auth_token="s3cret",
        auto_open=False,
        ui_enabled=False,
    )

    assert run_args == {"host": "0.0.0.0", "port": 9090}


def test_devserver_accepts_request_with_valid_bearer_token(monkeypatch):
    """When auth is on, supplying the configured Bearer token grants access."""
    monkeypatch.delenv("DEVUI_AUTH_TOKEN", raising=False)

    server = DevServer(auth_token="s3cret")
    app = server.get_app()

    with TestClient(app, base_url="http://127.0.0.1") as client:
        response = client.get("/v1/entities", headers={"Authorization": "Bearer s3cret"})

    assert response.status_code == 200


def test_meta_endpoint_requires_auth(monkeypatch):
    """/meta exposes capability flags (deployment, instrumentation, version) — gate it behind auth.

    Previously /meta was in the auth-bypass list alongside /health and /, so any
    unauthenticated caller could read the deployment's capability flags.
    """
    monkeypatch.delenv("DEVUI_AUTH_TOKEN", raising=False)

    server = DevServer(auth_token="s3cret")
    app = server.get_app()

    with TestClient(app, base_url="http://127.0.0.1") as client:
        unauth = client.get("/meta")
        assert unauth.status_code == 401

        ok = client.get("/meta", headers={"Authorization": "Bearer s3cret"})
        assert ok.status_code == 200


def test_loopback_bind_rejects_non_allowlisted_host_header(monkeypatch):
    """A loopback-bound server must reject requests with a non-loopback Host header.

    On a loopback bind, only Host values that name a loopback address are valid;
    anything else (e.g. an external hostname that happens to resolve to 127.0.0.1)
    is rejected before any handler runs.
    """
    monkeypatch.delenv("DEVUI_AUTH_TOKEN", raising=False)

    server = DevServer(host="127.0.0.1", auth_enabled=False)
    app = server.get_app()

    with TestClient(app, base_url="http://127.0.0.1") as client:
        rebound = client.get("/health", headers={"Host": "evil.example"})
        assert rebound.status_code == 400

        ok = client.get("/health", headers={"Host": "127.0.0.1"})
        assert ok.status_code == 200

        ok_localhost = client.get("/health", headers={"Host": "localhost:8080"})
        assert ok_localhost.status_code == 200


def test_serve_defaults_to_auth_enabled():
    """`serve()`'s public signature must default to auth_enabled=True."""
    sig = inspect.signature(agent_framework_devui.serve)
    assert sig.parameters["auth_enabled"].default is True, (
        "serve() must default to auth_enabled=True so `devui ./agents` is secure out of the box"
    )


def test_cli_enables_auth_by_default_and_supports_loopback_no_auth_optout():
    """`devui ./agents` must produce auth-enabled config; `--no-auth` is the loopback-only escape hatch."""
    from agent_framework_devui._cli import create_cli_parser

    parser = create_cli_parser()

    default_args = parser.parse_args([])
    assert default_args.no_auth is False, "Default CLI invocation should leave auth on"

    optout_args = parser.parse_args(["--no-auth"])
    assert optout_args.no_auth is True

    help_text = parser.format_help()
    assert "loopback-only" in help_text
    assert "Non-loopback hosts require auth" in help_text


def _run_cli_with_fake_uvicorn(monkeypatch, tmp_path: Path, *args: str) -> dict[str, Any]:
    """Run the DevUI CLI without binding a socket."""
    import uvicorn

    from agent_framework_devui import _cli

    run_args: dict[str, Any] = {}

    def fake_run(_app, *, host, port, **_kwargs):
        run_args["host"] = host
        run_args["port"] = port

    monkeypatch.setattr(uvicorn, "run", fake_run)
    monkeypatch.setattr(sys, "argv", ["devui", str(tmp_path), "--no-open", "--headless", *args])

    _cli.main()

    return run_args


def test_cli_allows_loopback_no_auth_without_binding_socket(monkeypatch, tmp_path):
    """`devui --no-auth` remains valid on the default loopback host."""
    monkeypatch.delenv("DEVUI_AUTH_TOKEN", raising=False)

    run_args = _run_cli_with_fake_uvicorn(monkeypatch, tmp_path, "--no-auth")

    assert run_args == {"host": "127.0.0.1", "port": 8080}


def test_cli_rejects_non_loopback_no_auth_before_binding_socket(monkeypatch, tmp_path, capsys):
    """`devui --host 0.0.0.0 --no-auth` must fail through shared server validation."""
    monkeypatch.delenv("DEVUI_AUTH_TOKEN", raising=False)

    with pytest.raises(SystemExit) as exc_info:
        _run_cli_with_fake_uvicorn(monkeypatch, tmp_path, "--host", "0.0.0.0", "--no-auth")

    assert exc_info.value.code == 1
    assert "authentication cannot be disabled" in capsys.readouterr().err


def test_cli_rejects_non_loopback_without_explicit_token_before_binding_socket(monkeypatch, tmp_path, capsys):
    """`devui --host 0.0.0.0` must fail when neither --auth-token nor DEVUI_AUTH_TOKEN is set."""
    monkeypatch.delenv("DEVUI_AUTH_TOKEN", raising=False)

    with pytest.raises(SystemExit) as exc_info:
        _run_cli_with_fake_uvicorn(monkeypatch, tmp_path, "--host", "0.0.0.0")

    assert exc_info.value.code == 1
    assert "DEVUI_AUTH_TOKEN or auth_token" in capsys.readouterr().err


def test_cli_allows_non_loopback_with_auth_token_without_binding_socket(monkeypatch, tmp_path):
    """`devui --host 0.0.0.0 --auth-token ...` starts with token auth enabled."""
    monkeypatch.delenv("DEVUI_AUTH_TOKEN", raising=False)

    run_args = _run_cli_with_fake_uvicorn(monkeypatch, tmp_path, "--host", "0.0.0.0", "--auth-token", "s3cret")

    assert run_args == {"host": "0.0.0.0", "port": 8080}


def test_cli_allows_non_loopback_with_env_token_without_binding_socket(monkeypatch, tmp_path):
    """`DEVUI_AUTH_TOKEN=... devui --host 0.0.0.0` starts with token auth enabled."""
    monkeypatch.setenv("DEVUI_AUTH_TOKEN", "env-s3cret")

    run_args = _run_cli_with_fake_uvicorn(monkeypatch, tmp_path, "--host", "0.0.0.0")

    assert run_args == {"host": "0.0.0.0", "port": 8080}
