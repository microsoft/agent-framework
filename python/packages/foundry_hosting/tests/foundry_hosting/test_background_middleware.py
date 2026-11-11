# Copyright (c) Microsoft. All rights reserved.

"""Check provider-background validators and native-workflow middleware boundaries."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from agent_framework_foundry_hosting import InvocationsHostServer, InvocationsWorkflowHostServer, WorkflowTurn
from agent_framework_foundry_hosting._shared import (
    validate_provider_background_options,
)

from .background_helpers import BackgroundCallbacks


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


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("shape", ["flat", "options"])
async def test_native_raw_agent_rejects_run_level_middleware(stream: bool, shape: str) -> None:
    callbacks = BackgroundCallbacks(source="none", location="options", injected={"background": True}, raw=True)
    client_kwargs: dict[str, Any] = {"middleware": [callbacks.inject_chat]}
    if shape == "options":
        client_kwargs = {"options": client_kwargs}
    host = InvocationsWorkflowHostServer(
        callbacks.workflow,
        parse_input=lambda request: WorkflowTurn(input="hi", stream=stream, client_kwargs=client_kwargs),
    )
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=host), base_url="http://test") as client:
        response = await client.post("/invocations?agent_session_id=raw-middleware", json={"message": "hi"})
    assert response.status_code == (200 if stream else 400)
    assert "cannot override hosting" in response.text
    if stream:
        assert "event: error" in response.text
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
