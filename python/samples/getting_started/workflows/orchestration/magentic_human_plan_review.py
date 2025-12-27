# Copyright (c) Microsoft. All rights reserved.

import asyncio
import json
from typing import cast

from agent_framework import (
    AgentRunUpdateEvent,
    ChatAgent,
    ChatMessage,
    MagenticBuilder,
    MagenticPlanReviewRequest,
    RequestInfoEvent,
    WorkflowOutputEvent,
)
from agent_framework.openai import OpenAIChatClient

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
        .participants([researcher_agent, analyst_agent])
        .with_standard_manager(
            agent=manager_agent,
            max_round_count=10,
            max_stall_count=1,  # Stall detection after 1 round without progress
            max_reset_count=2,
        )
        .with_plan_review()  # Request human input for plan review
        .build()
    )

    task = "Research sustainable aviation fuel technology and summarize the findings."

    print(f"\nTask: {task}")
    print("\nStarting workflow execution...")
    print("=" * 60)

    pending_request: RequestInfoEvent | None = None
    pending_responses: dict[str, object] | None = None
    output_event: WorkflowOutputEvent | None = None

    while not output_event:
        if pending_responses is not None:
            stream = workflow.send_responses_streaming(pending_responses)
        else:
            stream = workflow.run_stream(task)

        last_message_id: str | None = None
        async for event in stream:
            if isinstance(event, AgentRunUpdateEvent):
                message_id = event.data.message_id
                if message_id != last_message_id:
                    if last_message_id is not None:
                        print("\n")
                    print(f"- {event.executor_id}:", end=" ", flush=True)
                    last_message_id = message_id
                print(event.data, end="", flush=True)

            elif isinstance(event, RequestInfoEvent) and event.request_type is MagenticPlanReviewRequest:
                pending_request = event

            elif isinstance(event, WorkflowOutputEvent):
                output_event = event

        pending_responses = None

        # Handle plan review request if any
        if pending_request is not None:
            event_data = cast(MagenticPlanReviewRequest, pending_request.data)

            print("\n\n[Magentic Plan Review Request]")
            if event_data.current_progress is not None:
                print("Current Progress Ledger:")
                print(json.dumps(event_data.current_progress.to_dict(), indent=2))
                print()
            print(f"Proposed Plan:\n{event_data.plan.text}\n")
            print("Please provide your feedback (press Enter to approve):")

            reply = await asyncio.get_event_loop().run_in_executor(None, input, "> ")
            if reply.strip() == "":
                print("Plan approved.\n")
                pending_responses = {pending_request.request_id: event_data.approve()}
            else:
                print("Plan revised by human.\n")
                pending_responses = {pending_request.request_id: event_data.revise(reply)}
            pending_request = None

    print("\n" + "=" * 60)
    print("WORKFLOW COMPLETED")
    print("=" * 60)
    print("Final Output:")
    # The output of the Magentic workflow is a list of ChatMessages with only one final message
    # generated by the orchestrator.
    output_messages = cast(list[ChatMessage], output_event.data)
    if output_messages:
        output = output_messages[-1].text
        print(output)


if __name__ == "__main__":
    asyncio.run(main())
