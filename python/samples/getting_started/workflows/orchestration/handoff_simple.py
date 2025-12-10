# Copyright (c) Microsoft. All rights reserved.

import asyncio
from collections.abc import AsyncIterable
from typing import cast

from agent_framework import (
    ChatAgent,
    ChatMessage,
    HandoffBuilder,
    HandoffUserInputRequest,
    RequestInfoEvent,
    WorkflowEvent,
    WorkflowOutputEvent,
    WorkflowRunState,
    WorkflowStatusEvent,
)
from agent_framework.azure import AzureOpenAIChatClient
from azure.identity import AzureCliCredential

"""Sample: Simple handoff workflow with single-tier triage-to-specialist routing.

This sample demonstrates the basic handoff pattern where only the triage agent can
route to specialists. Specialists cannot hand off to other specialists - after any
specialist responds, control returns to the user for the next input.

Routing Pattern:
    User → Triage Agent → Specialist → Back to User → Triage Agent → ...

This is the simplest handoff configuration, suitable for straightforward support
scenarios where a triage agent dispatches to domain specialists, and each specialist
works independently.

For multi-tier specialist-to-specialist handoffs, see handoff_specialist_to_specialist.py.

Prerequisites:
    - `az login` (Azure CLI authentication)
    - Environment variables configured for AzureOpenAIChatClient (AZURE_OPENAI_ENDPOINT, etc.)

Key Concepts:
    - Single-tier routing: Only triage agent has handoff capabilities
    - Auto-registered handoff tools: HandoffBuilder creates tools automatically
    - Termination condition: Controls when the workflow stops requesting user input
    - Request/response cycle: Workflow requests input, user responds, cycle continues
"""


def create_agents(chat_client: AzureOpenAIChatClient) -> tuple[ChatAgent, ChatAgent, ChatAgent, ChatAgent]:
    """Create and configure the triage and specialist agents.

    The triage agent is responsible for:
    - Receiving all user input first
    - Deciding whether to handle the request directly or hand off to a specialist
    - Signaling handoff by calling one of the explicit handoff tools exposed to it

    Specialist agents are invoked only when the triage agent explicitly hands off to them.
    After a specialist responds, control returns to the triage agent.

    Returns:
        Tuple of (triage_agent, refund_agent, order_agent, support_agent)
    """
    # Triage agent: Acts as the frontline dispatcher
    # NOTE: The instructions explicitly tell it to call the correct handoff tool when routing.
    # The HandoffBuilder intercepts these tool calls and routes to the matching specialist.
    triage = chat_client.create_agent(
        instructions=(
            "You are frontline support triage. Read the latest user message and decide whether "
            "to hand off to refund_agent, order_agent, or support_agent. Provide a brief natural-language "
            "response for the user. When delegation is required, call the matching handoff tool "
            "(`handoff_to_refund_agent`, `handoff_to_order_agent`, or `handoff_to_support_agent`)."
        ),
        name="triage_agent",
    )

    # Refund specialist: Handles refund requests
    refund = chat_client.create_agent(
        instructions=(
            "You handle refund workflows. Ask for any order identifiers you require and outline the refund steps."
        ),
        name="refund_agent",
    )

    # Order/shipping specialist: Resolves delivery issues
    order = chat_client.create_agent(
        instructions=(
            "You resolve shipping and fulfillment issues. Clarify the delivery problem and describe the actions "
            "you will take to remedy it."
        ),
        name="order_agent",
    )

    # General support specialist: Fallback for other issues
    support = chat_client.create_agent(
        instructions=(
            "You are a general support agent. Offer empathetic troubleshooting and gather missing details if the "
            "issue does not match other specialists."
        ),
        name="support_agent",
    )

    return triage, refund, order, support


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
            print(f"[status] {event.state.name}")

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
                _print_handoff_request(event.data)
            requests.append(event)

    return requests


