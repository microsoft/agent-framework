# Copyright (c) Microsoft. All rights reserved.

import asyncio
import logging

from agent_framework import AgentProtocol, ChatMessage
from agent_framework.azure import AzureChatClient
from agent_framework_workflow import (
    AgentDeltaEvent,
    AgentMessageEvent,
    CallbackEvent,
    CallbackMode,
    FinalResultEvent,
    HandoffBuilder,
    RequestInfoEvent,
    Workflow,
    WorkflowCompletedEvent,
)
from azure.identity import AzureCliCredential

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

"""
Sample: Structured Handoff with Human-in-the-Loop (HITL)

Purpose:
This sample demonstrates a structured multi-agent handoff workflow that integrates
human-in-the-loop escalation. Agents handle specialized tasks (triage, refund, order,
support, delivery). When information is missing, an agent can emit a structured
`RequestInfoEvent` to request human input. The workflow pauses until the user provides
the required information, then continues execution.

Pipeline (typical sequence):
1. triage: Classifies the incoming request and routes it to the appropriate specialist.
   Possible destinations: refund, order, support.
2. refund: Handles billing, returns, and refund-related issues.
3. order: Handles shipping, order changes, and modifications. If missing details such as
   order number, it triggers HITL to collect the missing information before proceeding.
   Once the order change is complete, order hands off to delivery.
4. delivery: Provides delivery window estimates after modifications are made.
   If information is missing, it may also trigger HITL to collect it.
5. support: Handles general inquiries not tied to refund or order.

What you learn:
- How to create multiple agents with domain-specific roles and structured instructions.
- How to configure structured handoff routing rules with `HandoffBuilder`.
- How to enable human-in-the-loop escalation with `.enable_human_in_the_loop(...)`.
- How to capture and respond to `RequestInfoEvent` prompts to simulate human input.
- How to handle event callbacks for:
  - Incremental agent streaming (`AgentDeltaEvent`)
  - Final agent messages (`AgentMessageEvent`)
  - Final workflow results (`FinalResultEvent`)
  - Human escalation prompts (`RequestInfoEvent`)

Key behaviors demonstrated:
- Agents produce structured decisions (`handoff`, `respond`, `complete`) instead of
  free-form replies.
- The order and delivery agents can explicitly request human input if critical data
  is missing.
- The workflow pauses at a `RequestInfoEvent`, prints the prompt to the console, and
  waits for human input before resuming.
- Human responses are echoed back into the workflow via
  `workflow.send_responses_streaming(...)`.

Prerequisites:
- Azure authentication: run `az login` for `AzureCliCredential`.
- Proper environment variables for your Azure OpenAI deployment.
- Installed `agent_framework` and `agent_framework_workflow` packages.
"""


