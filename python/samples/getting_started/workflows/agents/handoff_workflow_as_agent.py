# Copyright (c) Microsoft. All rights reserved.

import asyncio
from collections.abc import Mapping
from typing import Any

from agent_framework import (
    ChatAgent,
    ChatMessage,
    FunctionCallContent,
    FunctionResultContent,
    HandoffBuilder,
    HandoffUserInputRequest,
    Role,
    WorkflowAgent,
)
from agent_framework.azure import AzureOpenAIChatClient
from azure.identity import AzureCliCredential

"""
Sample: Handoff Workflow as Agent with Human-in-the-Loop

Purpose:
This sample demonstrates how to use a HandoffBuilder workflow as an agent via
`.as_agent()`, enabling human-in-the-loop interactions through the standard
agent interface. The handoff pattern routes user requests through a triage agent
to specialist agents, with the workflow requesting user input as needed.

When using a handoff workflow as an agent:
1. The workflow emits `HandoffUserInputRequest` when it needs user input
2. `WorkflowAgent` converts this to a `FunctionCallContent` named "request_info"
3. The caller extracts `HandoffUserInputRequest` from the function call arguments
4. The caller provides a response via `FunctionResultContent`

This differs from running the workflow directly:
- Direct workflow: Use `workflow.run_stream()` and `workflow.send_responses_streaming()`
- As agent: Use `agent.run()` with `FunctionCallContent`/`FunctionResultContent` messages

Key Concepts:
- HandoffBuilder: Creates triage-to-specialist routing workflows
- WorkflowAgent: Wraps workflows to expose them as standard agents
- HandoffUserInputRequest: Contains conversation context and the awaiting agent
- FunctionCallContent/FunctionResultContent: Standard agent interface for HITL

Prerequisites:
- `az login` (Azure CLI authentication)
- Environment variables configured for AzureOpenAIChatClient (AZURE_OPENAI_ENDPOINT, etc.)
"""


def create_agents(chat_client: AzureOpenAIChatClient) -> tuple[ChatAgent, ChatAgent, ChatAgent, ChatAgent]:
    """Create and configure the triage and specialist agents.

    The triage agent dispatches requests to the appropriate specialist.
    Specialists handle their domain-specific queries.

    Returns:
        Tuple of (triage_agent, refund_agent, order_agent, support_agent)
    """
    triage = chat_client.create_agent(
        instructions=(
            "You are frontline support triage. Read the latest user message and decide whether "
            "to hand off to refund_agent, order_agent, or support_agent. Provide a brief natural-language "
            "response for the user. When delegation is required, call the matching handoff tool "
            "(`handoff_to_refund_agent`, `handoff_to_order_agent`, or `handoff_to_support_agent`)."
        ),
        name="triage_agent",
    )

    refund = chat_client.create_agent(
        instructions=(
            "You handle refund workflows. Ask for any order identifiers you require and outline the refund steps."
        ),
        name="refund_agent",
    )

    order = chat_client.create_agent(
        instructions=(
            "You resolve shipping and fulfillment issues. Clarify the delivery problem and describe the actions "
            "you will take to remedy it."
        ),
        name="order_agent",
    )

    support = chat_client.create_agent(
        instructions=(
            "You are a general support agent. Offer empathetic troubleshooting and gather missing details if the "
            "issue does not match other specialists."
        ),
        name="support_agent",
    )

    return triage, refund, order, support


