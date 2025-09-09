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
    Workflow,
    WorkflowCompletedEvent,
)
from azure.identity import AzureCliCredential

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

"""
Sample: Structured Multi-hop Handoff Workflow (No Human Escalation)

Purpose:
This sample demonstrates how to build a multi-hop workflow in which a user request
flows through multiple specialized agents. Routing decisions are made automatically
using structured JSON outputs from each agent. The workflow is purely machine-driven
(no human-in-the-loop escalation) and shows how to configure agent roles, handoff
rules, and structured routing.

Pipeline (typical sequence):
1. intake: Reads the user request and triages whether research, solution planning, or
   immediate answering is appropriate.
2. research: Collects factual information or contextual knowledge to support solution design.
3. solution: Synthesizes research into a step-by-step plan or implementation approach.
4. answer: Crafts the final user-facing response and terminates the workflow.

What you learn:
- How to define multiple `AgentProtocol` agents with distinct responsibilities.
- How to configure structured handoff routing decisions between agents using
  `HandoffBuilder`.
- How to use `.allow_transfers(...)` to explicitly define which agent may hand off to
  which, and under what rationale.
- How to register a unified callback (`on_event`) to handle incremental streaming,
  agent messages, and final results.
- How to observe the entire routing process by printing the structured JSON decisions.

Key behaviors demonstrated:
- Agents never reply directly to the user except the final `answer` stage.
- Each agent emits structured handoff decisions, not free-form responses.
- Routing is fully automatic; no human intervention occurs.
- The system prints incremental token streams, final agent outputs, and the ultimate
  workflow completion message.

Prerequisites:
- Azure authentication: run `az login` to enable use of `AzureCliCredential`.
- Proper environment configuration for Azure OpenAI deployment.
- `agent_framework` and `agent_framework_workflow` packages installed.
"""


