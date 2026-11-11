# Copyright (c) Microsoft. All rights reserved.

"""Check provider-background options after ordinary agent and chat middleware."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from agent_framework import RawAgent

from agent_framework_foundry_hosting import InvocationsHostServer, InvocationsWorkflowHostServer, WorkflowTurn
from agent_framework_foundry_hosting._shared import (
    foreground_agent_run_kwargs,
    validate_provider_background_options,
)

from .background_helpers import AgentChatCallbacks, BackgroundCallbacks, ReplacedMiddlewareCallbacks
from .options_helpers import OptionsClient


@pytest.mark.parametrize("provider_background", [False, True])
@pytest.mark.parametrize("background", [None, False, True, 0, "true"])
def test_pure_background_validator(provider_background: bool, background: Any) -> None:
    options = {"background": background, "temperature": 0.4}
    original = options.copy()
    if background is not None and not isinstance(background, bool):
        with pytest.raises(TypeError, match="boolean"):
            validate_provider_background_options(options, provider_background=provider_background)
    elif background is True and not provider_background:
        with pytest.raises(ValueError, match="outer background"):
            validate_provider_background_options(options, provider_background=provider_background)
    else:
        validate_provider_background_options(options, provider_background=provider_background)
    assert options == original


@pytest.mark.parametrize("provider_background", [False, True])
@pytest.mark.parametrize("background", [None, False, True])
def test_pure_validator_rejects_all_nested_background(provider_background: bool, background: Any) -> None:
    with pytest.raises(ValueError, match="host-controlled"):
        validate_provider_background_options(
            {"extra_body": {"background": background}}, provider_background=provider_background
        )


@pytest.mark.parametrize("workflow", [False, True])
@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("source", ["agent", "chat"])
@pytest.mark.parametrize("location", ["options", "kwargs"])
@pytest.mark.parametrize("injected", [{"background": True}, {"extra_body": {"background": True}}])
async def test_middleware_background_is_rejected_before_provider(
    workflow: bool, stream: bool, source: str, location: str, injected: dict[str, Any], caplog: pytest.LogCaptureFixture
) -> None:
    callbacks = BackgroundCallbacks(source=source, location=location, injected=injected)
    original_middleware = None if callbacks.agent.middleware is None else list(callbacks.agent.middleware)
    original_defaults = callbacks.agent.default_options.copy()
    host = (
        InvocationsWorkflowHostServer(
            callbacks.workflow, parse_input=lambda request: WorkflowTurn(input="hi", stream=stream)
        )
        if workflow
        else InvocationsHostServer(callbacks.agent)
    )
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=host), base_url="http://test") as client:
        response = await client.post(
            "/invocations?agent_session_id=background", json={"message": "hi", "stream": stream}
        )
    assert response.status_code == (200 if stream else 500)
    assert "invocation failed" in response.text.lower()
    assert "background" in caplog.text or "transport controls" in caplog.text
    assert callbacks.client.calls == []
    assert callbacks.agent.default_options == original_defaults
    if not workflow:
        assert callbacks.agent.middleware == original_middleware


@pytest.mark.parametrize("workflow", [False, True])
@pytest.mark.parametrize("stream", [False, True])
async def test_raw_agent_client_middleware_background_is_rejected(
    workflow: bool, stream: bool, caplog: pytest.LogCaptureFixture
) -> None:
    callbacks = BackgroundCallbacks(source="chat", location="options", injected={"background": True}, raw=True)
    host = (
        InvocationsWorkflowHostServer(
            callbacks.workflow, parse_input=lambda request: WorkflowTurn(input="hi", stream=stream)
        )
        if workflow
        else InvocationsHostServer(callbacks.agent)
    )
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=host), base_url="http://test") as client:
        response = await client.post(
            "/invocations?agent_session_id=raw-background", json={"message": "hi", "stream": stream}
        )
    assert response.status_code == (200 if stream else 500)
    assert "background" in caplog.text
    assert callbacks.client.calls == []


@pytest.mark.parametrize("workflow", [False, True])
@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("callbacks_type", [AgentChatCallbacks, ReplacedMiddlewareCallbacks])
async def test_run_guard_survives_agent_chat_middleware_and_replaced_client_middleware(
    workflow: bool, stream: bool, callbacks_type: type[BackgroundCallbacks]
) -> None:
    callbacks = (
        AgentChatCallbacks()
        if callbacks_type is AgentChatCallbacks
        else callbacks_type(source="agent", location="options", injected={"background": True})
    )
    host = (
        InvocationsWorkflowHostServer(
            callbacks.workflow, parse_input=lambda request: WorkflowTurn(input="hi", stream=stream)
        )
        if workflow
        else InvocationsHostServer(callbacks.agent)
    )
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=host), base_url="http://test") as client:
        response = await client.post(
            "/invocations?agent_session_id=background", json={"message": "hi", "stream": stream}
        )
    assert "invocation failed" in response.text.lower()
    assert callbacks.client.calls == []


@pytest.mark.parametrize("workflow", [False, True])
@pytest.mark.parametrize("raw", [False, True])
@pytest.mark.parametrize("stream", [False, True])
async def test_supported_middleware_preserves_foreground_generation(workflow: bool, raw: bool, stream: bool) -> None:
    callbacks = BackgroundCallbacks(source="chat", location="options", injected={"temperature": 0.2}, raw=raw)
    host = (
        InvocationsWorkflowHostServer(
            callbacks.workflow, parse_input=lambda request: WorkflowTurn(input="hi", stream=stream)
        )
        if workflow
        else InvocationsHostServer(callbacks.agent)
    )
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=host), base_url="http://test") as client:
        response = await client.post(
            "/invocations?agent_session_id=foreground", json={"message": "hi", "stream": stream}
        )
    assert response.status_code == 200
    assert "ok" in response.text
    assert callbacks.client.calls[0]["temperature"] == 0.2
    if not (workflow and raw):
        assert callbacks.client.chat_middleware == [callbacks.inject_chat]


def test_unlayered_client_receives_no_middleware_kwarg() -> None:
    assert foreground_agent_run_kwargs(RawAgent(client=OptionsClient())) == {}
