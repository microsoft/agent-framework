# Copyright (c) Microsoft. All rights reserved.
"""Side-by-side handoff orchestrations for Semantic Kernel and Agent Framework."""

import asyncio
import sys
from collections.abc import AsyncIterable, Iterator, Sequence
from typing import cast

from agent_framework import (
    ChatMessage,
    HandoffBuilder,
    HandoffUserInputRequest,
    RequestInfoEvent,
    WorkflowEvent,
    WorkflowOutputEvent,
    tool,
)
from agent_framework.azure import AzureOpenAIChatClient
from azure.identity import AzureCliCredential
from semantic_kernel.agents import Agent, ChatCompletionAgent, HandoffOrchestration, OrchestrationHandoffs
from semantic_kernel.agents.runtime import InProcessRuntime
from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion
from semantic_kernel.contents import (
    AuthorRole,
    ChatMessageContent,
    FunctionCallContent,
    FunctionResultContent,
    StreamingChatMessageContent,
)
from semantic_kernel.functions import kernel_function

if sys.version_info >= (3, 12):
    pass  # pragma: no cover
else:
    pass  # pragma: no cover


CUSTOMER_PROMPT = "I need help with order 12345. I want a replacement and need to know when it will arrive."
SCRIPTED_RESPONSES = [
    "The item arrived damaged. I'd like a replacement shipped to the same address.",
    "Great! Can you confirm the shipping cost won't be charged again?",
    "Thanks for confirming!",
]


######################################################################
# Semantic Kernel orchestration path
######################################################################


class OrderStatusPlugin:
    @kernel_function
    def check_order_status(self, order_id: str) -> str:
        return f"Order {order_id} is shipped and will arrive in 2-3 days."


class OrderRefundPlugin:
    @kernel_function
    def process_refund(self, order_id: str, reason: str) -> str:
        return f"Refund for order {order_id} has been processed successfully (reason: {reason})."


class OrderReturnPlugin:
    @kernel_function
    def process_return(self, order_id: str, reason: str) -> str:
        return f"Return for order {order_id} has been processed successfully (reason: {reason})."


def build_semantic_kernel_agents() -> tuple[list[Agent], OrchestrationHandoffs]:
    credential = AzureCliCredential()

    triage = ChatCompletionAgent(
        name="TriageAgent",
        description="Customer support triage specialist.",
        instructions="Greet the customer, collect intent, and hand off to the right specialist.",
        service=AzureChatCompletion(credential=credential),
    )
    refund = ChatCompletionAgent(
        name="RefundAgent",
        description="Handles refunds.",
        instructions="Process refund requests.",
        service=AzureChatCompletion(credential=credential),
        plugins=[OrderRefundPlugin()],
    )
    order_status = ChatCompletionAgent(
        name="OrderStatusAgent",
        description="Looks up order status.",
        instructions="Provide shipping timelines and tracking information.",
        service=AzureChatCompletion(credential=credential),
        plugins=[OrderStatusPlugin()],
    )
    order_return = ChatCompletionAgent(
        name="OrderReturnAgent",
        description="Handles returns.",
        instructions="Coordinate order returns.",
        service=AzureChatCompletion(credential=credential),
        plugins=[OrderReturnPlugin()],
    )

    handoffs = (
        OrchestrationHandoffs()
        .add_many(
            source_agent=triage.name,
            target_agents={
                refund.name: "Route refund-related requests here.",
                order_status.name: "Route shipping questions here.",
                order_return.name: "Route return-related requests here.",
            },
        )
        .add(refund.name, triage.name, "Return to triage for non-refund issues.")
        .add(order_status.name, triage.name, "Return to triage for non-status issues.")
        .add(order_return.name, triage.name, "Return to triage for non-return issues.")
    )

    return [triage, refund, order_status, order_return], handoffs


_sk_new_message = True


def _sk_streaming_callback(message: StreamingChatMessageContent, is_final: bool) -> None:
    """Display SK agent messages as they stream."""
    global _sk_new_message
    if _sk_new_message:
        print(f"{message.name}: ", end="", flush=True)
        _sk_new_message = False

    if message.content:
        print(message.content, end="", flush=True)

    for item in message.items:
        if isinstance(item, FunctionCallContent):
            print(f"[tool call: {item.name}({item.arguments})]", end="", flush=True)
        if isinstance(item, FunctionResultContent):
            print(f"[tool result: {item.result}]", end="", flush=True)

    if is_final:
        print()
        _sk_new_message = True


def _make_sk_human_responder(script: Iterator[str]) -> callable:
    def _responder() -> ChatMessageContent:
        try:
            user_text = next(script)
        except StopIteration:
            user_text = "Thanks, that's all."
        print(f"[User]: {user_text}")
        return ChatMessageContent(role=AuthorRole.USER, content=user_text)

    return _responder


