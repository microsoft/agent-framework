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

from agent_framework import (
    AgentExecutorResponse,
    AgentRequestInfoResponse,
    AgentResponse,
    AgentRunUpdateEvent,
    ChatMessage,
    GroupChatBuilder,
    RequestInfoEvent,
    WorkflowOutputEvent,
    WorkflowRunState,
    WorkflowStatusEvent,
    tool,
)
from agent_framework.azure import AzureOpenAIChatClient
from azure.identity import AzureCliCredential


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
    workflow = (
        GroupChatBuilder()
        .with_orchestrator(agent=orchestrator)
        .participants([optimist, pragmatist, creative])
        .with_max_rounds(6)
        .with_request_info(agents=[pragmatist])  # Only pause before pragmatist speaks
        .build()
    )

    # Run the workflow with human-in-the-loop
    pending_responses: dict[str, AgentRequestInfoResponse] | None = None
    workflow_complete = False
    current_agent: str | None = None  # Track current streaming agent

    print("Starting group discussion workflow...")
    print("=" * 60)

    while not workflow_complete:
        # Run or continue the workflow
        stream = (
            workflow.send_responses_streaming(pending_responses)
            if pending_responses
            else workflow.run_stream(
                "Discuss how our team should approach adopting AI tools for productivity. "
                "Consider benefits, risks, and implementation strategies."
            )
        )

        pending_responses = None

        # Process events
        async for event in stream:
            if isinstance(event, AgentRunUpdateEvent):
                # Show all agent responses as they stream
                if event.data and event.data.text:
                    agent_name = event.data.author_name or "unknown"
                    # Print agent name header only when agent changes
                    if agent_name != current_agent:
                        current_agent = agent_name
                        print(f"\n[{agent_name}]: ", end="", flush=True)
                    print(event.data.text, end="", flush=True)

            elif isinstance(event, RequestInfoEvent):
                current_agent = None  # Reset for next agent
                if isinstance(event.data, AgentExecutorResponse):
                    # Display pre-agent context for human input
                    print("\n" + "-" * 40)
                    print("INPUT REQUESTED")
                    print(f"About to call agent: {event.source_executor_id}")
                    print("-" * 40)
                    print("Conversation context:")
                    agent_response: AgentResponse = event.data.agent_response
                    messages: list[ChatMessage] = agent_response.messages
                    recent: list[ChatMessage] = messages[-3:] if len(messages) > 3 else messages  # type: ignore
                    for msg in recent:
                        name = msg.author_name or "unknown"
                        text = (msg.text or "")[:100]
                        print(f"  [{name}]: {text}...")
                    print("-" * 40)

                    # Get human input to steer the agent
                    user_input = input(f"Feedback for {event.source_executor_id} (or 'skip' to approve): ")  # noqa: ASYNC250
                    if user_input.lower() == "skip":
                        pending_responses = {event.request_id: AgentRequestInfoResponse.approve()}
                    else:
                        pending_responses = {event.request_id: AgentRequestInfoResponse.from_strings([user_input])}
                    print("(Resuming discussion...)")

            elif isinstance(event, WorkflowOutputEvent):
                print("\n" + "=" * 60)
                print("DISCUSSION COMPLETE")
                print("=" * 60)
                print("Final conversation:")
                if event.data:
                    messages: list[ChatMessage] = event.data
                    for msg in messages:
                        role = msg.role.value.capitalize()
                        name = msg.author_name or "unknown"
                        text = (msg.text or "")[:200]
                        print(f"[{role}][{name}]: {text}...")
                workflow_complete = True

            elif isinstance(event, WorkflowStatusEvent) and event.state == WorkflowRunState.IDLE:
                workflow_complete = True


if __name__ == "__main__":
    asyncio.run(main())
