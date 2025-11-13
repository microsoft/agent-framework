# Copyright (c) Microsoft. All rights reserved.

import asyncio
from collections.abc import AsyncIterable
from typing import cast

from agent_framework import (
    ChatAgent,
    HandoffBuilder,
    HandoffUserInputRequest,
    RequestInfoEvent,
    WorkflowEvent,
    WorkflowOutputEvent,
)
from agent_framework.azure import AzureOpenAIChatClient
from azure.identity import AzureCliCredential

"""Sample: Handoff workflow with return-to-previous routing enabled.

This interactive sample demonstrates the return-to-previous feature where user inputs
route directly back to the specialist currently handling their request, rather than
always going through the coordinator for re-evaluation.

Routing Pattern (with return-to-previous enabled):
    User -> Coordinator -> Technical Support -> User -> Technical Support -> ...

Routing Pattern (default, without return-to-previous):
    User -> Coordinator -> Technical Support -> User -> Coordinator -> Technical Support -> ...

This is useful when a specialist needs multiple turns with the user to gather
information or resolve an issue, avoiding unnecessary coordinator involvement.

Specialist-to-Specialist Handoff:
    When a user's request changes to a topic outside the current specialist's domain,
    the specialist can hand off DIRECTLY to another specialist without going back through
    the coordinator:

    User -> Coordinator -> Technical Support -> User -> Technical Support (billing question)
    -> Billing -> User -> Billing ...

Example Interaction:
    1. User reports a technical issue
    2. Coordinator routes to technical support specialist
    3. Technical support asks clarifying questions
    4. User provides details (routes directly back to technical support)
    5. Technical support continues troubleshooting with full context
    6. Issue resolved, user asks about billing
    7. Technical support hands off DIRECTLY to billing specialist
    8. Billing specialist helps with payment
    9. User continues with billing (routes directly to billing)

Prerequisites:
    - `az login` (Azure CLI authentication)
    - Environment variables configured for AzureOpenAIChatClient (AZURE_OPENAI_ENDPOINT, etc.)

Usage:
    Run the script and interact with the support workflow by typing your requests.
    Type 'exit' or 'quit' to end the conversation.

Key Concepts:
    - Return-to-previous: Direct routing to current agent handling the conversation
    - Current agent tracking: Framework remembers which agent is actively helping the user
    - Context preservation: Specialist maintains full conversation context
    - Domain switching: Specialists can hand back to coordinator when topic changes
"""


def create_agents(chat_client: AzureOpenAIChatClient) -> tuple[ChatAgent, ChatAgent, ChatAgent, ChatAgent]:
    """Create and configure the coordinator and specialist agents.

    Returns:
        Tuple of (coordinator, technical_support, account_specialist, billing_agent)
    """
    coordinator = chat_client.create_agent(
        instructions=(
            "You are a customer support coordinator. Analyze the user's request and route to "
            "the appropriate specialist:\n"
            "- technical_support for technical issues, troubleshooting, repairs, hardware/software problems\n"
            "- account_specialist for account changes, profile updates, settings, login issues\n"
            "- billing_agent for payments, invoices, refunds, charges, billing questions\n"
            "\n"
            "When you receive a request, immediately call the matching handoff tool without explaining. "
            "Read the most recent user message to determine the correct specialist."
        ),
        name="coordinator",
    )

    technical_support = chat_client.create_agent(
        instructions=(
            "You provide technical support. Help users troubleshoot technical issues, "
            "arrange repairs, and answer technical questions. "
            "Gather information through conversation. "
            "If the user asks about billing, payments, invoices, or refunds, hand off to billing_agent. "
            "If the user asks about account settings or profile changes, hand off to account_specialist."
        ),
        name="technical_support",
    )

    account_specialist = chat_client.create_agent(
        instructions=(
            "You handle account management. Help with profile updates, account settings, "
            "and preferences. Gather information through conversation. "
            "If the user asks about technical issues or troubleshooting, hand off to technical_support. "
            "If the user asks about billing, payments, invoices, or refunds, hand off to billing_agent."
        ),
        name="account_specialist",
    )

    billing_agent = chat_client.create_agent(
        instructions=(
            "You handle billing only. Process payments, explain invoices, handle refunds. "
            "If the user asks about technical issues or troubleshooting, hand off to technical_support. "
            "If the user asks about account settings or profile changes, hand off to account_specialist."
        ),
        name="billing_agent",
    )

    return coordinator, technical_support, account_specialist, billing_agent


def handle_events(events: list[WorkflowEvent]) -> list[RequestInfoEvent]:
    """Process events and return pending input requests."""
    pending_requests: list[RequestInfoEvent] = []
    for event in events:
        if isinstance(event, RequestInfoEvent):
            pending_requests.append(event)
            request_data = cast(HandoffUserInputRequest, event.data)
            print(f"\n{'=' * 60}")
            print(f"AWAITING INPUT FROM: {request_data.awaiting_agent_id.upper()}")
            print(f"{'=' * 60}")
            for msg in request_data.conversation[-3:]:
                author = msg.author_name or msg.role.value
                prefix = ">>> " if author == request_data.awaiting_agent_id else "    "
                print(f"{prefix}[{author}]: {msg.text}")
        elif isinstance(event, WorkflowOutputEvent):
            print(f"\n{'=' * 60}")
            print("[WORKFLOW COMPLETE]")
            print(f"{'=' * 60}")
    return pending_requests


async def _drain(stream: AsyncIterable[WorkflowEvent]) -> list[WorkflowEvent]:
    """Drain an async iterable into a list."""
    events: list[WorkflowEvent] = []
    async for event in stream:
        events.append(event)
    return events


