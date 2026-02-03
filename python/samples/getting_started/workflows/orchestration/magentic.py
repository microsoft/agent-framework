# Copyright (c) Microsoft. All rights reserved.

import asyncio
import json
import logging
from typing import cast

from agent_framework import (
    AgentRunUpdateEvent,
    ChatAgent,
    ChatMessage,
    GroupChatRequestSentEvent,
    HostedCodeInterpreterTool,
    MagenticBuilder,
    MagenticOrchestratorEvent,
    MagenticProgressLedger,
    WorkflowOutputEvent,
    tool,
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

    workflow = (
        MagenticBuilder()
        .participants([researcher_agent, coder_agent])
        .with_manager(
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

    # Keep track of the last executor to format output nicely in streaming mode
    last_message_id: str | None = None
    output_event: WorkflowOutputEvent | None = None
    async for event in workflow.run_stream(task):
        if isinstance(event, AgentRunUpdateEvent):
            message_id = event.data.message_id
            if message_id != last_message_id:
                if last_message_id is not None:
                    print("\n")
                print(f"- {event.executor_id}:", end=" ", flush=True)
                last_message_id = message_id
            print(event.data, end="", flush=True)

        elif isinstance(event, MagenticOrchestratorEvent):
            print(f"\n[Magentic Orchestrator Event] Type: {event.event_type.name}")
            if isinstance(event.data, ChatMessage):
                print(f"Please review the plan:\n{event.data.text}")
            elif isinstance(event.data, MagenticProgressLedger):
                print(f"Please review progress ledger:\n{json.dumps(event.data.to_dict(), indent=2)}")
            else:
                print(f"Unknown data type in MagenticOrchestratorEvent: {type(event.data)}")

            # Block to allow user to read the plan/progress before continuing
            # Note: this is for demonstration only and is not the recommended way to handle human interaction.
            # Please refer to `with_plan_review` for proper human interaction during planning phases.
            await asyncio.get_event_loop().run_in_executor(None, input, "Press Enter to continue...")

        elif isinstance(event, GroupChatRequestSentEvent):
            print(f"\n[REQUEST SENT ({event.round_index})] to agent: {event.participant_name}")

        elif isinstance(event, WorkflowOutputEvent):
            output_event = event

    if not output_event:
        raise RuntimeError("Workflow did not produce a final output event.")
    print("\n\nWorkflow completed!")
    print("Final Output:")
    # The output of the Magentic workflow is a list of ChatMessages with only one final message
    # generated by the orchestrator.
    output_messages = cast(list[ChatMessage], output_event.data)
    if output_messages:
        output = output_messages[-1].text
        print(output)


if __name__ == "__main__":
    asyncio.run(main())