def _print_handoff_request(request: HandoffUserInputRequest) -> None:
    """Display a user input request prompt with conversation context.

    The HandoffUserInputRequest contains the full conversation history so far,
    allowing the user to see what's been discussed before providing their next input.

    Args:
        request: The user input request containing conversation and prompt
    """
    print("\n=== User Input Requested ===")
    for message in request.conversation:
        speaker = message.author_name or message.role.value
        print(f"- {speaker}: {message.text}")
    print("============================")


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
    # - participants: All agents that can participate (triage MUST be first or explicitly set as set_coordinator)
    # - set_coordinator: The triage agent receives all user input first
    # - with_termination_condition: Custom logic to stop the request/response loop
    #   Default is 10 user messages; here we terminate after 4 to match our scripted demo
    workflow = (
        HandoffBuilder(
            name="customer_support_handoff",
            participants=[triage, refund, order, support],
        )
        .set_coordinator("triage_agent")
        .with_termination_condition(
            # Terminate after 4 user messages (initial + 3 scripted responses)
            # Count only USER role messages to avoid counting agent responses
            lambda conv: sum(1 for msg in conv if msg.role.value == "user") >= 4
        )
        .build()
    )

    # Scripted user responses for reproducible demo
    # In a console application, replace this with:
    #   user_input = input("Your response: ")
    # or integrate with a UI/chat interface
    scripted_responses = [
        "My order 1234 arrived damaged and the packaging was destroyed.",
        "Yes, I'd like a refund if that's possible.",
        "Thanks for resolving this.",
    ]

    # Start the workflow with the initial user message
    # run_stream() returns an async iterator of WorkflowEvent
    print("\n[Starting workflow with initial user message...]")
    events = await _drain(workflow.run_stream("Hello, I need assistance with my recent purchase."))
    pending_requests = _handle_events(events)

    # Process the request/response cycle
    # The workflow will continue requesting input until:
    # 1. The termination condition is met (4 user messages in this case), OR
    # 2. We run out of scripted responses
    while pending_requests and scripted_responses:
        # Get the next scripted response
        user_response = scripted_responses.pop(0)
        print(f"\n[User responding: {user_response}]")

        # Send response(s) to all pending requests
        # In this demo, there's typically one request per cycle, but the API supports multiple
        responses = {req.request_id: user_response for req in pending_requests}

        # Send responses and get new events
        events = await _drain(workflow.send_responses_streaming(responses))
        pending_requests = _handle_events(events)

    """
    Sample Output:

    [Starting workflow with initial user message...]

    === User Input Requested ===
    - user: Hello, I need assistance with my recent purchase.
    - triage_agent: I'd be happy to help you with your recent purchase. Could you please provide more details about the issue you're experiencing?
    ============================
    [status] IDLE_WITH_PENDING_REQUESTS

    [User responding: My order 1234 arrived damaged and the packaging was destroyed.]

    === User Input Requested ===
    - user: Hello, I need assistance with my recent purchase.
    - triage_agent: I'd be happy to help you with your recent purchase. Could you please provide more details about the issue you're experiencing?
    - user: My order 1234 arrived damaged and the packaging was destroyed.
    - triage_agent: I'm sorry to hear that your order arrived damaged and the packaging was destroyed. I will connect you with a specialist who can assist you further with this issue.

    Tool Call: handoff_to_support_agent (awaiting approval)
    - support_agent: I'm so sorry to hear that your order arrived in such poor condition. I'll help you get this sorted out.

    To assist you better, could you please let me know:
    - Which item(s) from order 1234 arrived damaged?
    - Could you describe the damage, or provide photos if possible?
    - Would you prefer a replacement or a refund?

    Once I have this information, I can help resolve this for you as quickly as possible.
    ============================
    [status] IDLE_WITH_PENDING_REQUESTS

    [User responding: Yes, I'd like a refund if that's possible.]

    === User Input Requested ===
    - user: Hello, I need assistance with my recent purchase.
    - triage_agent: I'd be happy to help you with your recent purchase. Could you please provide more details about the issue you're experiencing?
    - user: My order 1234 arrived damaged and the packaging was destroyed.
    - triage_agent: I'm sorry to hear that your order arrived damaged and the packaging was destroyed. I will connect you with a specialist who can assist you further with this issue.

    Tool Call: handoff_to_support_agent (awaiting approval)
    - support_agent: I'm so sorry to hear that your order arrived in such poor condition. I'll help you get this sorted out.

    To assist you better, could you please let me know:
    - Which item(s) from order 1234 arrived damaged?
    - Could you describe the damage, or provide photos if possible?
    - Would you prefer a replacement or a refund?

    Once I have this information, I can help resolve this for you as quickly as possible.
    - user: Yes, I'd like a refund if that's possible.
    - triage_agent: Thank you for letting me know you'd prefer a refund. I'll connect you with a specialist who can process your refund request.

    Tool Call: handoff_to_refund_agent (awaiting approval)
    - refund_agent: Thank you for confirming that you'd like a refund for order 1234.

    Here's what will happen next:

    ...

    Tool Call: handoff_to_refund_agent (awaiting approval)
    - refund_agent: Thank you for confirming that you'd like a refund for order 1234.

    Here's what will happen next:

    **1. Verification:**
    I will need to verify a few more details to proceed.
    - Can you confirm the items in order 1234 that arrived damaged?
    - Do you have any photos of the damaged items/packaging? (Photos help speed up the process.)

    **2. Refund Request Submission:**
    - Once I have the details, I will submit your refund request for review.

    **3. Return Instructions (if needed):**
    - In some cases, we may provide instructions on how to return the damaged items.
    - You will receive a prepaid return label if necessary.

    **4. Refund Processing:**
    - After your request is approved (and any returns are received if required), your refund will be processed.
    - Refunds usually appear on your original payment method within 5-10 business days.

    Could you please reply with the specific item(s) damaged and, if possible, attach photos? This will help me get your refund started right away.
    - user: Thanks for resolving this.
    ===================================
    [status] IDLE
    """  # noqa: E501


if __name__ == "__main__":
    asyncio.run(main())
