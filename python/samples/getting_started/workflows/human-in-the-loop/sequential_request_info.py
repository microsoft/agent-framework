# Copyright (c) Microsoft. All rights reserved.

"""
Sample: Request Info with SequentialBuilder

This sample demonstrates using the `.with_request_info()` method to pause a
SequentialBuilder workflow AFTER each agent runs, allowing external input
(e.g., human feedback) for review and optional iteration.

Purpose:
Show how to use the request info API that pauses after every agent response,
using the standard request_info pattern for consistency.

Demonstrate:
- Configuring request info with `.with_request_info()`
- Handling request_info events with AgentInputRequest data
- Injecting responses back into the workflow via run(responses=..., stream=True)

Prerequisites:
- Azure OpenAI configured for AzureOpenAIChatClient with required environment variables
- Authentication via azure-identity (run az login before executing)
"""

import asyncio
from collections.abc import AsyncIterable
from typing import cast

from agent_framework import (
    AgentExecutorResponse,
    ChatMessage,
    WorkflowEvent,
)
from agent_framework.azure import AzureOpenAIChatClient
from agent_framework.orchestrations import AgentRequestInfoResponse, SequentialBuilder
from azure.identity import AzureCliCredential


async def process_event_stream(stream: AsyncIterable[WorkflowEvent]) -> dict[str, AgentRequestInfoResponse] | None:
    """Process events from the workflow stream to capture human feedback requests."""

    requests: dict[str, AgentExecutorResponse] = {}
    async for event in stream:
        if event.type == "request_info" and isinstance(event.data, AgentExecutorResponse):
            requests[event.request_id] = event.data

        elif event.type == "output":
            # The output of the sequential workflow is a list of ChatMessages
            print("\n" + "=" * 60)
            print("WORKFLOW COMPLETE")
            print("=" * 60)
            print("Final output:")
            outputs = cast(list[ChatMessage], event.data)
            for message in outputs:
                print(f"[{message.author_name or message.role}]: {message.text}")

    responses: dict[str, AgentRequestInfoResponse] = {}
    if requests:
        for request_id, request in requests.items():
            # Display agent response and conversation context for review
            print("\n" + "-" * 40)
            print("REQUEST INFO: INPUT REQUESTED")
            print(
                f"Agent {request.executor_id} just responded with: '{request.agent_response.text}'. "
                "Please provide your feedback."
            )
            print("-" * 40)
            if request.full_conversation:
                print("Conversation context:")
                recent = (
                    request.full_conversation[-2:] if len(request.full_conversation) > 2 else request.full_conversation
                )
                for msg in recent:
                    name = msg.author_name or msg.role
                    text = (msg.text or "")[:150]
                    print(f"  [{name}]: {text}...")
                print("-" * 40)

            # Get feedback on the agent's response (approve or request iteration)
            user_input = input("Your guidance (or 'skip' to approve): ")  # noqa: ASYNC250
            if user_input.lower() == "skip":
                user_input = AgentRequestInfoResponse.approve()
            else:
                user_input = AgentRequestInfoResponse.from_strings([user_input])

            responses[request_id] = user_input

    return responses if responses else None


async def main() -> None:
    chat_client = AzureOpenAIChatClient(credential=AzureCliCredential())

    # Create agents for a sequential document review workflow
    drafter = chat_client.as_agent(
        name="drafter",
        instructions=("You are a document drafter. When given a topic, create a brief draft (2-3 sentences)."),
    )

    editor = chat_client.as_agent(
        name="editor",
        instructions=(
            "You are an editor. Review the draft and make improvements. "
            "Incorporate any human feedback that was provided."
        ),
    )

    finalizer = chat_client.as_agent(
        name="finalizer",
        instructions=(
            "You are a finalizer. Take the edited content and create a polished final version. "
            "Incorporate any additional feedback provided."
        ),
    )

    # Build workflow with request info enabled (pauses after each agent responds)
    workflow = (
        SequentialBuilder(participants=[drafter, editor, finalizer])
        # Only enable request info for the editor agent
        .with_request_info(agents=["editor"])
        .build()
    )

    # Initiate the first run of the workflow.
    # Runs are not isolated; state is preserved across multiple calls to run.
    stream = workflow.run("Write a brief introduction to artificial intelligence.", stream=True)

    pending_responses = await process_event_stream(stream)
    while pending_responses is not None:
        # Run the workflow until there is no more human feedback to provide,
        # in which case this workflow completes.
        stream = workflow.run(stream=True, responses=pending_responses)
        pending_responses = await process_event_stream(stream)


if __name__ == "__main__":
    asyncio.run(main())
