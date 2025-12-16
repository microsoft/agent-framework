# Copyright (c) Microsoft. All rights reserved.

import asyncio
import logging
from collections.abc import AsyncIterable
from typing import cast

from agent_framework import (
    ChatAgent,
    ChatMessage,
    HandoffBuilder,
    HandoffUserInputRequest,
    RequestInfoEvent,
    Role,
    Workflow,
    WorkflowEvent,
    WorkflowOutputEvent,
    ai_function,
)
from agent_framework.azure import AzureOpenAIChatClient
from azure.identity import AzureCliCredential
from typing import Annotated

logging.basicConfig(level=logging.ERROR)

"""Sample: Autonomous handoff workflow with agent factory.

This sample demonstrates how to use participant factories in HandoffBuilder to create
agents dynamically.

Using participant factories allows you to set up proper state isolation between workflow
instances created by the same builder. This is particularly useful when you need to handle
requests or tasks in parallel with stateful participants.

Routing Pattern:
    User -> Coordinator -> Specialist (iterates N times) -> Handoff -> Final Output

Prerequisites:
    - `az login` (Azure CLI authentication)
    - Environment variables for AzureOpenAIChatClient (AZURE_OPENAI_ENDPOINT, etc.)

Key Concepts:
    - Participant factories: create agents via factory functions for isolation
"""


@ai_function
def process_refund(order_number: Annotated[str, "Order number to process refund for"]) -> str:
    """Simulated function to process a refund for a given order number."""
    return f"Refund processed successfully for order {order_number}."


@ai_function
def check_order_status(order_number: Annotated[str, "Order number to check status for"]) -> str:
    """Simulated function to check the status of a given order number."""
    return f"Order {order_number} is currently being processed and will ship in 2 business days."


@ai_function
def process_return(order_number: Annotated[str, "Order number to process return for"]) -> str:
    """Simulated function to process a return for a given order number."""
    return f"Return initiated successfully for order {order_number}. You will receive return instructions via email."


def create_triage_agent() -> ChatAgent:
    """Factory function to create a triage agent instance."""
    return AzureOpenAIChatClient(credential=AzureCliCredential()).create_agent(
        instructions=(
            "You are frontline support triage. Route customer issues to the appropriate specialist agents "
            "based on the problem described."
        ),
        name="triage_agent",
    )


def create_refund_agent() -> ChatAgent:
    """Factory function to create a refund agent instance."""
    return AzureOpenAIChatClient(credential=AzureCliCredential()).create_agent(
        instructions="You process refund requests.",
        name="refund_agent",
        # In a real application, an agent can have multiple tools; here we keep it simple
        tools=[process_refund],
    )


def create_order_status_agent() -> ChatAgent:
    """Factory function to create an order status agent instance."""
    return AzureOpenAIChatClient(credential=AzureCliCredential()).create_agent(
        instructions="You handle order and shipping inquiries.",
        name="order_agent",
        # In a real application, an agent can have multiple tools; here we keep it simple
        tools=[check_order_status],
    )


def create_return_agent() -> ChatAgent:
    """Factory function to create a return agent instance."""
    return AzureOpenAIChatClient(credential=AzureCliCredential()).create_agent(
        instructions="You manage product return requests.",
        name="return_agent",
        # In a real application, an agent can have multiple tools; here we keep it simple
        tools=[process_return],
    )


async def _drain(stream: AsyncIterable[WorkflowEvent]) -> list[WorkflowEvent]:
    """Collect all events from an async stream into a list.

    This helper drains the workflow's event stream so we can process events
    synchronously after each workflow step completes.

    Args:
        stream: Async iterable of WorkflowEvent

    Returns:
        List of all events from the stream
    """
    return [event async for event in stream]


def _handle_events(events: list[WorkflowEvent]) -> list[RequestInfoEvent]:
    """Process workflow events and extract any pending user input requests.

    This function inspects each event type and:
    - Prints workflow status changes (IDLE, IDLE_WITH_PENDING_REQUESTS, etc.)
    - Displays final conversation snapshots when workflow completes
    - Prints user input request prompts
    - Collects all RequestInfoEvent instances for response handling

    Args:
        events: List of WorkflowEvent to process

    Returns:
        List of RequestInfoEvent representing pending user input requests
    """
    requests: list[RequestInfoEvent] = []

    for event in events:
        # WorkflowOutputEvent: Contains the final conversation when workflow terminates
        if isinstance(event, WorkflowOutputEvent):
            conversation = cast(list[ChatMessage], event.data)
            if isinstance(conversation, list):
                print("\n=== Final Conversation Snapshot ===")
                for message in conversation:
                    speaker = message.author_name or message.role.value
                    print(f"- {speaker}: {message.text}")
                print("===================================")

        # RequestInfoEvent: Workflow is requesting user input
        elif isinstance(event, RequestInfoEvent):
            if isinstance(event.data, HandoffUserInputRequest):
                _print_agent_responses_since_last_user_message(event.data)
            requests.append(event)

    return requests