async def main() -> None:
    # Authenticate with Azure (using Azure CLI credentials by default).
    # Replace with other credential types if needed.
    chat_client = AzureChatClient(credential=AzureCliCredential())

    # Define agents for each specialized role. All are created as `AgentProtocol`.

    # TRIAGE agent:
    # Decides whether the request belongs to refund, order, or support.
    # Does not itself resolve the request except for trivial support cases.
    triage: AgentProtocol = chat_client.create_agent(
        name="triage",
        id="triage",
        instructions=(
            "You are the Triage agent for an e-commerce support team. "
            "Read the user's request and decide whether Refund, Order, or Support should handle it. "
            "Do not provide the final resolution yourself unless it is clearly general support."
        ),
    )

    # REFUND agent:
    # Specializes in billing, returns, and refunds.
    refund: AgentProtocol = chat_client.create_agent(
        name="refund",
        id="refund",
        instructions=(
            "You are the Refund specialist. Handle returns, refunds, and billing issues succinctly. "
            "If this is not a refund matter, indicate that another specialist is more appropriate."
        ),
    )

    # ORDER agent:
    # Handles shipping, order changes, and cancellations.
    # If missing information (like order number), it uses HITL escalation by emitting
    # `RequestInfoEvent` (action='respond') to prompt the user for details.
    order: AgentProtocol = chat_client.create_agent(
        name="order",
        id="order",
        instructions=(
            "You are the Order specialist. Handle order status, changes, shipping, and delivery requests that "
            "require modifying an order.\n"
            "When missing information (like order number), ask exactly ONE short question at a time using "
            "action='respond' with an assistant_message that is a single question.\n"
            "After the user provides the order number and requested change (e.g., new size), delegate delivery "
            "time estimation to the Delivery specialist.\n"
            "At that point, DO NOT give the delivery estimate yourself. Emit a structured decision with "
            "action='handoff' and target='delivery' including a brief reason."
        ),
    )

    # SUPPORT agent:
    # Handles general product or service questions.
    support: AgentProtocol = chat_client.create_agent(
        name="support",
        id="support",
        instructions=(
            "You are General Support. Handle product questions and anything not covered by Refund or Order. "
            "If a specialist is more appropriate, indicate that handoff is preferred."
        ),
    )

    # DELIVERY agent:
    # Provides delivery windows after order changes.
    # If details are missing, it may request clarification via HITL.
    delivery: AgentProtocol = chat_client.create_agent(
        name="delivery",
        id="delivery",
        instructions=(
            "You are the Delivery specialist. After a handoff from Order (with order number + requested changes), "
            "provide an estimated delivery window. Keep it concise (e.g., 'Your updated order will arrive between "
            "Sept 14-16'). If sufficient info is present, finalize with action='complete' and a one-line summary "
            "including the delivery window. If something is missing, ask one clarifying question using "
            "action='respond'."
        ),
    )

    # Unified callback for handling incremental streaming, agent messages, and final results.
    last_stream_agent_id: str | None = None
    stream_line_open: bool = False

    async def on_event(event: CallbackEvent) -> None:
        nonlocal last_stream_agent_id, stream_line_open
        if isinstance(event, AgentDeltaEvent):
            # Handle incremental text from streaming output.
            if last_stream_agent_id != event.agent_id or not stream_line_open:
                if stream_line_open:
                    print()
                print(f"[STREAM:{event.agent_id}] ", end="", flush=True)
                last_stream_agent_id = event.agent_id
                stream_line_open = True
            if event.text:
                print(event.text, end="", flush=True)
        elif isinstance(event, AgentMessageEvent):
            # Handle an agent's final completed message.
            if stream_line_open:
                print(" (final)")
                stream_line_open = False
            if event.message is not None and (event.message.text or "").strip():
                print(f"\n[AGENT:{event.agent_id}]\n{event.message.text}\n{'-' * 26}")
        elif isinstance(event, FinalResultEvent):
            # Handle final workflow result callback.
            if event.message is not None:
                print("\n=== FINAL RESULT (callback) ===\n")
                print(event.message.text)

    # Build the workflow using HandoffBuilder.
    # Configure participants, routing rules, structured handoffs, and HITL escalation.
    workflow: Workflow = (
        HandoffBuilder()
        .participants([triage, refund, order, support, delivery])  # all agents registered
        .start_with("triage")  # workflow entry point
        .structured_handoff(enabled=True)  # enable JSON-based routing
        .on_event(on_event, mode=CallbackMode.STREAMING)  # callback for all events
        .enable_human_in_the_loop(
            executor_id="request_info",  # special executor for human feedback
            ask="if_question",  # legacy mode still works; structured mode uses action="ask_human"
        )
        .allow_transfers({
            "triage": [
                ("refund", "Billing, returns, exchanges, or refund policy questions"),
                ("order", "Order status, shipping, tracking, modifications, or cancellations"),
                ("support", "General questions or anything not clearly refund/order related"),
            ],
            "refund": [("support", "Not a refund/billing matter")],
            "order": [
                ("delivery", "Provide delivery window after order modifications"),
                ("support", "General question unrelated to order fulfillment"),
            ],
            "delivery": [("support", "General support follow-up after delivery details")],
        })
        .build()
    )

    # Example request:
    # This prompt is expected to flow triage -> order -> HITL for missing details,
    # then order -> delivery -> completion.
    user_request = "I ordered the wrong size yesterday. Please change it to a medium and confirm delivery time."

    print("Starting handoff workflow with HITL enabled...\n")

    # Variables to manage workflow completion and human prompts.
    completion_event: WorkflowCompletedEvent | None = None
    request_info_event: RequestInfoEvent | None = None
    user_input: str = ""

    # Main event loop:
    # 1. Run the workflow until either completion or HITL request.
    # 2. If HITL is requested, capture the prompt and wait for user input.
    # 3. Resume workflow with the human input.
    while True:
        if not request_info_event:
            response_stream = workflow.run_stream(user_request)
        else:
            # Resume workflow by sending human input back in response to HITL request.
            response_stream = workflow.send_responses_streaming({request_info_event.request_id: user_input})
            request_info_event = None

        async for event in response_stream:
            if isinstance(event, WorkflowCompletedEvent):
                completion_event = event
            elif isinstance(event, RequestInfoEvent):
                request_info_event = event
                # Print the HITL request prompt to the console.
                try:
                    prompt = getattr(event.data, "prompt", None)
                    agent = getattr(event.data, "agent", None)
                    if prompt:
                        print(f"\n[HITL REQUEST from {agent or event.source_executor_id}]\n{prompt}\n")
                except Exception:
                    pass

        if request_info_event is not None:
            # Wait for human feedback.
            user_input = input("Human feedback required. Please provide your input: ")
            if user_input.strip():
                print(f"\n[HITL INPUT ECHO]\n{user_input.strip()}\n")
            # Example responses:
            # 1st HITL: enter an order number, e.g., "1939393828"
            # 2nd HITL: confirm delivery, e.g., "Yes, please proceed"
        elif completion_event is not None:
            break

    # Print final workflow completion message.
    print("\n=== COMPLETED ===\n")
    assert completion_event is not None
    data = getattr(completion_event, "data", None)
    if isinstance(data, ChatMessage):
        print(data.text)
    else:
        print(str(data))


if __name__ == "__main__":
    asyncio.run(main())
