# Copyright (c) Microsoft. All rights reserved.

"""Verify supported settings and option boundaries without external model calls."""

from __future__ import annotations

from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from agent_framework import Agent, AgentContext, AgentSession, ChatOptions, RawAgent
from azure.ai.agentserver.responses import ResponsesServerOptions

from agent_framework_foundry_hosting import (
    InvocationsHostServer,
    InvocationsWorkflowHostServer,
    ResponsesRequest,
    WorkflowTurn,
)
from agent_framework_foundry_hosting._scope import FoundryRequestScope
from agent_framework_foundry_hosting._shared import (
    _NativeAgentOptions,
    build_response_server_options,
    prepare_response_options,
    reject_removed_host_settings,
    validate_agent_background_options,
    validate_request_options,
)

from .options_helpers import OptionCallbacks, OptionsClient


def test_history_default_is_omitted_instead_of_forced_unlimited(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEFAULT_FETCH_HISTORY_ITEM_COUNT", "7")
    with patch("agent_framework_foundry_hosting._shared.ResponsesServerOptions", wraps=ResponsesServerOptions) as sdk:
        result = build_response_server_options(is_workflow=False)
    assert "default_fetch_history_count" not in sdk.call_args.kwargs
    assert result.default_fetch_history_count == ResponsesServerOptions().default_fetch_history_count
    assert result.default_model is None
    assert result.steerable_conversations is False
    assert result.resilient_background is False
    assert build_response_server_options(is_workflow=False, max_history_items=7).default_fetch_history_count == 7


@pytest.mark.parametrize(
    ("settings", "error"),
    [
        ({"max_history_items": True}, TypeError),
        ({"max_history_items": 1.5}, TypeError),
        ({"max_history_items": 0}, ValueError),
        ({"max_history_items": -1}, ValueError),
        ({"sse_keep_alive_interval_seconds": True}, TypeError),
        ({"sse_keep_alive_interval_seconds": "5"}, TypeError),
        ({"sse_keep_alive_interval_seconds": 0}, ValueError),
        ({"sse_keep_alive_interval_seconds": -1}, ValueError),
        ({"shutdown_grace_period_seconds": True}, TypeError),
        ({"shutdown_grace_period_seconds": 0}, ValueError),
        ({"enable_background_recovery": 1}, TypeError),
        ({"enable_background_recovery": True}, ValueError),
        ({"history_source": "inference_service", "max_history_items": 2}, ValueError),
        ({"history_source": "agent_managed", "max_history_items": 2}, ValueError),
        ({"background_source": "inference_service"}, ValueError),
        ({"history_source": "wrong"}, ValueError),
        ({"background_source": "wrong"}, ValueError),
    ],
)
def test_invalid_settings_fail_before_sdk_options_construction(
    settings: dict[str, Any], error: type[Exception]
) -> None:
    with patch("agent_framework_foundry_hosting._shared.ResponsesServerOptions") as sdk, pytest.raises(error):
        build_response_server_options(is_workflow=False, **settings)
    sdk.assert_not_called()


def test_recovery_and_workflow_history_eligibility() -> None:
    assert build_response_server_options(
        is_workflow=False,
        history_source="inference_service",
        background_source="inference_service",
        enable_background_recovery=True,
    ).resilient_background
    assert build_response_server_options(is_workflow=True, enable_background_recovery=True).resilient_background
    with pytest.raises(ValueError, match="regular agents"):
        build_response_server_options(is_workflow=True, max_history_items=2)
    with pytest.raises(ValueError, match="regular agent"):
        build_response_server_options(is_workflow=True, background_source="inference_service")


@pytest.mark.parametrize(
    "name",
    [
        "options",
        "default_fetch_history_count",
        "default_model",
        "create_span_hook",
        "additional_server_version",
        "steerable_conversations",
        "resilient_background",
    ],
)
def test_removed_host_settings_fail_even_when_none(name: str) -> None:
    settings: dict[str, Any] = {name: None}
    with pytest.raises(TypeError, match=name):
        reject_removed_host_settings({name: None})
    with (
        patch("agent_framework_foundry_hosting._invocations_shared.InvocationAgentServerHost.__init__") as sdk,
        pytest.raises(TypeError, match=name),
    ):
        InvocationsHostServer(Agent(client=OptionsClient()), **settings)
    sdk.assert_not_called()


@pytest.mark.parametrize(
    "name",
    [
        "max_history_items",
        "history_source",
        "background_source",
        "enable_background_recovery",
        "shutdown_grace_period_seconds",
    ],
)
def test_invocations_rejects_responses_only_settings_before_sdk(name: str) -> None:
    settings: dict[str, Any] = {name: None}
    with (
        patch("agent_framework_foundry_hosting._invocations_shared.InvocationAgentServerHost.__init__") as sdk,
        pytest.raises(TypeError, match="Responses-only"),
    ):
        InvocationsHostServer(Agent(client=OptionsClient()), **settings)
    sdk.assert_not_called()


@pytest.mark.parametrize("env", [None, "0", "-2", "3"])
@pytest.mark.parametrize("explicit", [None, 5])
def test_invocations_heartbeat_precedence_and_per_host_isolation(
    monkeypatch: pytest.MonkeyPatch, env: str | None, explicit: int | None
) -> None:
    if env is None:
        monkeypatch.delenv("SSE_KEEPALIVE_INTERVAL", raising=False)
    else:
        monkeypatch.setenv("SSE_KEEPALIVE_INTERVAL", env)
    first = InvocationsHostServer(Agent(client=OptionsClient()), sse_keep_alive_interval_seconds=explicit)
    second = InvocationsHostServer(Agent(client=OptionsClient()))
    inherited = max(0, int(env or "0"))
    assert first.config.sse_keepalive_interval == (explicit if explicit is not None else inherited)
    assert second.config.sse_keepalive_interval == inherited
    assert first.config is not second.config


def test_legacy_raw_stream_does_not_inherit_heartbeats(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SSE_KEEPALIVE_INTERVAL", "3")
    with pytest.warns(DeprecationWarning):
        server = InvocationsHostServer(Agent(client=OptionsClient()), legacy_wire_format=True)
    assert server.config.sse_keepalive_interval == 0
    with pytest.raises(ValueError, match="framed SSE"):
        InvocationsHostServer(Agent(client=OptionsClient()), legacy_wire_format=True, sse_keep_alive_interval_seconds=1)


@pytest.mark.parametrize("provider_background", [False, True])
@pytest.mark.parametrize("background", [None, False, True, "true", 1])
def test_agent_background_defaults_are_validated_without_mutation(provider_background: bool, background: Any) -> None:
    agent = RawAgent(client=OptionsClient(), default_options=cast(ChatOptions, {"background": background}))
    before = dict(agent.default_options)
    if background is not None and not isinstance(background, bool):
        with pytest.raises(TypeError, match="boolean"):
            validate_agent_background_options(agent, provider_background=provider_background)
    elif background is True and not provider_background:
        with pytest.raises(ValueError, match="outer background"):
            validate_agent_background_options(agent, provider_background=provider_background)
    else:
        validate_agent_background_options(agent, provider_background=provider_background)
    assert agent.default_options == before


@pytest.mark.parametrize("provider_background", [False, True])
def test_transport_body_cannot_bypass_background_selection(provider_background: bool) -> None:
    agent = RawAgent(client=OptionsClient(), default_options=cast(ChatOptions, {"extra_body": {"background": True}}))
    with pytest.raises(ValueError, match="extra_body"):
        validate_agent_background_options(agent, provider_background=provider_background)


@pytest.mark.parametrize("field", ["additional_function_arguments", "client_kwargs", "function_invocation_kwargs"])
def test_response_hook_cannot_supply_run_context(field: str) -> None:
    with pytest.raises(ValueError, match=field):
        validate_request_options({field: {"background": True}})


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("async_hook", [False, True])
async def test_invocations_hook_before_factory_preserves_developer_model(stream: bool, async_hook: bool) -> None:
    callbacks = OptionCallbacks(defaults={"model": "developer", "temperature": 0.4})
    host = InvocationsHostServer(
        callbacks.factory,
        prepare_options=callbacks.prepare_async if async_hook else callbacks.prepare,
    )
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=host), base_url="http://test") as client:
        response = await client.post(
            "/invocations?agent_session_id=options",
            json={"message": "hi", "stream": stream, "options": {"model": "caller", "temperature": 0.8}},
        )
    assert response.status_code == 200
    assert callbacks.events == ["hook", "factory"]
    assert callbacks.client.calls[0]["model"] == "developer"
    assert callbacks.client.calls[0]["temperature"] == 0.8
    assert callbacks.defaults == {"model": "developer", "temperature": 0.4}


