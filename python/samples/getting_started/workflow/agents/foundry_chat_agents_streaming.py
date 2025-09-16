# Copyright (c) Microsoft. All rights reserved.

# import asyncio

# from agent_framework.foundry import FoundryChatClient
# from agent_framework import AgentRunUpdateEvent, WorkflowBuilder, WorkflowCompletedEvent
# from azure.identity.aio import AzureCliCredential

# """
# Sample: Agents in a workflow with streaming

# A Writer agent generates content, then a Reviewer agent critiques it.
# The workflow uses streaming so you can observe incremental AgentRunUpdateEvent chunks as each agent produces tokens.

# Purpose:
# Show how to wire chat agents directly into a WorkflowBuilder pipeline where agents are auto wrapped as executors.

# Demonstrate:
# - Automatic streaming of agent deltas via AgentRunUpdateEvent.
# - A simple console aggregator that groups updates by executor id and prints them as they arrive.
# - A final WorkflowCompletedEvent that contains the reviewer outcome after both agents finish.

# Prerequisites:
# - Foundry Agent Service configured, along with the required environment variables.
# - Authentication via azure-identity. Use AzureCliCredential and run az login before executing the sample.
# - Basic familiarity with WorkflowBuilder, edges, events, and streaming runs.
# """


# async def main():
#     """Build and run a simple two node agent workflow: Writer then Reviewer."""
#     # Create the Foundry chat client.
#     async with (
#         AzureCliCredential() as credential,
#         FoundryChatClient(async_credential=credential).create_agent(
#             name="Writer",
#             instructions=(
#                 "You are an excellent content writer.You create new content and edit contents based on the feedback."
#             ),
#         ) as writer_agent,
#         FoundryChatClient(async_credential=credential).create_agent(
#             name="Reviewer",
#             instructions=(
#                 "You are an excellent content reviewer."
#                 "Provide actionable feedback to the writer about the provided content."
#                 "Provide the feedback in the most concise manner possible."
#             ),
#         ) as reviewer_agent,
#     ):
#         # Build the workflow using the fluent builder.
#         # Set the start node and connect an edge from writer to reviewer.
#         workflow = WorkflowBuilder().set_start_executor(writer_agent).add_edge(writer_agent, reviewer_agent).build()

#         # Stream events from the workflow. We aggregate partial token updates per executor for readable output.
#         completed_event: WorkflowCompletedEvent | None = None
#         last_executor_id = None

#         async for event in workflow.run_stream(
#             "Create a slogan for a new electric SUV that is affordable and fun to drive."
#         ):
#             if isinstance(event, AgentRunUpdateEvent):
#                 # AgentRunUpdateEvent contains incremental text deltas from the underlying agent.
#                 # Print a prefix when the executor changes, then append updates on the same line.
#                 eid = event.executor_id
#                 if eid != last_executor_id:
#                     if last_executor_id is not None:
#                         print()
#                     print(f"{eid}:", end=" ", flush=True)
#                     last_executor_id = eid
#                 print(event.data, end="", flush=True)
#             elif isinstance(event, WorkflowCompletedEvent):
#                 # Terminal event with the final reviewer output.
#                 completed_event = event

#         # Print the final consolidated reviewer result.
#         if completed_event:
#             print("\n===== Final Output =====")
#             print(completed_event.data)

#         """
#         Sample Output:

#         writer_agent: Charge Up Your Journey. Fun, Affordable, Electric.
#         reviewer_agent: Clear message, but consider highlighting SUV specific benefits
#             (space, versatility) for stronger impact. Try more vivid language to evoke
#             excitement. Example: "Big on Space. Big on Fun. Electric for Everyone."
#         ===== Final Output =====
#         Clear message, but consider highlighting SUV specific benefits (space, versatility)
#             for stronger impact. Try more vivid language to evoke excitement. Example:
#             "Big on Space. Big on Fun. Electric for Everyone."
#         """


# if __name__ == "__main__":
#     asyncio.run(main())

import asyncio
from contextlib import AsyncExitStack
from typing import Any
from collections.abc import Awaitable, Callable

from agent_framework.foundry import FoundryChatClient
from agent_framework import AgentRunUpdateEvent, WorkflowBuilder, WorkflowCompletedEvent
from azure.identity.aio import AzureCliCredential


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

        completed: WorkflowCompletedEvent | None = None
        last_executor_id: str | None = None

        async for event in workflow.run_stream(
            "Create a slogan for a new electric SUV that is affordable and fun to drive."
        ):
            if isinstance(event, AgentRunUpdateEvent):
                eid = event.executor_id
                if eid != last_executor_id:
                    if last_executor_id is not None:
                        print()
                    print(f"{eid}:", end=" ", flush=True)
                    last_executor_id = eid
                print(event.data, end="", flush=True)
            elif isinstance(event, WorkflowCompletedEvent):
                completed = event

        if completed:
            print("\n===== Final Output =====")
            print(completed.data)

    finally:
        await close()


if __name__ == "__main__":
    asyncio.run(main())
