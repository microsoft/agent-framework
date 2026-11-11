# Copyright (c) Microsoft. All rights reserved.

"""Workflow fixtures for hosting tests.

Defined in a module that does not use ``from __future__ import annotations``
because the workflow handler validation reflects on real annotation objects
rather than stringified forms.
"""

from collections.abc import AsyncIterator, Awaitable, Mapping, Sequence
from typing import Any

from agent_framework import (
    Agent,
    AgentExecutor,
    BaseChatClient,
    ChatOptions,
    ChatResponse,
    ChatResponseUpdate,
    Content,
    Executor,
    InMemoryHistoryProvider,
    Message,
    ResponseStream,
    Workflow,
    WorkflowBuilder,
    WorkflowContext,
    handler,
)


class _UpperExecutor(Executor):
    @handler
    async def handle(self, text: str, ctx: WorkflowContext[Any, str]) -> None:
        await ctx.yield_output(text.upper())


class _EchoExecutor(Executor):
    @handler
    async def handle(self, text: str, ctx: WorkflowContext[Any, str]) -> None:
        await ctx.yield_output(text)


def build_upper_workflow() -> Workflow:
    return WorkflowBuilder(start_executor=_UpperExecutor(id="upper")).build()


def build_echo_workflow() -> Workflow:
    return WorkflowBuilder(start_executor=_EchoExecutor(id="echo")).build()


def echo_workflow_builder() -> WorkflowBuilder:
    """Return an *unbuilt* echo ``WorkflowBuilder``, for testing builder-shaped targets."""
    return WorkflowBuilder(start_executor=_EchoExecutor(id="echo"))


class _MultiChunkExecutor(Executor):
    """Yields three separate ``output`` events so streaming has something to chew on."""

    @handler
    async def handle(self, text: str, ctx: WorkflowContext[Any, str]) -> None:
        for chunk in (f"{text}-1", f"{text}-2", f"{text}-3"):
            await ctx.yield_output(chunk)


def build_multi_chunk_workflow() -> Workflow:
    return WorkflowBuilder(start_executor=_MultiChunkExecutor(id="multi")).build()


class RecordingClient(BaseChatClient[ChatOptions[None]]):
    """Chat client that records the text of every model-bound message and always replies ``response``."""

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[list[str]] = []

    def _inner_get_response(
        self,
        *,
        messages: Sequence[Message],
        stream: bool = False,
        options: Mapping[str, Any],
        **kwargs: Any,
    ) -> Awaitable[ChatResponse] | ResponseStream[ChatResponseUpdate, ChatResponse]:
        self.calls.append([message.text for message in messages])
        if stream:

            async def updates() -> AsyncIterator[ChatResponseUpdate]:
                yield ChatResponseUpdate(role="assistant", contents=[Content.from_text("response")])

            return ResponseStream(updates(), finalizer=ChatResponse.from_updates)

        async def get_response() -> ChatResponse:
            return ChatResponse(messages=Message("assistant", ["response"]))

        return get_response()


def agent_executor_workflow_builder(client: RecordingClient) -> WorkflowBuilder:
    """Return an *unbuilt* builder whose ``AgentExecutor`` is created once and shared by every build."""
    agent = Agent(client=client, name="worker", context_providers=[InMemoryHistoryProvider(source_id="history")])
    executor = AgentExecutor(agent, id="worker")
    return WorkflowBuilder(start_executor=executor, output_from=[executor])


def build_agent_executor_workflow(client: RecordingClient) -> Workflow:
    """Build a workflow around a new ``AgentExecutor``, which owns a new ``AgentSession``."""
    return agent_executor_workflow_builder(client).build()


async def run_workflow(workflow: Workflow, text: str, *, stream: bool) -> None:
    """Run ``workflow`` once, streaming or not, and drain the result."""
    if stream:
        async for _ in workflow.run(text, stream=True):
            pass
    else:
        await workflow.run(text)
