# Copyright (c) Microsoft. All rights reserved.

import asyncio
from typing import Any

from agent_framework import (
    ChatMessage,
    ConcurrentBuilder,
    HumanInputRequest,
    RequestInfoEvent,
    Role,
    WorkflowOutputEvent,
    WorkflowRunState,
    WorkflowStatusEvent,
)
from agent_framework._workflows._agent_executor import AgentExecutorResponse
from agent_framework.azure import AzureOpenAIChatClient
from azure.identity import AzureCliCredential

"""
Sample: Human Input Hook with ConcurrentBuilder

This sample demonstrates using the `.with_human_input_hook()` method to request
arbitrary human feedback mid-workflow with ConcurrentBuilder. The hook is called
after all parallel agents complete but before the aggregator runs.

Purpose:
Show how to use HumanInputRequest to pause a ConcurrentBuilder workflow and request
human review of parallel agent outputs before aggregation.

Demonstrate:
- Configuring a human input hook on ConcurrentBuilder
- Reviewing outputs from multiple concurrent agents simultaneously
- Injecting human guidance before the aggregator synthesizes results

Prerequisites:
- Azure OpenAI configured for AzureOpenAIChatClient with required environment variables
- Authentication via azure-identity (run az login before executing)
"""

# Store chat client at module level for aggregator access
_chat_client: AzureOpenAIChatClient | None = None


def review_concurrent_outputs(
    conversation: list[ChatMessage],
    agent_id: str | None,
) -> HumanInputRequest | None:
    """Hook that requests human input after concurrent agents complete.

    This is a simple demonstration heuristic that always requests review when
    multiple agents have responded. In practice, you might use other strategies:
    - Always pause unconditionally for mandatory human review
    - Check for conflicting opinions between agents
    - Call an async policy service to determine if review is needed
    - Use content classification to detect topics requiring human judgment
    - Skip review if all agents reached similar conclusions

    For ConcurrentBuilder, the hook is called once with a merged view of all
    agent outputs. The agent_id is None since multiple agents contributed.

    Args:
        conversation: Merged conversation including all concurrent agent responses
        agent_id: None for concurrent (multiple agents contributed)

    Returns:
        HumanInputRequest to pause and request input, or None to continue
    """
    if not conversation:
        return None

    # Example heuristic: request review when we have multiple perspectives
    # This is just one approach - replace with your own logic as needed
    assistant_msgs = [m for m in conversation if m.role and m.role.value == "assistant"]

    if len(assistant_msgs) >= 2:
        return HumanInputRequest(
            prompt=(
                f"Received {len(assistant_msgs)} different perspectives. "
                "Please review and provide guidance on which aspects to prioritize in the final summary:"
            ),
            conversation=conversation,
            source_agent_id=agent_id,
            metadata={"num_perspectives": len(assistant_msgs)},
        )
    return None


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

    # Build workflow with human input hook and custom aggregator
    workflow = (
        ConcurrentBuilder()
        .participants([technical_analyst, business_analyst, user_experience_analyst])
        .with_aggregator(aggregate_with_synthesis)
        .with_human_input_hook(review_concurrent_outputs)
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
                if isinstance(event.data, HumanInputRequest):
                    # Display the concurrent agent outputs
                    print("\n" + "-" * 40)
                    print("HUMAN INPUT REQUESTED")
                    print("-" * 40)
                    print("Concurrent agent outputs:")

                    # Show each assistant message (one per analyst)
                    for msg in event.data.conversation:
                        if msg.role and msg.role.value == "assistant":
                            text = (msg.text or "")[:250]
                            print(f"\n  [analyst]: {text}...")

                    print("\n" + "-" * 40)
                    print(f"Prompt: {event.data.prompt}")
                    print("(Workflow paused)")

                    # Get human input
                    user_input = input("Your guidance (or 'skip' to continue): ")
                    if user_input.lower() == "skip":
                        user_input = "All perspectives are equally important. Please create a balanced summary."

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
                # Note: IDLE_WITH_PENDING_REQUESTS is handled inline with RequestInfoEvent


if __name__ == "__main__":
    asyncio.run(main())
