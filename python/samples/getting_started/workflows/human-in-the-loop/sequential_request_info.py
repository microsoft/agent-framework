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
- Handling RequestInfoEvent with AgentInputRequest data
- Injecting responses back into the workflow via send_responses_streaming

Prerequisites:
- Azure OpenAI configured for AzureOpenAIChatClient with required environment variables
- Authentication via azure-identity (run az login before executing)
"""

import asyncio

from agent_framework import (
    AgentExecutorResponse,
    AgentRequestInfoResponse,
    ChatMessage,
    RequestInfoEvent,
    SequentialBuilder,
    WorkflowOutputEvent,
    WorkflowRunState,
    WorkflowStatusEvent,
    tool,
)
from agent_framework.azure import AzureOpenAIChatClient
from azure.identity import AzureCliCredential


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
        SequentialBuilder()
        .participants([drafter, editor, finalizer])
        # Only enable request info for the editor agent
        .with_request_info(agents=["editor"])
        .build()
    )

    # Run the workflow with request info handling
    pending_responses: dict[str, AgentRequestInfoResponse] | None = None
    workflow_complete = False

    print("Starting document review workflow...")
    print("=" * 60)

    while not workflow_complete:
        # Run or continue the workflow
        stream = (
            workflow.send_responses_streaming(pending_responses)
            if pending_responses
            else workflow.run_stream("Write a brief introduction to artificial intelligence.")
        )

        pending_responses = None

        # Process events
        async for event in stream:
            if isinstance(event, RequestInfoEvent):
                if isinstance(event.data, AgentExecutorResponse):
                    # Display agent response and conversation context for review
                    print("\n" + "-" * 40)
                    print("REQUEST INFO: INPUT REQUESTED")
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

                    # Get feedback on the agent's response (approve or request iteration)
                    user_input = input("Your guidance (or 'skip' to approve): ")  # noqa: ASYNC250
                    if user_input.lower() == "skip":
                        user_input = AgentRequestInfoResponse.approve()
                    else:
                        user_input = AgentRequestInfoResponse.from_strings([user_input])

                    pending_responses = {event.request_id: user_input}
                    print("(Resuming workflow...)")

            elif isinstance(event, WorkflowOutputEvent):
                print("\n" + "=" * 60)
                print("WORKFLOW COMPLETE")
                print("=" * 60)
                print("Final output:")
                if event.data:
                    messages: list[ChatMessage] = event.data[-3:]
                    for msg in messages:
                        role = msg.role.value if msg.role else "unknown"
                        print(f"[{role}]: {msg.text}")
                workflow_complete = True

            elif isinstance(event, WorkflowStatusEvent) and event.state == WorkflowRunState.IDLE:
                workflow_complete = True


if __name__ == "__main__":
    asyncio.run(main())
