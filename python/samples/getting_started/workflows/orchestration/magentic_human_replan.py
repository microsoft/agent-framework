# Copyright (c) Microsoft. All rights reserved.

import asyncio
import logging
from typing import cast

from agent_framework import (
    MAGENTIC_EVENT_TYPE_AGENT_DELTA,
    MAGENTIC_EVENT_TYPE_ORCHESTRATOR,
    AgentRunUpdateEvent,
    ChatAgent,
    ChatMessage,
    MagenticBuilder,
    MagenticHumanInterventionDecision,
    MagenticHumanInterventionKind,
    MagenticHumanInterventionReply,
    MagenticHumanInterventionRequest,
    RequestInfoEvent,
    WorkflowOutputEvent,
)
from agent_framework.openai import OpenAIChatClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

"""
Sample: Magentic Orchestration with Human Stall Intervention

This sample demonstrates how humans can intervene when a Magentic workflow stalls.
When agents stop making progress, the workflow requests human input instead of
automatically replanning.

Key concepts:
- with_human_input_on_stall(): Enables human intervention when workflow detects stalls
- MagenticHumanInterventionKind.STALL: The request kind for stall interventions
- Human can choose to: continue, trigger replan, or provide guidance

Stall intervention options:
- CONTINUE: Reset stall counter and continue with current plan
- REPLAN: Trigger automatic replanning by the manager
- GUIDANCE: Provide text guidance to help agents get back on track

Prerequisites:
- OpenAI credentials configured for `OpenAIChatClient`.

NOTE: it is sometimes difficult to get the agents to actually stall depending on the task.
"""


async def main() -> None:
    researcher_agent = ChatAgent(
        name="ResearcherAgent",
        description="Specialist in research and information gathering",
        instructions="You are a Researcher. You find information and gather facts.",
        chat_client=OpenAIChatClient(model_id="gpt-4o"),
    )

    analyst_agent = ChatAgent(
        name="AnalystAgent",
        description="Data analyst who processes and summarizes research findings",
        instructions="You are an Analyst. You analyze findings and create summaries.",
        chat_client=OpenAIChatClient(model_id="gpt-4o"),
    )

    manager_agent = ChatAgent(
        name="MagenticManager",
        description="Orchestrator that coordinates the workflow",
        instructions="You coordinate a team to complete tasks efficiently.",
        chat_client=OpenAIChatClient(model_id="gpt-4o"),
    )

    print("\nBuilding Magentic Workflow with Human Stall Intervention...")

    workflow = (
        MagenticBuilder()
        .participants(researcher=researcher_agent, analyst=analyst_agent)
        .with_standard_manager(
            agent=manager_agent,
            max_round_count=10,
            max_stall_count=1,  # Stall detection after 1 round without progress
            max_reset_count=2,
        )
        .with_human_input_on_stall()  # Request human input when stalled (instead of auto-replan)
        .build()
    )

    task = "Research sustainable aviation fuel technology and summarize the findings."

    print(f"\nTask: {task}")
    print("\nStarting workflow execution...")
    print("=" * 60)

    try:
        pending_request: RequestInfoEvent | None = None
        pending_responses: dict[str, object] | None = None
        completed = False
        workflow_output: str | None = None

        last_stream_agent_id: str | None = None
        stream_line_open: bool = False

        while not completed:
            if pending_responses is not None:
                stream = workflow.send_responses_streaming(pending_responses)
            else:
                stream = workflow.run_stream(task)

            async for event in stream:
                if isinstance(event, AgentRunUpdateEvent):
                    props = event.data.additional_properties if event.data else None
                    event_type = props.get("magentic_event_type") if props else None

                    if event_type == MAGENTIC_EVENT_TYPE_ORCHESTRATOR:
                        kind = props.get("orchestrator_message_kind", "") if props else ""
                        text = event.data.text if event.data else ""
                        if stream_line_open:
                            print()
                            stream_line_open = False
                        print(f"\n[ORCHESTRATOR: {kind}]\n{text}\n{'-' * 40}")
                    elif event_type == MAGENTIC_EVENT_TYPE_AGENT_DELTA:
                        agent_id = props.get("agent_id", "unknown") if props else "unknown"
                        if last_stream_agent_id != agent_id or not stream_line_open:
                            if stream_line_open:
                                print()
                            print(f"\n[{agent_id}]: ", end="", flush=True)
                            last_stream_agent_id = agent_id
                            stream_line_open = True
                        if event.data and event.data.text:
                            print(event.data.text, end="", flush=True)

                elif isinstance(event, RequestInfoEvent) and event.request_type is MagenticHumanInterventionRequest:
                    if stream_line_open:
                        print()
                        stream_line_open = False
                    pending_request = event
                    req = cast(MagenticHumanInterventionRequest, event.data)

                    if req.kind == MagenticHumanInterventionKind.STALL:
                        print("\n" + "=" * 60)
                        print("STALL INTERVENTION REQUESTED")
                        print("=" * 60)
                        print(f"\nWorkflow appears stalled after {req.stall_count} rounds")
                        print(f"Reason: {req.stall_reason}")
                        if req.last_agent:
                            print(f"Last active agent: {req.last_agent}")
                        if req.plan_text:
                            print(f"\nCurrent plan:\n{req.plan_text}")
                        print()

                elif isinstance(event, WorkflowOutputEvent):
                    if stream_line_open:
                        print()
                        stream_line_open = False
                    workflow_output = event.data if event.data else None
                    completed = True

            if stream_line_open:
                print()
                stream_line_open = False
            pending_responses = None

            # Handle stall intervention request
            if pending_request is not None:
                req = cast(MagenticHumanInterventionRequest, pending_request.data)
                reply: MagenticHumanInterventionReply | None = None

                if req.kind == MagenticHumanInterventionKind.STALL:
                    print("Stall intervention options:")
                    print("1. continue - Continue with current plan (reset stall counter)")
                    print("2. replan - Trigger automatic replanning")
                    print("3. guidance - Provide guidance to help agents")
                    print("4. exit - Exit the workflow")

                    while True:
                        choice = input("Enter your choice (1-4): ").strip().lower()  # noqa: ASYNC250
                        if choice in ["continue", "1"]:
                            reply = MagenticHumanInterventionReply(decision=MagenticHumanInterventionDecision.CONTINUE)
                            break
                        if choice in ["replan", "2"]:
                            reply = MagenticHumanInterventionReply(decision=MagenticHumanInterventionDecision.REPLAN)
                            break
                        if choice in ["guidance", "3"]:
                            guidance = input("Enter your guidance: ").strip()  # noqa: ASYNC250
                            reply = MagenticHumanInterventionReply(
                                decision=MagenticHumanInterventionDecision.GUIDANCE,
                                comments=guidance if guidance else None,
                            )
                            break
                        if choice in ["exit", "4"]:
                            print("Exiting workflow...")
                            return
                        print("Invalid choice. Please enter a number 1-4.")

                if reply is not None:
                    pending_responses = {pending_request.request_id: reply}
                pending_request = None

        print("\n" + "=" * 60)
        print("WORKFLOW COMPLETED")
        print("=" * 60)
        if workflow_output:
            messages = cast(list[ChatMessage], workflow_output)
            if messages:
                final_msg = messages[-1]
                print(f"\nFinal Result:\n{final_msg.text}")

    except Exception as e:
        print(f"Workflow execution failed: {e}")
        logger.exception("Workflow exception", exc_info=e)


if __name__ == "__main__":
    asyncio.run(main())