def _print_agent_responses_since_last_user_message(request: HandoffUserInputRequest) -> None:
    """Display agent responses since the last user message in a handoff request.

    The HandoffUserInputRequest contains the full conversation history so far,
    allowing the user to see what's been discussed before providing their next input.

    Args:
        request: The user input request containing conversation and prompt
    """
    if not request.conversation:
        raise RuntimeError("HandoffUserInputRequest missing conversation history.")

    # Reverse iterate to collect agent responses since last user message
    agent_responses: list[ChatMessage] = []
    for message in request.conversation[::-1]:
        if message.role == Role.USER:
            break
        agent_responses.append(message)

    # Print agent responses in original order
    agent_responses.reverse()
    for message in agent_responses:
        speaker = message.author_name or message.role.value
        print(f"- {speaker}: {message.text}")


async def _run_Workflow(workflow: Workflow, user_inputs: list[str]) -> None:
    """Run the workflow with the given user input and display events."""
    print(f"- User: {user_inputs[0]}")
    events = await _drain(workflow.run_stream(user_inputs[0]))
    pending_requests = _handle_events(events)

    # Process the request/response cycle
    # The workflow will continue requesting input until:
    # 1. The termination condition is met (4 user messages in this case), OR
    # 2. We run out of scripted responses
    while pending_requests and user_inputs[1:]:
        # Get the next scripted response
        user_response = user_inputs.pop(1)
        print(f"\n- User: {user_response}")

        # Send response(s) to all pending requests
        # In this demo, there's typically one request per cycle, but the API supports multiple
        responses = {req.request_id: user_response for req in pending_requests}

        # Send responses and get new events
        # We use send_responses_streaming() to get events as they occur, allowing us to
        # display agent responses in real-time and handle new requests as they arrive
        events = await _drain(workflow.send_responses_streaming(responses))
        pending_requests = _handle_events(events)


async def main() -> None:
    """Run the autonomous handoff workflow with participant factories."""
    # Build the handoff workflow using participant factories
    workflow_builder = (
        HandoffBuilder(
            name="Autonomous Handoff with Participant Factories",
            participant_factories={
                "triage": create_triage_agent,
                "refund": create_refund_agent,
                "order_status": create_order_status_agent,
                "return": create_return_agent,
            },
        )
        .set_coordinator("triage")
        .with_termination_condition(
            # Custom termination: Check if the triage agent has provided a closing message.
            # This looks for the last message being from triage_agent and containing "welcome",
            # which indicates the conversation has concluded naturally.
            lambda conversation: len(conversation) > 0
            and conversation[-1].author_name == "triage_agent"
            and "welcome" in conversation[-1].text.lower()
        )
    )

    # Scripted user responses for reproducible demo
    # In a console application, replace this with:
    #   user_input = input("Your response: ")
    # or integrate with a UI/chat interface
    user_inputs = [
        "Hello, I need assistance with my recent purchase.",
        "My order 1234 arrived damaged and the packaging was destroyed. I'd like to return it.",
        "Is my return being processed?",
        "Thanks for resolving this.",
    ]

    workflow_a = workflow_builder.build()
    print("=== Running workflow_a ===")
    await _run_Workflow(workflow_a, list(user_inputs))

    workflow_b = workflow_builder.build()
    print("=== Running workflow_b ===")
    # Only provide the last two inputs to workflow_b to demonstrate state isolation
    # The agents in this workflow have no prior context thus should not have knowledge of
    # order 1234 or previous interactions.
    await _run_Workflow(workflow_b, user_inputs[2:])
    """
    Expected behavior:
    - workflow_a and workflow_b maintain separate states for their participants.
    - Each workflow processes its requests independently without interference.
    - workflow_a will answer the follow-up request based on its own conversation history,
      while workflow_b will provide a general answer without prior context.
    """


if __name__ == "__main__":
    asyncio.run(main())