@pytest.mark.parametrize("stream", [False, True])
async def test_invocations_rejects_factory_hidden_background_before_model_call(
    stream: bool, caplog: pytest.LogCaptureFixture
) -> None:
    callbacks = OptionCallbacks(defaults={"background": True})
    host = InvocationsHostServer(callbacks.factory, prepare_options=callbacks.prepare)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=host), base_url="http://test") as client:
        response = await client.post("/invocations?agent_session_id=options", json={"message": "hi", "stream": stream})
    assert response.status_code == (200 if stream else 500)
    assert "Agent invocation failed." in response.text
    assert "background=True requires an outer background" in caplog.text
    assert callbacks.events == ["hook", "factory"]
    assert callbacks.client.calls == []


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("source", ["defaults", "middleware"])
async def test_native_workflow_rejects_inner_background_before_model_call(
    stream: bool, source: str, caplog: pytest.LogCaptureFixture
) -> None:
    callbacks = OptionCallbacks(
        defaults={"background": True} if source == "defaults" else None,
        injected={"background": True} if source == "middleware" else None,
    )
    host = InvocationsWorkflowHostServer(
        callbacks.workflow, parse_input=lambda request: WorkflowTurn(input="hi", stream=stream)
    )
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=host), base_url="http://test") as client:
        response = await client.post("/invocations?agent_session_id=workflow-options", json={})
    assert response.status_code == (200 if stream else 500 if source == "middleware" else 400)
    if source == "middleware":
        assert "Workflow invocation failed." in response.text
        assert "Native workflow model options cannot override hosting" in caplog.text
    else:
        assert "hosting identity defaults" in response.text
    assert callbacks.client.calls == []


