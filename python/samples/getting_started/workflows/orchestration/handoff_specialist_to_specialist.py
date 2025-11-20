# Copyright (c) Microsoft. All rights reserved.

"""Sample: Multi-tier handoff workflow with specialist-to-specialist routing.

This sample demonstrates advanced handoff routing where specialist agents can hand off
to other specialists, enabling complex multi-tier workflows. Unlike the simple handoff
pattern (see handoff_simple.py), specialists here can delegate to other specialists
without returning control to the user until the specialist chain completes.

Routing Pattern:
    User → Triage → Specialist A → Specialist B → Back to User

This pattern is useful for complex support scenarios where different specialists need
to collaborate or escalate to each other before returning to the user. For example:
    - Replacement agent needs shipping info → hands off to delivery agent
    - Technical support needs billing info → hands off to billing agent
    - Level 1 support escalates to Level 2 → hands off to escalation agent

Configuration uses `.add_handoff()` to explicitly define the routing graph.

Prerequisites:
    - `az login` (Azure CLI authentication)
    - Environment variables configured for AzureOpenAIChatClient
"""

import asyncio
from collections.abc import AsyncIterable
from typing import cast

from agent_framework import (
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


def create_agents(chat_client: AzureOpenAIChatClient):
    """Create triage and specialist agents with multi-tier handoff capabilities.

    Returns:
        Tuple of (triage_agent, replacement_agent, delivery_agent, billing_agent)
    """
    triage = chat_client.create_agent(
        instructions=(
            "You are a customer support triage agent. Assess the user's issue and route appropriately:\n"
            "- For product replacement issues: call handoff_to_replacement_agent\n"
            "- For delivery/shipping inquiries: call handoff_to_delivery_agent\n"
            "- For billing/payment issues: call handoff_to_billing_agent\n"
            "Be concise and friendly."
        ),
        name="triage_agent",
    )

    replacement = chat_client.create_agent(
        instructions=(
            "You handle product replacement requests. Ask for order number and reason for replacement.\n"
            "If the user also needs shipping/delivery information, call handoff_to_delivery_agent to "
            "get tracking details. Otherwise, process the replacement and confirm with the user.\n"
            "Be concise and helpful."
        ),
        name="replacement_agent",
    )

    delivery = chat_client.create_agent(
        instructions=(
            "You handle shipping and delivery inquiries. Provide tracking information, estimated "
            "delivery dates, and address any delivery concerns.\n"
            "If billing issues come up, call handoff_to_billing_agent.\n"
            "Be concise and clear."
        ),
        name="delivery_agent",
    )

    billing = chat_client.create_agent(
        instructions=(
            "You handle billing and payment questions. Help with refunds, payment methods, "
            "and invoice inquiries. Be concise."
        ),
        name="billing_agent",
    )

    return triage, replacement, delivery, billing


async def _drain(stream: AsyncIterable[WorkflowEvent]) -> list[WorkflowEvent]:
    """Collect all events from an async stream into a list."""
    return [event async for event in stream]


def _handle_events(events: list[WorkflowEvent]) -> list[RequestInfoEvent]:
    """Process workflow events and extract pending user input requests."""
    requests: list[RequestInfoEvent] = []

    for event in events:
        if isinstance(event, WorkflowStatusEvent) and event.state in {
            WorkflowRunState.IDLE,
            WorkflowRunState.IDLE_WITH_PENDING_REQUESTS,
        }:
            print(f"[status] {event.state.name}")

        elif isinstance(event, WorkflowOutputEvent):
            conversation = cast(list[ChatMessage], event.data)
            if isinstance(conversation, list):
                print("\n=== Final Conversation ===")
                for message in conversation:
                    # Filter out messages with no text (tool calls)
                    if not message.text.strip():
                        continue
                    speaker = message.author_name or message.role.value
                    print(f"- {speaker}: {message.text}")
                print("==========================")

        elif isinstance(event, RequestInfoEvent):
            if isinstance(event.data, HandoffUserInputRequest):
                _print_handoff_request(event.data)
            requests.append(event)

    return requests


def _print_handoff_request(request: HandoffUserInputRequest) -> None:
    """Display a user input request with conversation context."""
    print("\n=== User Input Requested ===")
    # Filter out messages with no text for cleaner display
    messages_with_text = [msg for msg in request.conversation if msg.text.strip()]
    print(f"Last {len(messages_with_text)} messages in conversation:")
    for message in messages_with_text[-5:]:  # Show last 5 for brevity
        speaker = message.author_name or message.role.value
        text = message.text[:100] + "..." if len(message.text) > 100 else message.text
        print(f"  {speaker}: {text}")
    print("============================")


async def main() -> None:
    """Demonstrate specialist-to-specialist handoffs in a multi-tier support scenario.

    This sample shows:
    1. Triage agent routes to replacement specialist
    2. Replacement specialist hands off to delivery specialist
    3. Delivery specialist can hand off to billing if needed
    4. All transitions are seamless without returning to user until complete

    The workflow configuration explicitly defines which agents can hand off to which others:
    - triage_agent → replacement_agent, delivery_agent, billing_agent
    - replacement_agent → delivery_agent, billing_agent
    - delivery_agent → billing_agent
    """
    chat_client = AzureOpenAIChatClient(credential=AzureCliCredential())
    triage, replacement, delivery, billing = create_agents(chat_client)

    # Configure multi-tier handoffs using fluent add_handoff() API
    # This allows specialists to hand off to other specialists
    workflow = (
        HandoffBuilder(
            name="multi_tier_support",
            participants=[triage, replacement, delivery, billing],
        )
        .set_coordinator(triage)
        .add_handoff(triage, [replacement, delivery, billing])  # Triage can route to any specialist
        .add_handoff(replacement, [delivery, billing])  # Replacement can delegate to delivery or billing
        .add_handoff(delivery, billing)  # Delivery can escalate to billing
        # Termination condition: Stop when more than 3 user messages exist.
        # This allows agents to respond to the 3rd user message before the 4th triggers termination.
        # In this sample: initial message + 3 scripted responses = 4 messages, then workflow ends.
        .with_termination_condition(lambda conv: sum(1 for msg in conv if msg.role.value == "user") > 3)
        .build()
    )

    # Scripted user responses simulating a multi-tier handoff scenario
    # Note: The initial run_stream() call sends the first user message,
    # then these scripted responses are sent in sequence (total: 4 user messages).
    # A 5th response triggers termination after agents respond to the 4th message.
    scripted_responses = [
        "I need help with order 12345. I want a replacement and need to know when it will arrive.",
        "The item arrived damaged. I'd like a replacement shipped to the same address.",
        "Great! Can you confirm the shipping cost won't be charged again?",
        "Thank you!",  # Final response to trigger termination after billing agent answers
    ]

    print("\n" + "=" * 80)
    print("SPECIALIST-TO-SPECIALIST HANDOFF DEMONSTRATION")
    print("=" * 80)
    print("\nScenario: Customer needs replacement + shipping info + billing confirmation")
    print("Expected flow: User → Triage → Replacement → Delivery → Billing → User")
    print("=" * 80 + "\n")

    # Start workflow with initial message
    print(f"[User]: {scripted_responses[0]}\n")
    events = await _drain(workflow.run_stream(scripted_responses[0]))
    pending_requests = _handle_events(events)

    # Process scripted responses
    response_index = 1
    while pending_requests and response_index < len(scripted_responses):
        user_response = scripted_responses[response_index]
        print(f"\n[User]: {user_response}\n")

        responses = {req.request_id: user_response for req in pending_requests}
        events = await _drain(workflow.send_responses_streaming(responses))
        pending_requests = _handle_events(events)

        response_index += 1

    """
    Sample Output:

    ================================================================================
    SPECIALIST-TO-SPECIALIST HANDOFF DEMONSTRATION
    ================================================================================

    Scenario: Customer needs replacement + shipping info + billing confirmation
    Expected flow: User → Triage → Replacement → Delivery → Billing → User
    ================================================================================

    [User]: I need help with order 12345. I want a replacement and need to know when it will arrive.


    === User Input Requested ===
    Last 5 messages in conversation:
    user: I need help with order 12345. I want a replacement and need to know when it will arrive.
    triage_agent: I am connecting you to our replacement agent to assist with your replacement request and to our deli...
    replacement_agent: I have connected you to our agents who will assist with your replacement request for order 12345 and...
    delivery_agent: For your replacement request and delivery details regarding order 12345, I'll connect you to the app...
    billing_agent: I don’t have access to order details. Please contact the seller or customer service directly for rep...
    ============================
    [status] IDLE_WITH_PENDING_REQUESTS

    [User]: The item arrived damaged. I'd like a replacement shipped to the same address.


    === User Input Requested ===
    Last 8 messages in conversation:
    delivery_agent: For your replacement request and delivery details regarding order 12345, I'll connect you to the app...
    billing_agent: I don’t have access to order details. Please contact the seller or customer service directly for rep...
    user: The item arrived damaged. I'd like a replacement shipped to the same address.
    triage_agent: I'm connecting you to our replacement agent who will assist you with getting a replacement shipped t...
    replacement_agent: Thank you for the info. I'll start the replacement process for your damaged item on order 12345 and ...
    ============================
    [status] IDLE_WITH_PENDING_REQUESTS

    [User]: Great! Can you confirm the shipping cost won't be charged again?


    === User Input Requested ===
    Last 11 messages in conversation:
    triage_agent: I'm connecting you to our replacement agent who will assist you with getting a replacement shipped t...
    replacement_agent: Thank you for the info. I'll start the replacement process for your damaged item on order 12345 and ...
    user: Great! Can you confirm the shipping cost won't be charged again?
    triage_agent: I'm connecting you to our billing agent who can confirm whether the shipping cost will be charged ag...
    billing_agent: Replacements for damaged items are typically shipped at no extra shipping cost. I recommend confirmi...
    ============================
    [status] IDLE_WITH_PENDING_REQUESTS

    [User]: Thank you!


    === Final Conversation ===
    - user: I need help with order 12345. I want a replacement and need to know when it will arrive.
    - triage_agent: I am connecting you to our replacement agent to assist with your replacement request and to our delivery agent who can provide information on the arrival of your replacement. They will help you shortly!
    - replacement_agent: I have connected you to our agents who will assist with your replacement request for order 12345 and provide shipping and delivery information. They will help you with the details shortly. If you have any other questions, feel free to ask!
    - delivery_agent: For your replacement request and delivery details regarding order 12345, I'll connect you to the appropriate agent who can assist with both billing and delivery concerns. They will provide you with the estimated arrival date and replacement process. Is there anything else you'd like to know meanwhile?
    - billing_agent: I don’t have access to order details. Please contact the seller or customer service directly for replacement and delivery info on order 12345. If you need help with billing, refunds, or payments, I can assist!
    - user: The item arrived damaged. I'd like a replacement shipped to the same address.
    - triage_agent: I'm connecting you to our replacement agent who will assist you with getting a replacement shipped to the same address for the damaged item. They will help you shortly!
    - replacement_agent: Thank you for the info. I'll start the replacement process for your damaged item on order 12345 and arrange to ship it to the same address. Please hold on a moment while I proceed.
    Thank you for providing the reason. I will process a replacement for the damaged item from order 12345 and arrange the shipment to the same address. Please hold on a moment while I take care of this.
    - user: Great! Can you confirm the shipping cost won't be charged again?
    - triage_agent: I'm connecting you to our billing agent who can confirm whether the shipping cost will be charged again for the replacement of your damaged item. They will assist you shortly!
    - billing_agent: Replacements for damaged items are typically shipped at no extra shipping cost. I recommend confirming with the replacements or billing department to be sure. Let me know if you’d like me to connect you!
    - user: Thank you!
    ==========================
    [status] IDLE
    """  # noqa: E501


if __name__ == "__main__":
    asyncio.run(main())