def extract_handoff_request(
    response_messages: list[ChatMessage],
) -> tuple[FunctionCallContent, HandoffUserInputRequest]:
    """Extract the HandoffUserInputRequest from agent response messages.

    When a handoff workflow running as an agent needs user input, it emits a
    FunctionCallContent with name="request_info" containing the HandoffUserInputRequest.

    Args:
        response_messages: Messages from the agent response

    Returns:
        Tuple of (function_call, handoff_request)

    Raises:
        ValueError: If no request_info function call is found or payload is invalid
    """
    for message in response_messages:
        for content in message.contents:
            if isinstance(content, FunctionCallContent) and content.name == WorkflowAgent.REQUEST_INFO_FUNCTION_NAME:
                # Parse the function arguments to extract the HandoffUserInputRequest
                args = content.arguments
                if isinstance(args, str):
                    request_args = WorkflowAgent.RequestInfoFunctionArgs.from_json(args)
                elif isinstance(args, Mapping):
                    request_args = WorkflowAgent.RequestInfoFunctionArgs.from_dict(dict(args))
                else:
                    raise ValueError("Unexpected argument type for request_info function call.")

                payload: Any = request_args.data
                if not isinstance(payload, HandoffUserInputRequest):
                    raise ValueError(
                        f"Expected HandoffUserInputRequest in request_info payload, got {type(payload).__name__}"
                    )

                return content, payload

    raise ValueError("No request_info function call found in response messages.")


def print_conversation(request: HandoffUserInputRequest) -> None:
    """Display the conversation history from a HandoffUserInputRequest."""
    print("\n=== Conversation History ===")
    for message in request.conversation:
        speaker = message.author_name or message.role.value
        print(f"  [{speaker}]: {message.text}")
    print(f"  [Awaiting]: {request.awaiting_agent_id}")
    print("============================")


async def main() -> None:
    """Main entry point demonstrating handoff workflow as agent.

    This demo:
    1. Builds a handoff workflow with triage and specialist agents
    2. Converts it to an agent using .as_agent()
    3. Runs a multi-turn conversation with scripted user responses
    4. Demonstrates the FunctionCallContent/FunctionResultContent pattern for HITL
    """
    print("Starting Handoff Workflow as Agent Demo")
    print("=" * 55)

    # Initialize the Azure OpenAI chat client
    chat_client = AzureOpenAIChatClient(credential=AzureCliCredential())

    # Create agents
    triage, refund, order, support = create_agents(chat_client)

    # Build the handoff workflow and convert to agent
    # Termination condition: stop after 4 user messages
    agent = (
        HandoffBuilder(
            name="customer_support_handoff",
            participants=[triage, refund, order, support],
        )
        .set_coordinator("triage_agent")
        .with_termination_condition(lambda conv: sum(1 for msg in conv if msg.role.value == "user") >= 4)
        .build()
        .as_agent()  # Convert workflow to agent interface
    )

    # Scripted user responses for reproducible demo
    scripted_responses = [
        "My order 1234 arrived damaged and the packaging was destroyed.",
        "Yes, I'd like a refund if that's possible.",
        "Thanks for your help!",
    ]

    # Start the conversation
    print("\n[User]: Hello, I need assistance with my recent purchase.")
    response = await agent.run("Hello, I need assistance with my recent purchase.")

    # Process conversation turns until workflow completes or responses exhausted
    while True:
        # Check if the agent is requesting user input
        try:
            function_call, handoff_request = extract_handoff_request(response.messages)
        except ValueError:
            # No request_info call found - workflow has completed
            print("\n[Workflow completed - no pending requests]")
            if response.messages:
                final_text = response.messages[-1].text
                if final_text:
                    print(f"[Final response]: {final_text}")
            break

        # Display the conversation context
        print_conversation(handoff_request)

        # Get the next scripted response
        if not scripted_responses:
            print("\n[No more scripted responses - ending conversation]")
            break

        user_input = scripted_responses.pop(0)

        print(f"\n[User responding]: {user_input}")

        # Create the function result to send back to the agent
        # The result is the user's text response which gets converted to ChatMessage
        function_result = FunctionResultContent(
            call_id=function_call.call_id,
            result=user_input,
        )

        # Send the response back to the agent
        response = await agent.run(ChatMessage(role=Role.TOOL, contents=[function_result]))

    print("\n" + "=" * 55)
    print("Demo completed!")


if __name__ == "__main__":
    print("Initializing Handoff Workflow as Agent Sample...")
    asyncio.run(main())