async def test_native_middleware_rechecks_direct_client_kwargs() -> None:
    client = OptionsClient()
    context = AgentContext(
        agent=Agent(client=client),
        messages=[],
        session=AgentSession(),
        client_kwargs={"background": True},
    )
    policy = _NativeAgentOptions(FoundryRequestScope("session", None, None, False))
    with pytest.raises(ValueError, match="client kwargs"):
        await policy.process(context, cast(Any, None))
    assert client.calls == []


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("injected", [{"background": True}, {"extra_body": {"background": True}}])
async def test_native_middleware_rechecks_effective_options(stream: bool, injected: dict[str, Any]) -> None:
    context = AgentContext(
        agent=Agent(client=OptionsClient()),
        messages=[],
        session=AgentSession(),
        stream=stream,
        options=injected,
    )
    policy = _NativeAgentOptions(FoundryRequestScope("session", None, None, False))
    dispatch = AsyncMock()
    with pytest.raises(ValueError, match="hosting|host-controlled"):
        await policy.process(context, dispatch)
    dispatch.assert_not_called()


@pytest.mark.parametrize("workflow", [False, True])
async def test_explicit_interval_emits_heartbeat_on_real_invocations_stream(workflow: bool) -> None:
    callbacks = OptionCallbacks()
    callbacks.client = OptionsClient(delay=1.1)
    host = (
        InvocationsWorkflowHostServer(
            callbacks.workflow,
            parse_input=lambda request: WorkflowTurn(input="hi", stream=True),
            sse_keep_alive_interval_seconds=1,
        )
        if workflow
        else InvocationsHostServer(callbacks.factory, sse_keep_alive_interval_seconds=1)
    )
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=host), base_url="http://test") as client:
        response = await client.post("/invocations?agent_session_id=heartbeat", json={"message": "hi", "stream": True})
    assert response.status_code == 200
    assert ": keep-alive\n\n" in response.text
    assert "ok" in response.text
    assert len(callbacks.client.calls) == 1


async def test_response_hook_returns_independent_nested_options() -> None:
    source: dict[str, Any] = {"metadata": {"source": "caller"}}
    request = ResponsesRequest(
        cast(Any, {}),
        MagicMock(),
        FoundryRequestScope("session", None, None, False),
        source,
    )
    await prepare_response_options(request, lambda request, options: options)
    assert dict(request.options) == source
    assert request.options["metadata"] is not source["metadata"]
    with pytest.raises(TypeError, match="mapping"):
        await prepare_response_options(request, lambda request, options: cast(Any, {1: "not-string"}))