async def main() -> None:
    # Create the Azure-backed chat client.
    # This client will be used to instantiate multiple specialized agents.
    chat_client = AzureChatClient(credential=AzureCliCredential())

    # INTAKE agent:
    # First entry point of the workflow. Its role is to classify the request:
    # - If factual research is needed, route to "research".
    # - If multi-step reasoning is needed, route to "solution".
    # - If the request is trivial and answerable directly, route to "answer".
    # The intake agent never answers the user directly.
    intake: AgentProtocol = chat_client.create_agent(
        name="intake",
        id="intake",
        instructions=(
            "You are the Intake agent. Read the user request and decide if research or solution design is needed.\n"
            "If factual lookup / deeper context is needed, handoff to 'research'.\n"
            "If the task is simple and answerable immediately, handoff directly to 'answer'.\n"
            "Else if implementation planning is required (multi-step reasoning), handoff to 'solution'.\n"
            "Do NOT answer the user directly. Always emit a structured decision."
        ),
    )

    # RESEARCH agent:
    # Performs information gathering and contextualization.
    # Produces a structured summary of facts or clarifications needed for planning.
    # Typically hands off to "solution" after completing its task.
    research: AgentProtocol = chat_client.create_agent(
        name="research",
        id="research",
        instructions=(
            "You are the Research specialist. Given the user's request + prior context, summarize key factual points\n"
            "needed for a solid solution design (short bullet style internally). After compiling facts,\n"
            "handoff to 'solution'. Avoid handing off to 'answer' unless the solution is trivially obvious.\n"
            "Do NOT respond to the user directly. Always emit a structured decision."
        ),
    )

    # SOLUTION agent:
    # Transforms research and context into a concise internal plan.
    # If the plan is ready, handoff to "answer".
    # If missing facts, loop back to "research".
    # It never directly produces the final user-facing message.
    solution: AgentProtocol = chat_client.create_agent(
        name="solution",
        id="solution",
        instructions=(
            "You are the Solution Design agent. Transform the research/context into a concise plan (internally).\n"
            "If the plan is complete, handoff to 'answer'. If more facts are needed, handoff back to 'research'.\n"
            "Never answer the user directly. Always emit a structured decision."
        ),
    )

    # ANSWER agent:
    # The final stage that produces the user-facing message.
    # This is the only agent allowed to reply directly to the user.
    # If necessary details are missing, it may hand back to "solution".
    answer: AgentProtocol = chat_client.create_agent(
        name="answer",
        id="answer",
        instructions=(
            "You are the final Answer agent. Based on prior context (including plan + facts), craft a clear, helpful\n"
            "user-facing answer. When complete, use action='complete' with a one-line summary AND set\n"
            "to the final response text. If critical plan details are missing, handoff to 'solution'."
        ),
    )

    # Variables for tracking streaming across agents.
    last_stream_agent_id: str | None = None
    stream_open = False

    # Unified callback for handling events from all agents.
    # This function prints:
    # - Incremental streaming text as it arrives
    # - Final agent messages (per stage)
    # - The final workflow result
    async def on_event(event: CallbackEvent) -> None:  # noqa: D401
        nonlocal last_stream_agent_id, stream_open
        if isinstance(event, AgentDeltaEvent):
            # Handle incremental token-level streaming from an agent.
            if last_stream_agent_id != event.agent_id or not stream_open:
                if stream_open:
                    print()
                print(f"[STREAM:{event.agent_id}] ", end="", flush=True)
                last_stream_agent_id = event.agent_id
                stream_open = True
            if event.text:
                print(event.text, end="", flush=True)
        elif isinstance(event, AgentMessageEvent):
            # Handle completion of an agent's turn.
            if stream_open:
                print(" (final)")
                stream_open = False
            if event.message and (event.message.text or "").strip():
                print(f"\n[AGENT:{event.agent_id}]\n{event.message.text}\n{'-' * 26}")
        elif isinstance(event, FinalResultEvent):
            # Handle final aggregated workflow result.
            if event.message:
                print("\n=== FINAL RESULT (callback) ===\n")
                print(event.message.text)

    # Build the workflow using HandoffBuilder.
    # Participants: intake -> research -> solution -> answer
    # Routing is defined explicitly via allow_transfers.
    workflow: Workflow = (
        HandoffBuilder()
        .participants([intake, research, solution, answer])  # register all agents
        .start_with("intake")  # entry point agent
        .structured_handoff(enabled=True)  # enable structured JSON routing
        .on_event(on_event, mode=CallbackMode.STREAMING)  # register unified callback
        .allow_transfers({
            "intake": [
                ("research", "Factual lookup or domain detail required"),
                ("solution", "Complex multi-step reasoning required"),
                ("answer", "Trivial or immediately solvable"),
            ],
            "research": [
                ("solution", "Sufficient facts compiled for planning"),
                ("answer", "Direct answer now obvious"),
            ],
            "solution": [
                ("answer", "Plan complete; craft final response"),
                ("research", "Missing key facts; need more data"),
            ],
            # Answer is terminal, so no outbound transfers defined.
        })
        .build()
    )

    # Example user request that will be routed through the workflow.
    user_request = (
        "I need a short step-by-step plan to reduce cloud infrastructure costs for a SaaS product while maintaining "
        "reliability. Include quick wins and medium-term optimizations."
    )

    print("Starting multi-hop handoff workflow (no HITL)...\n")

    # Run the workflow with streaming enabled.
    completion: WorkflowCompletedEvent | None = None
    async for event in workflow.run_stream(user_request):
        if isinstance(event, WorkflowCompletedEvent):
            completion = event

    # Print the final result at the end of execution.
    print("\n=== COMPLETED ===\n")
    if completion and isinstance(completion.data, ChatMessage):  # type: ignore[attr-defined]
        print(completion.data.text)  # type: ignore[union-attr]
    else:
        print(str(getattr(completion, "data", "<no data>")))


if __name__ == "__main__":
    asyncio.run(main())
