# Copyright (c) Microsoft. All rights reserved.

"""
Sample: Request Info with GroupChatBuilder

This sample demonstrates using the `.with_request_info()` method to pause a
GroupChatBuilder workflow BEFORE specific participants speak. By using the
`agents=` filter parameter, you can target only certain participants rather
than pausing before every turn.

Purpose:
Show how to use the request info API with selective filtering to pause before
specific participants speak, allowing human input to steer their response.

Demonstrate:
- Configuring request info with `.with_request_info(agents=[...])`
- Using agent filtering to reduce interruptions
- Steering agent behavior with pre-agent human input

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
from agent_framework.orchestrations import AgentRequestInfoResponse, GroupChatBuilder
from azure.identity import AzureCliCredential


async def process_event_stream(stream: AsyncIterable[WorkflowEvent]) -> dict[str, AgentRequestInfoResponse] | None:
    """Process events from the workflow stream to capture human feedback requests."""

    requests: dict[str, AgentExecutorResponse] = {}
    async for event in stream:
        if event.type == "request_info" and isinstance(event.data, AgentExecutorResponse):
            requests[event.request_id] = event.data

        if event.type == "output":
            # The output of the workflow comes from the orchestrator and it's a list of messages
            print("\n" + "=" * 60)
            print("DISCUSSION COMPLETE")
            print("=" * 60)
            print("Final discussion summary:")
            # To make the type checker happy, we cast event.data to the expected type
            outputs = cast(list[ChatMessage], event.data)
            for msg in outputs:
                speaker = msg.author_name or msg.role
                print(f"[{speaker}]: {msg.text}")

    responses: dict[str, AgentRequestInfoResponse] = {}
    if requests:
        for request_id, request in requests.items():
            # Display pre-agent context for human input
            print("\n" + "-" * 40)
            print("INPUT REQUESTED")
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

            # Get human input to steer the agent
            user_input = input(f"Feedback for {request.executor_id} (or 'skip' to approve): ")  # noqa: ASYNC250
            if user_input.lower() == "skip":
                user_input = AgentRequestInfoResponse.approve()
            else:
                user_input = AgentRequestInfoResponse.from_strings([user_input])

            responses[request_id] = user_input

    return responses if responses else None


async def main() -> None:
    chat_client = AzureOpenAIChatClient(credential=AzureCliCredential())

    # Create agents for a group discussion
    optimist = chat_client.as_agent(
        name="optimist",
        instructions=(
            "You are an optimistic team member. You see opportunities and potential "
            "in ideas. Engage constructively with the discussion, building on others' "
            "points while maintaining a positive outlook. Keep responses to 2-3 sentences."
        ),
    )

    pragmatist = chat_client.as_agent(
        name="pragmatist",
        instructions=(
            "You are a pragmatic team member. You focus on practical implementation "
            "and realistic timelines. Sometimes you disagree with overly optimistic views. "
            "Keep responses to 2-3 sentences."
        ),
    )

    creative = chat_client.as_agent(
        name="creative",
        instructions=(
            "You are a creative team member. You propose innovative solutions and "
            "think outside the box. You may suggest alternatives to conventional approaches. "
            "Keep responses to 2-3 sentences."
        ),
    )

    # Orchestrator coordinates the discussion
    orchestrator = chat_client.as_agent(
        name="orchestrator",
        instructions=(
            "You are a discussion manager coordinating a team conversation between participants. "
            "Your job is to select who speaks next.\n\n"
            "RULES:\n"
            "1. Rotate through ALL participants - do not favor any single participant\n"
            "2. Each participant should speak at least once before any participant speaks twice\n"
            "3. Continue for at least 5 rounds before ending the discussion\n"
            "4. Do NOT select the same participant twice in a row"
        ),
    )

    # Build workflow with request info enabled
    # Using agents= filter to only pause before pragmatist speaks (not every turn)
    # max_rounds=6: Limit to 6 rounds
    workflow = (
        GroupChatBuilder(
            participants=[optimist, pragmatist, creative],
            max_rounds=6,
            orchestrator_agent=orchestrator,
        )
        .with_request_info(agents=[pragmatist])  # Only pause before pragmatist speaks
        .build()
    )

    # Initiate the first run of the workflow.
    # Runs are not isolated; state is preserved across multiple calls to run.
    stream = workflow.run(
        "Discuss how our team should approach adopting AI tools for productivity. "
        "Consider benefits, risks, and implementation strategies.",
        stream=True,
    )

    pending_responses = await process_event_stream(stream)
    while pending_responses is not None:
        # Run the workflow until there is no more human feedback to provide,
        # in which case this workflow completes.
        stream = workflow.run(stream=True, responses=pending_responses)
        pending_responses = await process_event_stream(stream)


if __name__ == "__main__":
    asyncio.run(main())
