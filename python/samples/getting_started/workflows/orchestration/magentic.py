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
    HostedCodeInterpreterTool,
    MagenticBuilder,
    WorkflowOutputEvent,
)
from agent_framework.openai import OpenAIChatClient, OpenAIResponsesClient

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

"""
Sample: Magentic Orchestration (multi-agent)

What it does:
- Orchestrates multiple agents using `MagenticBuilder` with streaming callbacks.

- ResearcherAgent (ChatAgent backed by an OpenAI chat client) for
    finding information.
- CoderAgent (ChatAgent backed by OpenAI Assistants with the hosted
    code interpreter tool) for analysis and computation.

The workflow is configured with:
- A Standard Magentic manager (uses a chat client for planning and progress).
- Callbacks for final results, per-message agent responses, and streaming
    token updates.

When run, the script builds the workflow, submits a task about estimating the
energy efficiency and CO2 emissions of several ML models, streams intermediate
events, and prints the final answer. The workflow completes when idle.

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
        chat_client=OpenAIChatClient(model_id="gpt-4o-search-preview"),
    )

    coder_agent = ChatAgent(
        name="CoderAgent",
        description="A helpful assistant that writes and executes code to process and analyze data.",
        instructions="You solve questions using code. Please provide detailed analysis and computation process.",
        chat_client=OpenAIResponsesClient(),
        tools=HostedCodeInterpreterTool(),
    )

    # Create a manager agent for orchestration
    manager_agent = ChatAgent(
        name="MagenticManager",
        description="Orchestrator that coordinates the research and coding workflow",
        instructions="You coordinate a team to complete complex tasks efficiently.",
        chat_client=OpenAIChatClient(),
    )

    print("\nBuilding Magentic Workflow...")

    # State used by on_agent_stream callback
    last_stream_agent_id: str | None = None
    stream_line_open: bool = False

    workflow = (
        MagenticBuilder()
        .participants(researcher=researcher_agent, coder=coder_agent)
        .with_standard_manager(
            agent=manager_agent,
            max_round_count=10,
            max_stall_count=3,
            max_reset_count=2,
        )
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
        output: str | None = None
        async for event in workflow.run_stream(task):
            if isinstance(event, AgentRunUpdateEvent):
                props = event.data.additional_properties if event.data else None
                event_type = props.get("magentic_event_type") if props else None

                if event_type == MAGENTIC_EVENT_TYPE_ORCHESTRATOR:
                    kind = props.get("orchestrator_message_kind", "") if props else ""
                    text = event.data.text if event.data else ""
                    print(f"\n[ORCH:{kind}]\n\n{text}\n{'-' * 26}")
                elif event_type == MAGENTIC_EVENT_TYPE_AGENT_DELTA:
                    agent_id = props.get("agent_id", event.executor_id) if props else event.executor_id
                    if last_stream_agent_id != agent_id or not stream_line_open:
                        if stream_line_open:
                            print()
                        print(f"\n[STREAM:{agent_id}]: ", end="", flush=True)
                        last_stream_agent_id = agent_id
                        stream_line_open = True
                    if event.data and event.data.text:
                        print(event.data.text, end="", flush=True)
                elif event.data and event.data.text:
                    print(event.data.text, end="", flush=True)
            elif isinstance(event, WorkflowOutputEvent):
                output_messages = cast(list[ChatMessage], event.data)
                if output_messages:
                    output = output_messages[-1].text

        if stream_line_open:
            print()
            stream_line_open = False

        if output is not None:
            print(f"Workflow completed with result:\n\n{output}")

    except Exception as e:
        print(f"Workflow execution failed: {e}")


if __name__ == "__main__":
    asyncio.run(main())
