# Copyright (c) Microsoft. All rights reserved.

import asyncio
from collections.abc import AsyncIterable
from typing import Annotated, cast

from agent_framework import (
    ChatAgent,
    ChatMessage,
    HandoffBuilder,
    HandoffUserInputRequest,
    RequestInfoEvent,
    Role,
    WorkflowEvent,
    WorkflowOutputEvent,
    WorkflowRunState,
    WorkflowStatusEvent,
    ai_function,
)
from agent_framework.azure import AzureOpenAIChatClient
from azure.identity import AzureCliCredential

"""Sample: Simple handoff workflow with single-tier triage-to-specialist routing.

This sample demonstrates the basic handoff pattern where only the triage agent can
route to specialists. Specialists cannot hand off to other specialists - after any
specialist responds, control returns to the user (via the triage agent) for the next input.

Routing Pattern:
    User → Triage Agent → Specialist → Triage Agent → User → Triage Agent → ...

This is the simplest handoff configuration, suitable for straightforward support
scenarios where a triage agent dispatches to domain specialists, and each specialist
works independently.

For multi-tier specialist-to-specialist handoffs, see handoff_specialist_to_specialist.py.

Prerequisites:
    - `az login` (Azure CLI authentication)
    - Environment variables configured for AzureOpenAIChatClient (AZURE_OPENAI_ENDPOINT, etc.)

Key Concepts:
    - Single-tier routing: Only triage agent has handoff capabilities
    - Auto-registered handoff tools: HandoffBuilder automatically creates handoff tools
      for each participant, allowing the coordinator to transfer control to specialists
    - Termination condition: Controls when the workflow stops requesting user input
    - Request/response cycle: Workflow requests input, user responds, cycle continues
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


def create_agents(chat_client: AzureOpenAIChatClient) -> tuple[ChatAgent, ChatAgent, ChatAgent, ChatAgent]:
    """Create and configure the triage and specialist agents.

    The triage agent is responsible for:
    - Receiving all user input first
    - Deciding whether to handle the request directly or hand off to a specialist
    - Signaling handoff by calling one of the explicit handoff tools exposed to it

    Specialist agents are invoked only when the triage agent explicitly hands off to them.
    After a specialist responds, control returns to the triage agent, which then prompts
    the user for their next message.

    Returns:
        Tuple of (triage_agent, refund_agent, order_agent, return_agent)
    """
    # Triage agent: Acts as the frontline dispatcher
    triage_agent = chat_client.create_agent(
        instructions=(
            "You are frontline support triage. Route customer issues to the appropriate specialist agents "
            "based on the problem described."
        ),
        name="triage_agent",
    )

    # Refund specialist: Handles refund requests
    refund_agent = chat_client.create_agent(
        instructions="You process refund requests.",
        name="refund_agent",
        # In a real application, an agent can have multiple tools; here we keep it simple
        tools=[process_refund],
    )

    # Order/shipping specialist: Resolves delivery issues
    order_agent = chat_client.create_agent(
        instructions="You handle order and shipping inquiries.",
        name="order_agent",
        # In a real application, an agent can have multiple tools; here we keep it simple
        tools=[check_order_status],
    )

    # Return specialist: Handles return requests
    return_agent = chat_client.create_agent(
        instructions="You manage product return requests.",
        name="return_agent",
        # In a real application, an agent can have multiple tools; here we keep it simple
        tools=[process_return],
    )

    return triage_agent, refund_agent, order_agent, return_agent


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
        # WorkflowStatusEvent: Indicates workflow state changes
        if isinstance(event, WorkflowStatusEvent) and event.state in {
            WorkflowRunState.IDLE,
            WorkflowRunState.IDLE_WITH_PENDING_REQUESTS,
        }:
            print(f"\n[Workflow Status] {event.state.name}")

        # WorkflowOutputEvent: Contains the final conversation when workflow terminates
        elif isinstance(event, WorkflowOutputEvent):
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


async def main() -> None:
    """Main entry point for the handoff workflow demo.

    This function demonstrates:
    1. Creating triage and specialist agents
    2. Building a handoff workflow with custom termination condition
    3. Running the workflow with scripted user responses
    4. Processing events and handling user input requests

    The workflow uses scripted responses instead of interactive input to make
    the demo reproducible and testable. In a production application, you would
    replace the scripted_responses with actual user input collection.
    """
    # Initialize the Azure OpenAI chat client
    chat_client = AzureOpenAIChatClient(credential=AzureCliCredential())

    # Create all agents: triage + specialists
    triage, refund, order, support = create_agents(chat_client)

    # Build the handoff workflow
    # - participants: All agents that can participate in the workflow
    # - set_coordinator: The triage agent is designated as the coordinator, which means
    #   it receives all user input first and orchestrates handoffs to specialists
    # - with_termination_condition: Custom logic to stop the request/response loop.
    #   Without this, the default behavior continues requesting user input until max_turns
    #   is reached. Here we use a custom condition that checks if the conversation has ended
    #   naturally (when triage agent says something like "you're welcome").
    workflow = (
        HandoffBuilder(
            name="customer_support_handoff",
            participants=[triage, refund, order, support],
        )
        .set_coordinator(triage)
        .with_termination_condition(
            # Custom termination: Check if the triage agent has provided a closing message.
            # This looks for the last message being from triage_agent and containing "welcome",
            # which indicates the conversation has concluded naturally.
            lambda conversation: len(conversation) > 0
            and conversation[-1].author_name == "triage_agent"
            and "welcome" in conversation[-1].text.lower()
        )
        .build()
    )

    # Scripted user responses for reproducible demo
    # In a console application, replace this with:
    #   user_input = input("Your response: ")
    # or integrate with a UI/chat interface
    scripted_responses = [
        "My order 1234 arrived damaged and the packaging was destroyed. I'd like to return it.",
        "Thanks for resolving this.",
    ]

    # Start the workflow with the initial user message
    # run_stream() returns an async iterator of WorkflowEvent
    print("[Starting workflow with initial user message...]\n")
    initial_message = "Hello, I need assistance with my recent purchase."
    print(f"- User: {initial_message}")
    events = await _drain(workflow.run_stream(initial_message))
    pending_requests = _handle_events(events)

    # Process the request/response cycle
    # The workflow will continue requesting input until:
    # 1. The termination condition is met (4 user messages in this case), OR
    # 2. We run out of scripted responses
    while pending_requests and scripted_responses:
        # Get the next scripted response
        user_response = scripted_responses.pop(0)
        print(f"\n- User: {user_response}")

        # Send response(s) to all pending requests
        # In this demo, there's typically one request per cycle, but the API supports multiple
        responses = {req.request_id: user_response for req in pending_requests}

        # Send responses and get new events
        # We use send_responses_streaming() to get events as they occur, allowing us to
        # display agent responses in real-time and handle new requests as they arrive
        events = await _drain(workflow.send_responses_streaming(responses))
        pending_requests = _handle_events(events)

    """
    Sample Output:

    [Starting workflow with initial user message...]

    - User: Hello, I need assistance with my recent purchase.
    - triage_agent: Could you please provide more details about the issue you're experiencing with your recent purchase? This will help me route you to the appropriate specialist.

    [Workflow Status] IDLE_WITH_PENDING_REQUESTS

    - User: My order 1234 arrived damaged and the packaging was destroyed. I'd like to return it.
    - triage_agent: I've directed your request to our return agent, who will assist you with returning the damaged order. Thank you for your patience!
    - return_agent: The return for your order 1234 has been successfully initiated. You will receive return instructions via email shortly. If you have any other questions or need further assistance, feel free to ask!

    [Workflow Status] IDLE_WITH_PENDING_REQUESTS

    - User: Thanks for resolving this.

    === Final Conversation Snapshot ===
    - user: Hello, I need assistance with my recent purchase.
    - triage_agent: Could you please provide more details about the issue you're experiencing with your recent purchase? This will help me route you to the appropriate specialist.
    - user: My order 1234 arrived damaged and the packaging was destroyed. I'd like to return it.
    - triage_agent: I've directed your request to our return agent, who will assist you with returning the damaged order. Thank you for your patience!
    - return_agent: The return for your order 1234 has been successfully initiated. You will receive return instructions via email shortly. If you have any other questions or need further assistance, feel free to ask!
    - user: Thanks for resolving this.
    - triage_agent: You're welcome! If you have any more questions or need assistance in the future, feel free to reach out. Have a great day!
    ===================================

    [Workflow Status] IDLE
    """  # noqa: E501


if __name__ == "__main__":
    asyncio.run(main())
