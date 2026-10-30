# Copyright (c) Microsoft. All rights reserved.

"""Fixtures for hosted tool-execution-context tests."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable, Mapping, Sequence
from typing import Any, Literal, cast

import pytest
from agent_framework import (
    Agent,
    AgentExecutorRequest,
    BaseChatClient,
    ChatMiddlewareLayer,
    ChatResponse,
    ChatResponseUpdate,
    Content,
    FunctionInvocationContext,
    FunctionInvocationLayer,
    Message,
    ResponseStream,
    WorkflowAgent,
    WorkflowBuilder,
    WorkflowContext,
    executor,
    tool,
)

TRUSTED_TENANT_ID = "trusted"

TenantAgentFactory = Callable[..., Agent[Any]]
TenantWorkflowAgentFactory = Callable[[list[Any]], WorkflowAgent]


class _ToolCallingClient(
    FunctionInvocationLayer[Any],
    ChatMiddlewareLayer[Any],
    BaseChatClient[Any],
):
    """Call ``read_tenant_data`` once, then answer."""

    def __init__(self) -> None:
        super().__init__(middleware=[])
        self.calls = 0

    def _inner_get_response(
        self,
        *,
        messages: Sequence[Message],
        stream: bool,
        options: Mapping[str, Any],
        **kwargs: Any,
    ) -> Awaitable[ChatResponse] | ResponseStream[ChatResponseUpdate, ChatResponse]:
        del options, kwargs
        assert stream is True, "The inner agent only runs in stream mode in Foundry Hosted Agents."
        self.calls += 1
        needs_tool_call = not any(
            content.type == "function_result" for message in messages for content in message.contents
        )

        async def stream_response() -> AsyncIterator[ChatResponseUpdate]:
            if needs_tool_call:
                yield ChatResponseUpdate(
                    contents=[Content.from_function_call(call_id="call_1", name="read_tenant_data", arguments="{}")],
                    role="assistant",
                )
            else:
                yield ChatResponseUpdate(contents=[Content.from_text("done")], role="assistant")

        return ResponseStream(stream_response(), finalizer=ChatResponse.from_updates)


@pytest.fixture
def tenant_agent_factory() -> TenantAgentFactory:
    """Create agents whose tool records the tenant it receives from hidden runtime context."""

    def factory(seen_tenants: list[Any], *, approval_mode: Literal["always_require", "never_require"]) -> Agent[Any]:
        @tool(name="read_tenant_data", approval_mode=approval_mode)
        def read_tenant_data(ctx: FunctionInvocationContext) -> str:
            seen_tenants.append(ctx.kwargs.get("tenant_id"))
            return "ok"

        return Agent(
            client=_ToolCallingClient(),
            tools=[read_tenant_data],
            default_options=cast(Any, {"additional_function_arguments": {"tenant_id": TRUSTED_TENANT_ID}}),
        )

    return factory


@pytest.fixture
def tenant_workflow_agent_factory(tenant_agent_factory: TenantAgentFactory) -> TenantWorkflowAgentFactory:
    """Wrap the tenant agent in a legacy ``WorkflowAgent`` so the workflow hosting path can be exercised."""

    def factory(seen_tenants: list[Any]) -> WorkflowAgent:
        @executor
        async def start(messages: list[Message], ctx: WorkflowContext[AgentExecutorRequest]) -> None:
            await ctx.send_message(AgentExecutorRequest(messages=messages, should_respond=True))

        inner = tenant_agent_factory(seen_tenants, approval_mode="never_require")
        workflow = WorkflowBuilder(start_executor=start).add_edge(start, inner).build()
        return WorkflowAgent(workflow=workflow, name="Tenant Workflow Agent")

    return factory
