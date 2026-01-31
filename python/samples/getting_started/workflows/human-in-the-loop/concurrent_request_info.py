# Copyright (c) Microsoft. All rights reserved.

"""
Sample: Request Info with ConcurrentBuilder

This sample demonstrates using the `.with_request_info()` method to pause a
ConcurrentBuilder workflow for specific agents, allowing human review and
modification of individual agent outputs before aggregation.

Purpose:
Show how to use the request info API that pauses for selected concurrent agents,
allowing review and steering of their results.

Demonstrate:
- Configuring request info with `.with_request_info()` for specific agents
- Reviewing output from individual agents during concurrent execution
- Injecting human guidance for specific agents before aggregation

Prerequisites:
- Azure OpenAI configured for AzureOpenAIChatClient with required environment variables
- Authentication via azure-identity (run az login before executing)
"""

import asyncio
from typing import Any, AsyncIterable

from agent_framework import (
    AgentRequestInfoResponse,
    ChatMessage,
    ConcurrentBuilder,
    RequestInfoEvent,
    Role,
    WorkflowEvent,
    WorkflowOutputEvent,
)
from agent_framework._workflows._agent_executor import AgentExecutorResponse
from agent_framework.azure import AzureOpenAIChatClient
from azure.identity import AzureCliCredential

# Store chat client at module level for aggregator access
_chat_client: AzureOpenAIChatClient | None = None


async def aggregate_with_synthesis(results: list[AgentExecutorResponse]) -> Any:
    """Custom aggregator that synthesizes concurrent agent outputs using an LLM.

    This aggregator extracts the outputs from each parallel agent and uses the
    chat client to create a unified summary, incorporating any human feedback
    that was injected into the conversation.

    Args:
        results: List of responses from all concurrent agents

    Returns:
        The synthesized summary text
    """
    if not _chat_client:
        return "Error: Chat client not initialized"

    # Extract each agent's final output
    expert_sections: list[str] = []
    human_guidance = ""

    for r in results:
        try:
            messages = getattr(r.agent_response, "messages", [])
            final_text = messages[-1].text if messages and hasattr(messages[-1], "text") else "(no content)"
            expert_sections.append(f"{getattr(r, 'executor_id', 'analyst')}:\n{final_text}")

            # Check for human feedback in the conversation (will be last user message if present)
            if r.full_conversation:
                for msg in reversed(r.full_conversation):
                    if msg.role == Role.USER and msg.text and "perspectives" not in msg.text.lower():
                        human_guidance = msg.text
                        break
        except Exception:
            expert_sections.append(f"{getattr(r, 'executor_id', 'analyst')}: (error extracting output)")

    # Build prompt with human guidance if provided
    guidance_text = f"\n\nHuman guidance: {human_guidance}" if human_guidance else ""

    system_msg = ChatMessage(
        Role.SYSTEM,
        text=(
            "You are a synthesis expert. Consolidate the following analyst perspectives "
            "into one cohesive, balanced summary (3-4 sentences). If human guidance is provided, "
            "prioritize aspects as directed."
        ),
    )
    user_msg = ChatMessage(Role.USER, text="\n\n".join(expert_sections) + guidance_text)

    response = await _chat_client.get_response([system_msg, user_msg])
    return response.messages[-1].text if response.messages else ""


async def process_event_stream(stream: AsyncIterable[WorkflowEvent]) -> dict[str, AgentRequestInfoResponse] | None:
    """Process events from the workflow stream to capture human feedback requests."""

    responses: dict[str, AgentRequestInfoResponse] = {}

    async for event in stream:
        if isinstance(event, RequestInfoEvent) and isinstance(event.data, AgentExecutorResponse):
            # Display agent output for review and potential modification
            print("\n" + "-" * 40)
            print("INPUT REQUESTED")
            print(
                f"Agent {event.source_executor_id} just responded with: '{event.data.agent_response.text}'. "
                "Please provide your feedback."
            )
            print("-" * 40)
            if event.data.full_conversation:
                print("Conversation context:")
                recent = (
                    event.data.full_conversation[-2:]
                    if len(event.data.full_conversation) > 2
                    else event.data.full_conversation
                )
                for msg in recent:
                    name = msg.author_name or msg.role.value
                    text = (msg.text or "")[:150]
                    print(f"  [{name}]: {text}...")
                print("-" * 40)

            # Get human input to steer this agent's contribution
            user_input = input("Your guidance for the analysts (or 'skip' to approve): ")  # noqa: ASYNC250
            if user_input.lower() == "skip":
                user_input = AgentRequestInfoResponse.approve()
            else:
                user_input = AgentRequestInfoResponse.from_strings([user_input])

            responses[event.request_id] = user_input

        if isinstance(event, WorkflowOutputEvent):
            # The output of the workflow comes from the aggregator and it's a single string
            print("\n" + "=" * 60)
            print("ANALYSIS COMPLETE")
            print("=" * 60)
            print("Final synthesized analysis:")
            print(event.data)

    return responses if responses else None


async def main() -> None:
    global _chat_client
    _chat_client = AzureOpenAIChatClient(credential=AzureCliCredential())

    # Create agents that analyze from different perspectives
    technical_analyst = _chat_client.as_agent(
        name="technical_analyst",
        instructions=(
            "You are a technical analyst. When given a topic, provide a technical "
            "perspective focusing on implementation details, performance, and architecture. "
            "Keep your analysis to 2-3 sentences."
        ),
    )

    business_analyst = _chat_client.as_agent(
        name="business_analyst",
        instructions=(
            "You are a business analyst. When given a topic, provide a business "
            "perspective focusing on ROI, market impact, and strategic value. "
            "Keep your analysis to 2-3 sentences."
        ),
    )

    user_experience_analyst = _chat_client.as_agent(
        name="ux_analyst",
        instructions=(
            "You are a UX analyst. When given a topic, provide a user experience "
            "perspective focusing on usability, accessibility, and user satisfaction. "
            "Keep your analysis to 2-3 sentences."
        ),
    )

    # Build workflow with request info enabled and custom aggregator
    workflow = (
        ConcurrentBuilder()
        .participants([technical_analyst, business_analyst, user_experience_analyst])
        .with_aggregator(aggregate_with_synthesis)
        # Only enable request info for the technical analyst agent
        .with_request_info(agents=["technical_analyst"])
        .build()
    )

    # Initiate the first run of the workflow.
    # Runs are not isolated; state is preserved across multiple calls to run or send_responses_streaming.
    stream = workflow.run_stream("Analyze the impact of large language models on software development.")

    pending_responses = await process_event_stream(stream)
    while pending_responses is not None:
        # Run the workflow until there is no more human feedback to provide,
        # in which case this workflow completes.
        stream = workflow.send_responses_streaming(pending_responses)
        pending_responses = await process_event_stream(stream)


if __name__ == "__main__":
    asyncio.run(main())
