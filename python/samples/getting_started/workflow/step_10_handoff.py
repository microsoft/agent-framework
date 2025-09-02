# Copyright (c) Microsoft. All rights reserved.

import asyncio
import logging

from agent_framework import ChatMessage, ChatRole
from agent_framework.azure import AzureChatClient
from agent_framework.workflow import (
    AgentDeltaEvent,
    AgentMessageEvent,
    CallbackEvent,
    CallbackMode,
    FinalResultEvent,
    HandoffBuilder,
    RequestInfoEvent,
    WorkflowCompletedEvent,
)
from azure.identity import AzureCliCredential

"""
Handoff workflow sample.

This sample demonstrates a simple triage-and-handoff pattern across multiple
specialized agents. The workflow starts with a Triage agent, which can transfer
control to a more specialized agent (Refund, Order, or Support) by emitting a
handoff directive in its first line:

    HANDOFF TO <agent_name>: <brief reason>

Only transfers configured via allow_transfers are accepted.
"""


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main() -> None:
    # For authentication, run `az login` or replace AzureCliCredential
    # with your preferred credential.
    chat_client = AzureChatClient(credential=AzureCliCredential())

    # Define agents (AIAgent instances). Names are used in allow_transfers.

    triage = chat_client.create_agent(
        name="triage",
        id="triage",
        instructions=(
            "You are the Triage agent for an e-commerce support team. "
            "Read the user's request and determine if it belongs to Refund (billing/returns), "
            "Order (shipping/status/changes), or Support (general questions).\n\n"
            "If you decide to transfer, start your FIRST line exactly with:\n"
            "HANDOFF TO <agent_name>: <brief reason>\n"
            "Then stop and do not provide a full answer. If no transfer is needed, answer directly."
        ),
    )

    refund = chat_client.create_agent(
        name="refund",
        id="refund",
        instructions=("You are the Refund specialist. Handle returns, refunds, and billing issues succinctly."),
    )

    order = chat_client.create_agent(
        name="order",
        id="order",
        instructions=("You are the Order specialist. Handle order status, changes, shipping, and delivery questions."),
    )

    support = chat_client.create_agent(
        name="support",
        id="support",
        instructions=("You are General Support. Handle product questions and anything not covered by Refund or Order."),
    )

    # Unified callback for streaming and final messages
    last_stream_agent_id: str | None = None
    stream_line_open: bool = False

    async def on_event(event: CallbackEvent) -> None:
        nonlocal last_stream_agent_id, stream_line_open
        if isinstance(event, AgentDeltaEvent):
            if last_stream_agent_id != event.agent_id or not stream_line_open:
                if stream_line_open:
                    print()
                print(f"[STREAM:{event.agent_id}] ", end="", flush=True)
                last_stream_agent_id = event.agent_id
                stream_line_open = True
            if event.text:
                print(event.text, end="", flush=True)
        elif isinstance(event, AgentMessageEvent):
            if stream_line_open:
                print(" (final)")
                stream_line_open = False
            if event.message is not None and (event.message.text or "").strip():
                print(f"\n[AGENT:{event.agent_id}]\n{event.message.text}\n{'-' * 26}")
        elif isinstance(event, FinalResultEvent):
            # Final result from orchestrator
            if event.message is not None:
                print("\n=== FINAL RESULT (callback) ===\n")
                print(event.message.text)

    workflow = (
        HandoffBuilder()
        .participants([triage, refund, order, support])
        .start_with("triage")
        .on_event(on_event, mode=CallbackMode.STREAMING)
        .enable_human_in_the_loop(
            executor_id="request_info",
            ask="if_question",
        )
        .allow_transfers({
            # Triage can handoff to specific specialists
            "triage": [
                ("refund", "Billing, returns, exchanges, or refund policy questions"),
                ("order", "Order status, shipping, tracking, modifications, or cancellations"),
                ("support", "General questions or anything not clearly refund/order related"),
            ],
            # Specialists can escalate to general support if needed
            "refund": [("support", "Not a refund/billing matter")],
            "order": [("support", "Not an order/shipping matter")],
        })
        .build()
    )

    # Try with a prompt that can trigger handoffs and possibly HIL
    user_request = "I ordered the wrong size yesterday. Can I change it to a medium and confirm delivery time?"

    print("Starting handoff workflow...\n")

    completion_event: WorkflowCompletedEvent | None = None
    request_info_event: RequestInfoEvent | None = None
    user_input: str = ""

    while True:
        if not request_info_event:
            response_stream = workflow.run_streaming(user_request)
        else:
            # Send human feedback back into the workflow
            response_stream = workflow.send_responses_streaming(
                {request_info_event.request_id: [ChatMessage(ChatRole.USER, text=user_input)]}
            )
            request_info_event = None

        async for event in response_stream:
            # The on_event callback already streams agent deltas and final messages
            if isinstance(event, WorkflowCompletedEvent):
                completion_event = event
            elif isinstance(event, RequestInfoEvent):
                request_info_event = event
                # Provide the prompt to the user for clarity
                try:
                    prompt = getattr(event.data, "prompt", None)
                    agent = getattr(event.data, "agent", None)
                    if prompt:
                        print(f"\n[HITL REQUEST from {agent or event.source_executor_id}]\n{prompt}\n")
                except Exception:
                    pass

        if request_info_event is not None:
            user_input = input("Human feedback required. Please provide your input: ")
        elif completion_event is not None:
            break

    print("\n=== COMPLETED ===\n")
    # completion_event is guaranteed non-None here due to the loop break condition
    assert completion_event is not None
    data = getattr(completion_event, "data", None)
    if isinstance(data, ChatMessage):
        print(data.text)
    else:
        print(str(data))


if __name__ == "__main__":
    asyncio.run(main())
