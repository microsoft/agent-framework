# Copyright (c) Microsoft. All rights reserved.

import asyncio
import logging
from typing import cast

from agent_framework import ChatAgent, HostedCodeInterpreterTool
from agent_framework.openai import OpenAIChatClient, OpenAIResponsesClient
from agent_framework_workflow import (
    MagenticAgentDeltaEvent,
    MagenticAgentMessageEvent,
    MagenticBuilder,
    MagenticCallbackEvent,
    MagenticCallbackMode,
    MagenticFinalResultEvent,
    MagenticOrchestratorMessageEvent,
    MagenticPlanReviewDecision,
    MagenticPlanReviewReply,
    MagenticPlanReviewRequest,
    RequestInfoEvent,
    WorkflowCompletedEvent,
)

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

"""
Sample: Magentic Orchestration + Human Plan Review

What it does:
- Builds a Magentic workflow with two agents and enables human plan review.
  A human approves or edits the plan via `RequestInfoEvent` before execution.

- researcher: ChatAgent backed by OpenAIChatClient (web/search-capable model)
- coder: ChatAgent backed by OpenAIAssistantsClient with the Hosted Code Interpreter tool

Key behaviors demonstrated:
- with_plan_review(): requests a PlanReviewRequest before coordination begins
- Event loop that waits for RequestInfoEvent[PlanReviewRequest], prints the plan, then
    replies with PlanReviewReply (here we auto-approve, but you can edit/collect input)
- Callbacks: on_agent_stream (incremental chunks), on_agent_response (final messages),
    on_result (final answer), and on_exception

Prerequisites:
- OpenAI credentials configured for `OpenAIChatClient` and `OpenAIResponsesClient`.
"""


async def main() -> None:
    researcher_agent = ChatAgent(
        name="ResearcherAgent",
        description="Specialist in research and information gathering",
        instructions=(
            "You are a Researcher. You find information without additional computation or quantitative analysis."
        ),
        # This agent requires the gpt-4o-search-preview model to perform web searches.
        # Feel free to explore with other agents that support web search, for example,
        # the `OpenAIResponseAgent` or `AzureAgentProtocol` with bing grounding.
        chat_client=OpenAIChatClient(ai_model_id="gpt-4o-search-preview"),
    )

    coder_agent = ChatAgent(
        name="CoderAgent",
        description="A helpful assistant that writes and executes code to process and analyze data.",
        instructions="You solve questions using code. Please provide detailed analysis and computation process.",
        chat_client=OpenAIResponsesClient(),
        tools=HostedCodeInterpreterTool(),
    )

    # Callbacks
    def on_exception(exception: Exception) -> None:
        print(f"Exception occurred: {exception}")
        logger.exception("Workflow exception", exc_info=exception)

    # Unified callback
    async def on_event(event: MagenticCallbackEvent) -> None:
        nonlocal last_stream_agent_id, stream_line_open
        if isinstance(event, MagenticOrchestratorMessageEvent):
            print(f"\n[ORCH:{event.kind}]\n\n{getattr(event.message, 'text', '')}\n{'-' * 26}")
        elif isinstance(event, MagenticAgentDeltaEvent):
            if last_stream_agent_id != event.agent_id or not stream_line_open:
                if stream_line_open:
                    print()
                print(f"\n[STREAM:{event.agent_id}]: ", end="", flush=True)
                last_stream_agent_id = event.agent_id
                stream_line_open = True
            print(event.text, end="", flush=True)
        elif isinstance(event, MagenticAgentMessageEvent):
            if stream_line_open:
                print(" (final)")
                stream_line_open = False
                print()
            msg = event.message
            if msg is not None:
                response_text = (msg.text or "").replace("\n", " ")
                print(f"\n[AGENT:{event.agent_id}] {msg.role.value}\n\n{response_text}\n{'-' * 26}")
        elif isinstance(event, MagenticFinalResultEvent):
            print("\n" + "=" * 50)
            print("FINAL RESULT:")
            print("=" * 50)
            if event.message is not None:
                print(event.message.text)
            print("=" * 50)

    print("\nBuilding Magentic Workflow...")

    last_stream_agent_id: str | None = None
    stream_line_open: bool = False

    workflow = (
        MagenticBuilder()
        .participants(researcher=researcher_agent, coder=coder_agent)
        .on_exception(on_exception)
        .on_event(on_event, mode=MagenticCallbackMode.STREAMING)
        .with_standard_manager(
            chat_client=OpenAIChatClient(),
            max_round_count=10,
            max_stall_count=3,
            max_reset_count=2,
        )
        .with_plan_review()
        .build()
    )

    task = (
        "I am preparing a report on the energy efficiency of different machine learning model architectures. "
        "Compare the estimated training and inference energy consumption of ResNet-50, BERT-base, and GPT-2 "
        "on standard datasets (e.g., ImageNet for ResNet, GLUE for BERT, WebText for GPT-2). "
        "Then, estimate the CO2 emissions associated with each, assuming training on an Azure Standard_NC6s_v3 "
        "VM for 24 hours. Provide tables for clarity, and recommend the most energy-efficient model "
        "per task type (image classification, text classification, and text generation)."
    )

    print(f"\nTask: {task}")
    print("\nStarting workflow execution...")

    try:
        completion_event: WorkflowCompletedEvent | None = None
        pending_request: RequestInfoEvent | None = None

        while True:
            # Phase 1: run until either completion or a HIL request
            if pending_request is None:
                async for event in workflow.run_stream(task):
                    print(f"Event: {event}")

                    if isinstance(event, WorkflowCompletedEvent):
                        completion_event = event

                    if isinstance(event, RequestInfoEvent) and event.request_type is MagenticPlanReviewRequest:
                        pending_request = event
                        review_req = cast(MagenticPlanReviewRequest, event.data)
                        if review_req.plan_text:
                            print(f"\n=== PLAN REVIEW REQUEST ===\n{review_req.plan_text}\n")

            # Break if completed
            if completion_event is not None:
                data = getattr(completion_event, "data", None)
                preview = getattr(data, "text", None) or (str(data) if data is not None else "")
                print(f"Workflow completed with result:\n\n{preview}")

            # Phase 2: respond to the pending plan review (HIL) request
            if pending_request is not None:
                # For demo purposes we approve as-is. Replace this with UI input
                # to collect a human decision/comments/edited plan.
                reply = MagenticPlanReviewReply(decision=MagenticPlanReviewDecision.APPROVE)

                async for event in workflow.send_responses_streaming({pending_request.request_id: reply}):
                    print(f"Event: {event}")

                    if isinstance(event, WorkflowCompletedEvent):
                        completion_event = event

                    if isinstance(event, RequestInfoEvent) and event.request_type is MagenticPlanReviewRequest:
                        # Another review cycle requested; keep pending
                        pending_request = event
                        review_req = cast(MagenticPlanReviewRequest, event.data)
                        if review_req.plan_text:
                            print(f"\n=== PLAN REVIEW REQUEST ===\n{review_req.plan_text}\n")
                    else:
                        # Clear pending if no immediate new request
                        pending_request = None

    except Exception as e:
        print(f"Workflow execution failed: {e}")
        on_exception(e)


if __name__ == "__main__":
    asyncio.run(main())