async def main() -> None:
    """Demonstrate return-to-previous routing in a handoff workflow."""
    chat_client = AzureOpenAIChatClient(credential=AzureCliCredential())
    coordinator, technical, account, billing = create_agents(chat_client)

    print("Handoff Workflow with Return-to-Previous Routing")
    print("=" * 60)
    print("\nThis interactive demo shows how user inputs route directly")
    print("to the specialist handling your request, avoiding unnecessary")
    print("coordinator re-evaluation on each turn.")
    print("\nSpecialists can hand off directly to other specialists when")
    print("your request changes topics (e.g., from technical to billing).")
    print("\nType 'exit' or 'quit' to end the conversation.\n")

    # Configure handoffs with return-to-previous enabled
    # Specialists can hand off directly to other specialists when topic changes
    workflow = (
        HandoffBuilder(
            name="return_to_previous_demo",
            participants=[coordinator, technical, account, billing],
        )
        .set_coordinator(coordinator)
        .add_handoff(coordinator, [technical, account, billing])  # Coordinator routes to all specialists
        .add_handoff(technical, [billing, account])  # Technical can route to billing or account
        .add_handoff(account, [technical, billing])  # Account can route to technical or billing
        .add_handoff(billing, [technical, account])  # Billing can route to technical or account
        .enable_return_to_previous(True)  # Enable the `return to previous handoff` feature
        .with_termination_condition(lambda conv: sum(1 for msg in conv if msg.role.value == "user") >= 10)
        .build()
    )

    # Get initial user request
    initial_request = input("You: ").strip()  # noqa: ASYNC250
    if not initial_request or initial_request.lower() in ["exit", "quit"]:
        print("Goodbye!")
        return

    # Start workflow with initial message
    events = await _drain(workflow.run_stream(initial_request))
    pending_requests = handle_events(events)

    # Interactive loop: keep prompting for user input
    while pending_requests:
        user_input = input("\nYou: ").strip()  # noqa: ASYNC250

        if not user_input or user_input.lower() in ["exit", "quit"]:
            print("\nEnding conversation. Goodbye!")
            break

        responses = {req.request_id: user_input for req in pending_requests}
        events = await _drain(workflow.send_responses_streaming(responses))
        pending_requests = handle_events(events)

    print("\n" + "=" * 60)
    print("Conversation ended.")

    """
    Sample Output:

    Handoff Workflow with Return-to-Previous Routing
    ============================================================

    This interactive demo shows how user inputs route directly
    to the specialist handling your request, avoiding unnecessary
    coordinator re-evaluation on each turn.

    Specialists can hand off directly to other specialists when
    your request changes topics (e.g., from technical to billing).

    Type 'exit' or 'quit' to end the conversation.

    You: I need help with my bill, I was charged twice by mistake.

    ============================================================
    AWAITING INPUT FROM: BILLING_AGENT
    ============================================================
        [user]: I need help with my bill, I was charged twice by mistake.
        [coordinator]: You will be connected to a billing agent who can assist you with the double charge on your bill.
    >>> [billing_agent]: I'm here to help with billing concerns! I'm sorry you were charged twice. Could you
        please provide the invoice number or your account email so I can look into this and begin processing a refund?

    You: Invoice 1234

    ============================================================
    AWAITING INPUT FROM: BILLING_AGENT
    ============================================================
    >>> [billing_agent]: I'm here to help with billing concerns! I'm sorry you were charged twice.
        Could you please provide the invoice number or your account email so I can look into this and begin
            processing a refund?
        [user]: Invoice 1234
    >>> [billing_agent]: Thank you for providing the invoice number (1234). I will review the details and work
        on processing a refund for the duplicate charge.

    Can you confirm which payment method you used for this bill (e.g., credit card, PayPal)?
        This helps ensure your refund is processed to the correct account.

    You: I used my credit card, which is on autopay.

    ============================================================
    AWAITING INPUT FROM: BILLING_AGENT
    ============================================================
    >>> [billing_agent]: Thank you for providing the invoice number (1234). I will review the details and work on
        processing a refund for the duplicate charge.

    Can you confirm which payment method you used for this bill (e.g., credit card, PayPal)? This helps ensure
        your refund is processed to the correct account.
        [user]: I used my credit card, which is on autopay.
    >>> [billing_agent]: Thank you for confirming your payment method. I will look into invoice 1234 and
        process a refund for the duplicate charge to your credit card.

    You will receive a notification once the refund is completed. If you have any further questions about your billing
        or need an update, please let me know!

    You: Actually I also can't turn on my modem. It reset and now won't turn on.

    ============================================================
    AWAITING INPUT FROM: TECHNICAL_SUPPORT
    ============================================================
        [user]: Actually I also can't turn on my modem. It reset and now won't turn on.
        [billing_agent]: I'm connecting you with technical support for assistance with your modem not turning on after
            the reset. They'll be able to help troubleshoot and resolve this issue.

    At the same time, technical support will also handle your refund request for the duplicate charge on invoice 1234
        to your credit card on autopay.

    You will receive updates from the appropriate teams shortly.
    >>> [technical_support]: Thanks for letting me know about your modem issue! To help you further, could you tell me:

    1. Is there any light showing on the modem at all, or is it completely off?
    2. Have you tried unplugging the modem from power and plugging it back in?
    3. Do you hear or feel anything (like a slight hum or vibration) when the modem is plugged in?

    Let me know, and I'll guide you through troubleshooting or arrange a repair if needed.

    You: exit

    Ending conversation. Goodbye!

    ============================================================
    Conversation ended.
    """


if __name__ == "__main__":
    asyncio.run(main())
