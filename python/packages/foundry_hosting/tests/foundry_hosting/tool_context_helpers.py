# Copyright (c) Microsoft. All rights reserved.

"""Deterministic agent helpers for hosted tool-execution-context tests."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Mapping, Sequence
from typing import Any, Literal

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
FORGED_TENANT_CONTEXT: dict[str, Any] = {"additional_function_arguments": {"tenant_id": "forged"}}


class ToolCallingClient(
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


def make_tenant_agent(
    seen_tenants: list[Any], *, approval_mode: Literal["always_require", "never_require"]
) -> Agent[Any]:
    """Create an agent whose tool records the tenant it receives from hidden runtime context."""

    @tool(name="read_tenant_data", approval_mode=approval_mode)
    def read_tenant_data(ctx: FunctionInvocationContext) -> str:
        seen_tenants.append(ctx.kwargs.get("tenant_id"))
        return "ok"

    return Agent(
        client=ToolCallingClient(),
        tools=[read_tenant_data],
        default_options={"additional_function_arguments": {"tenant_id": TRUSTED_TENANT_ID}},
    )


def make_tenant_workflow_agent(seen_tenants: list[Any]) -> WorkflowAgent:
    """Wrap the tenant agent in a legacy ``WorkflowAgent`` so the workflow hosting path can be exercised."""

    @executor
    async def start(messages: list[Message], ctx: WorkflowContext[AgentExecutorRequest]) -> None:
        await ctx.send_message(AgentExecutorRequest(messages=messages, should_respond=True))

    inner = make_tenant_agent(seen_tenants, approval_mode="never_require")
    workflow = WorkflowBuilder(start_executor=start).add_edge(start, inner).build()
    return WorkflowAgent(workflow=workflow, name="Tenant Workflow Agent")
