# Copyright (c) Microsoft. All rights reserved.

"""
Sample: Request Info with ConcurrentBuilder

This sample demonstrates using the `.with_request_info()` method to pause a
ConcurrentBuilder workflow AFTER all parallel agents complete but BEFORE
aggregation, allowing human review and modification of the combined results.

Purpose:
Show how to use the request info API that pauses after concurrent agents run,
allowing review and steering of results before they are aggregated.

Demonstrate:
- Configuring request info with `.with_request_info()`
- Reviewing outputs from multiple concurrent agents
- Injecting human guidance after agents execute but before aggregation

Prerequisites:
- Azure OpenAI configured for AzureOpenAIChatClient with required environment variables
- Authentication via azure-identity (run az login before executing)
"""

import asyncio
from typing import Any

from agent_framework import (
    AgentInputRequest,
    ChatMessage,
    ConcurrentBuilder,
    RequestInfoEvent,
    Role,
    WorkflowOutputEvent,
    WorkflowRunState,
    WorkflowStatusEvent,
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
            messages = getattr(r.agent_run_response, "messages", [])
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


async def main() -> None:
    global _chat_client
    _chat_client = AzureOpenAIChatClient(credential=AzureCliCredential())

    # Create agents that analyze from different perspectives
    technical_analyst = _chat_client.create_agent(
        name="technical_analyst",
        instructions=(
            "You are a technical analyst. When given a topic, provide a technical "
            "perspective focusing on implementation details, performance, and architecture. "
            "Keep your analysis to 2-3 sentences."
        ),
    )

    business_analyst = _chat_client.create_agent(
        name="business_analyst",
        instructions=(
            "You are a business analyst. When given a topic, provide a business "
            "perspective focusing on ROI, market impact, and strategic value. "
            "Keep your analysis to 2-3 sentences."
        ),
    )

    user_experience_analyst = _chat_client.create_agent(
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
        .with_request_info()
        .build()
    )

    # Run the workflow with human-in-the-loop
    pending_responses: dict[str, str] | None = None
    workflow_complete = False

    print("Starting multi-perspective analysis workflow...")
    print("=" * 60)

    while not workflow_complete:
        # Run or continue the workflow
        stream = (
            workflow.send_responses_streaming(pending_responses)
            if pending_responses
            else workflow.run_stream("Analyze the impact of large language models on software development.")
        )

        pending_responses = None

        # Process events
        async for event in stream:
            if isinstance(event, RequestInfoEvent):
                if isinstance(event.data, AgentInputRequest):
                    # Display pre-execution context for steering concurrent agents
                    print("\n" + "-" * 40)
                    print("INPUT REQUESTED (BEFORE CONCURRENT AGENTS)")
                    print("-" * 40)
                    print(f"About to call agents: {event.data.target_agent_id}")
                    print("Conversation context:")
                    recent = (
                        event.data.conversation[-2:] if len(event.data.conversation) > 2 else event.data.conversation
                    )
                    for msg in recent:
                        role = msg.role.value if msg.role else "unknown"
                        text = (msg.text or "")[:150]
                        print(f"  [{role}]: {text}...")
                    print("-" * 40)

                    # Get human input to steer all agents
                    user_input = input("Your guidance for the analysts (or 'skip' to continue): ")  # noqa: ASYNC250
                    if user_input.lower() == "skip":
                        user_input = "Please analyze objectively from your unique perspective."

                    pending_responses = {event.request_id: user_input}
                    print("(Resuming workflow...)")

            elif isinstance(event, WorkflowOutputEvent):
                print("\n" + "=" * 60)
                print("WORKFLOW COMPLETE")
                print("=" * 60)
                print("Aggregated output:")
                # Custom aggregator returns a string
                if event.data:
                    print(event.data)
                workflow_complete = True

            elif isinstance(event, WorkflowStatusEvent):
                if event.state == WorkflowRunState.IDLE:
                    workflow_complete = True


if __name__ == "__main__":
    asyncio.run(main())
