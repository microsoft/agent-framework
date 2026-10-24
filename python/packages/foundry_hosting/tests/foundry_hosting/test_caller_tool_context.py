# Copyright (c) Microsoft. All rights reserved.

"""Callers must not supply or replace trusted tool-execution context on Responses requests."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal, cast
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from azure.ai.agentserver.responses import InMemoryResponseProvider, ResponseContext
from azure.ai.agentserver.responses.models import CreateResponse

from agent_framework_foundry_hosting import HostedResponseRequest, ResponsesHostServer
from agent_framework_foundry_hosting._request import (
    prepare_response_options,
    response_run_options,
    validate_request_options,
)
from agent_framework_foundry_hosting._scope import FoundryRequestScope

TRUSTED_TENANT_ID = "trusted"
FORGED_TENANT_CONTEXT: dict[str, Any] = {"additional_function_arguments": {"tenant_id": "forged"}}


@pytest.mark.parametrize(
    "payload",
    [
        {"additional_function_arguments": {"tenant_id": "forged"}},
        {"extra_body": {"additional_function_arguments": {"tenant_id": "forged"}}},
        {"additional_function_arguments": None},
        {"extra_body": {"additional_function_arguments": None}},
    ],
)
def test_caller_cannot_supply_tool_execution_context(payload: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match="agent-controlled fields: additional_function_arguments"):
        response_run_options(cast(CreateResponse, {"input": "hello", "temperature": 0.2, **payload}))


def test_requests_without_tool_context_keep_other_options() -> None:
    request = cast(CreateResponse, {"input": "hello", "extra_body": {"slogan_style": "retro"}, "temperature": 0.2})
    assert response_run_options(request) == {"temperature": 0.2, "slogan_style": "retro"}


async def test_hook_can_supply_trusted_tool_context() -> None:
    context = MagicMock(spec=ResponseContext)
    context.response_id = "outer-id"
    context.conversation_id = None
    context.get_input_text = AsyncMock(return_value="hello")
    scope = FoundryRequestScope(session_id="sandbox", user_id="user", call_id="call", is_hosted=True)
    request = HostedResponseRequest(cast(CreateResponse, {"input": "hello"}), context, scope, {})

    def inject(view: HostedResponseRequest, options: dict[str, Any]) -> dict[str, Any]:
        return {**options, "additional_function_arguments": {"tenant_id": view.scope.user_id}}

    await prepare_response_options(request, inject)
    validate_request_options(request.options)
    assert request.options["additional_function_arguments"] == {"tenant_id": "user"}


async def _post_json(server: ResponsesHostServer, payload: dict[str, Any]) -> httpx.Response:
    transport = httpx.ASGITransport(app=server)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post("/responses", json=payload)


def _make_server(agent: Any, **kwargs: Any) -> ResponsesHostServer:
    return ResponsesHostServer(agent, response_store=InMemoryResponseProvider(), **kwargs)


@pytest.mark.xdist_group("session_isolation")
class TestCallerCannotOverrideToolContext:
    async def test_baseline_uses_trusted_tool_context(self, tenant_agent_factory: Callable[..., Any]) -> None:
        seen: list[Any] = []
        server = _make_server(tenant_agent_factory(seen, approval_mode="never_require"))

        response = await _post_json(server, {"input": "go", "stream": False})

        assert response.json()["status"] == "completed"
        assert seen == [TRUSTED_TENANT_ID]

    @pytest.mark.parametrize("stream", [False, True])
    @pytest.mark.parametrize("location", ["top_level", "extra_body"])
    async def test_forged_tool_context_is_rejected_before_any_tool_runs(
        self, tenant_agent_factory: Callable[..., Any], location: Literal["top_level", "extra_body"], stream: bool
    ) -> None:
        seen: list[Any] = []
        agent = tenant_agent_factory(seen, approval_mode="never_require")
        server = _make_server(agent)
        payload: dict[str, Any] = {"input": "go", "stream": stream}
        if location == "top_level":
            payload.update(FORGED_TENANT_CONTEXT)
        else:
            payload["extra_body"] = FORGED_TENANT_CONTEXT

        response = await _post_json(server, payload)

        assert "additional_function_arguments" in response.text
        assert "failed" in response.text
        assert seen == []
        assert agent.client.calls == 0

    @pytest.mark.filterwarnings("ignore:Hosting WorkflowAgent through agent=.*:DeprecationWarning")
    @pytest.mark.parametrize("location", ["top_level", "extra_body"])
    async def test_forged_tool_context_is_rejected_for_legacy_workflow_agents(
        self, tenant_workflow_agent_factory: Callable[..., Any], location: Literal["top_level", "extra_body"]
    ) -> None:
        seen: list[Any] = []
        server = _make_server(tenant_workflow_agent_factory(seen))
        payload: dict[str, Any] = {"input": "go", "stream": False}
        if location == "top_level":
            payload.update(FORGED_TENANT_CONTEXT)
        else:
            payload["extra_body"] = FORGED_TENANT_CONTEXT

        response = await _post_json(server, payload)

        assert "additional_function_arguments" in response.text
        assert response.json()["status"] == "failed"
        assert seen == []

    @pytest.mark.filterwarnings("ignore:Hosting WorkflowAgent through agent=.*:DeprecationWarning")
    async def test_legacy_workflow_agent_without_forged_context_still_runs(
        self, tenant_workflow_agent_factory: Callable[..., Any]
    ) -> None:
        seen: list[Any] = []
        server = _make_server(tenant_workflow_agent_factory(seen))

        response = await _post_json(server, {"input": "go", "stream": False})

        assert response.json()["status"] == "completed"
        assert seen == [TRUSTED_TENANT_ID]

    async def test_hook_can_still_supply_trusted_tool_context(self, tenant_agent_factory: Callable[..., Any]) -> None:
        seen: list[Any] = []
        server = _make_server(
            tenant_agent_factory(seen, approval_mode="never_require"),
            prepare_options=lambda request, options: {
                **options,
                "additional_function_arguments": {"tenant_id": f"from-hook:{request.scope.user_id}"},
            },
        )

        response = await _post_json(server, {"input": "go", "stream": False})

        assert response.json()["status"] == "completed"
        assert len(seen) == 1
        assert str(seen[0]).startswith("from-hook:")

    async def test_forged_context_on_approval_resume_is_rejected_without_consuming_approval(
        self, tenant_agent_factory: Callable[..., Any]
    ) -> None:
        seen: list[Any] = []
        server = _make_server(tenant_agent_factory(seen, approval_mode="always_require"))

        first = await _post_json(server, {"input": "go", "stream": False, "store": True})
        first_body = first.json()
        approval_id = next(item["id"] for item in first_body["output"] if item["type"] == "mcp_approval_request")
        assert seen == []

        def resume(**extra: Any) -> dict[str, Any]:
            return {
                "input": [{"type": "mcp_approval_response", "approval_request_id": approval_id, "approve": True}],
                "previous_response_id": first_body["id"],
                "stream": False,
                "store": True,
                **extra,
            }

        forged = await _post_json(server, resume(**FORGED_TENANT_CONTEXT))
        assert "additional_function_arguments" in forged.text
        assert seen == []

        legitimate = await _post_json(server, resume())
        assert legitimate.json()["status"] == "completed"
        assert seen == [TRUSTED_TENANT_ID]
