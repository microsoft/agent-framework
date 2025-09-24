# Copyright (c) Microsoft. All rights reserved.

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import AsyncExitStack
from typing import Any

from agent_framework import AgentRunUpdateEvent, WorkflowBuilder, WorkflowOutputEvent
from agent_framework.foundry import FoundryChatClient
from azure.identity.aio import AzureCliCredential

"""
Sample: Agents in a workflow with streaming

A Writer agent generates content, then a Reviewer agent critiques it.
The workflow uses streaming so you can observe incremental AgentRunUpdateEvent chunks as each agent produces tokens.

Purpose:
Show how to wire chat agents directly into a WorkflowBuilder pipeline where agents are auto wrapped as executors.

Demonstrate:
- Automatic streaming of agent deltas via AgentRunUpdateEvent.
- A simple console aggregator that groups updates by executor id and prints them as they arrive.
- The workflow completes when idle and outputs are available in events.get_outputs().

Prerequisites:
- Foundry Agent Service configured, along with the required environment variables.
- Authentication via azure-identity. Use AzureCliCredential and run az login before executing the sample.
- Basic familiarity with WorkflowBuilder, edges, events, and streaming runs.
"""


async def create_foundry_agent() -> tuple[Callable[..., Awaitable[Any]], Callable[[], Awaitable[None]]]:
    """Helper method to create a Foundry agent factory and a close function.

    This makes sure the async context managers are properly handled.
    """
    stack = AsyncExitStack()
    cred = await stack.enter_async_context(AzureCliCredential())

    client = await stack.enter_async_context(FoundryChatClient(async_credential=cred))

    async def agent(**kwargs: Any) -> Any:
        return await stack.enter_async_context(client.create_agent(**kwargs))

    async def close() -> None:
        await stack.aclose()

    return agent, close


async def main() -> None:
    agent, close = await create_foundry_agent()
    try:
        writer = await agent(
            name="Writer",
            instructions=(
                "You are an excellent content writer. You create new content and edit contents based on the feedback."
            ),
        )
        reviewer = await agent(
            name="Reviewer",
            instructions=(
                "You are an excellent content reviewer. "
                "Provide actionable feedback to the writer about the provided content. "
                "Provide the feedback in the most concise manner possible."
            ),
        )

        workflow = WorkflowBuilder().set_start_executor(writer).add_edge(writer, reviewer).build()

        last_executor_id: str | None = None

        events = workflow.run_stream("Create a slogan for a new electric SUV that is affordable and fun to drive.")
        async for event in events:
            if isinstance(event, AgentRunUpdateEvent):
                eid = event.executor_id
                if eid != last_executor_id:
                    if last_executor_id is not None:
                        print()
                    print(f"{eid}:", end=" ", flush=True)
                    last_executor_id = eid
                print(event.data, end="", flush=True)
            elif isinstance(event, WorkflowOutputEvent):
                print("\n===== Final output =====")
                print(event.data)
    finally:
        await close()


if __name__ == "__main__":
    asyncio.run(main())