async def run_semantic_kernel_example(initial_task: str, scripted_responses: Sequence[str]) -> str:
    agents, handoffs = build_semantic_kernel_agents()
    response_iter = iter(scripted_responses)

    orchestration = HandoffOrchestration(
        members=agents,
        handoffs=handoffs,
        streaming_agent_response_callback=_sk_streaming_callback,
        human_response_function=_make_sk_human_responder(response_iter),
    )

    runtime = InProcessRuntime()
    runtime.start()

    try:
        orchestration_result = await orchestration.invoke(task=initial_task, runtime=runtime)
        final_message = await orchestration_result.get(timeout=30)
        if isinstance(final_message, ChatMessageContent):
            return final_message.content or ""
        return str(final_message)
    finally:
        await runtime.stop_when_idle()


######################################################################
# Agent Framework orchestration path
######################################################################


def _create_af_agents(client: AzureOpenAIChatClient):
    triage = client.as_agent(
        name="triage_agent",
        instructions=(
            "You are a customer support triage agent. Route requests:\n"
            "- handoff_to_refund_agent for refunds\n"
            "- handoff_to_order_status_agent for shipping/timeline questions\n"
            "- handoff_to_order_return_agent for returns"
        ),
    )
    refund = client.as_agent(
        name="refund_agent",
        instructions=(
            "Handle refunds. Ask for order id and reason. If shipping info is needed, hand off to order_status_agent."
        ),
    )
    status = client.as_agent(
        name="order_status_agent",
        instructions=(
            "Provide order status, tracking, and timelines. If billing questions appear, hand off to refund_agent."
        ),
    )
    returns = client.as_agent(
        name="order_return_agent",
        instructions=(
            "Coordinate returns, confirm addresses, and summarize next steps. Hand off to triage_agent if unsure."
        ),
    )
    return triage, refund, status, returns


async def _drain_events(stream: AsyncIterable[WorkflowEvent]) -> list[WorkflowEvent]:
    return [event async for event in stream]


def _collect_handoff_requests(events: list[WorkflowEvent]) -> list[RequestInfoEvent]:
    requests: list[RequestInfoEvent] = []
    for event in events:
        if isinstance(event, RequestInfoEvent) and isinstance(event.data, HandoffUserInputRequest):
            requests.append(event)
    return requests


def _extract_final_conversation(events: list[WorkflowEvent]) -> list[ChatMessage]:
    for event in events:
        if isinstance(event, WorkflowOutputEvent):
            data = cast(list[ChatMessage], event.data)
            return data
    return []


async def run_agent_framework_example(initial_task: str, scripted_responses: Sequence[str]) -> str:
    client = AzureOpenAIChatClient(credential=AzureCliCredential())
    triage, refund, status, returns = _create_af_agents(client)

    workflow = (
        HandoffBuilder(name="sk_af_handoff_migration", participants=[triage, refund, status, returns])
        .set_coordinator(triage)
        .add_handoff(triage, [refund, status, returns])
        .add_handoff(refund, [status, triage])
        .add_handoff(status, [refund, triage])
        .add_handoff(returns, triage)
        .build()
    )

    events = await _drain_events(workflow.run_stream(initial_task))
    pending = _collect_handoff_requests(events)
    scripted_iter = iter(scripted_responses)

    final_events = events
    while pending:
        try:
            user_reply = next(scripted_iter)
        except StopIteration:
            user_reply = "Thanks, that's all."
        responses = {request.request_id: user_reply for request in pending}
        final_events = await _drain_events(workflow.send_responses_streaming(responses))
        pending = _collect_handoff_requests(final_events)

    conversation = _extract_final_conversation(final_events)
    if not conversation:
        return ""

    # Render final transcript succinctly.
    lines = []
    for message in conversation:
        text = message.text or ""
        if not text.strip():
            continue
        speaker = message.author_name or message.role.value
        lines.append(f"{speaker}: {text}")
    return "\n".join(lines)


######################################################################
# Console entry point
######################################################################


async def main() -> None:
    print("===== Agent Framework Handoff =====")
    af_transcript = await run_agent_framework_example(CUSTOMER_PROMPT, SCRIPTED_RESPONSES)
    print(af_transcript or "No output produced.")
    print()

    print("===== Semantic Kernel Handoff =====")
    sk_result = await run_semantic_kernel_example(CUSTOMER_PROMPT, SCRIPTED_RESPONSES)
    print(sk_result or "No output produced.")


if __name__ == "__main__":
    asyncio.run(main())
