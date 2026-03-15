# Copyright (c) Microsoft. All rights reserved.

import asyncio
import json
import logging
import os
from typing import cast

from agent_framework import (
    Agent,
    AgentResponseUpdate,
    Message,
    WorkflowEvent,
)
from agent_framework.azure import AzureOpenAIResponsesClient
from agent_framework.orchestrations import GroupChatRequestSentEvent, MagenticBuilder, MagenticProgressLedger
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)


"""
Sample: Magentic Orchestration (multi-agent)

What it does:
- Orchestrates multiple agents using `MagenticBuilder` with streaming callbacks.

- ResearcherAgent (Agent backed by an OpenAI chat client) for
    finding information.
- CoderAgent (Agent backed by OpenAI Assistants with the hosted
    code interpreter tool) for analysis and computation.

The workflow is configured with:
- A Standard Magentic manager (uses a chat client for planning and progress).
- Callbacks for final results, per-message agent responses, and streaming
    token updates.

When run, the script builds the workflow, submits a task about estimating the
energy efficiency and CO2 emissions of several ML models, streams intermediate
events, and prints the final answer. The workflow completes when idle.

Prerequisites:
- AZURE_AI_PROJECT_ENDPOINT must be your Azure AI Foundry Agent Service (V2) project endpoint.
- Azure OpenAI configured for AzureOpenAIResponsesClient with required environment variables.
- Authentication via azure-identity. Use AzureCliCredential and run az login before executing the sample.
"""

# Load environment variables from .env file
load_dotenv()


async def main() -> None:
    client = AzureOpenAIResponsesClient(
        project_endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
        deployment_name=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        credential=AzureCliCredential(),
    )

    researcher_agent = Agent(
        name="ResearcherAgent",
        description="Specialist in research and information gathering",
        instructions=(
            "You are a Researcher. You find information without additional computation or quantitative analysis."
        ),
        client=client,
    )

    # Create code interpreter tool using instance method
    code_interpreter_tool = client.get_code_interpreter_tool()

    coder_agent = Agent(
        name="CoderAgent",
        description="A helpful assistant that writes and executes code to process and analyze data.",
        instructions="You solve questions using code. Please provide detailed analysis and computation process.",
        client=client,
        tools=code_interpreter_tool,
    )

    # Create a manager agent for orchestration
    manager_agent = Agent(
        name="MagenticManager",
        description="Orchestrator that coordinates the research and coding workflow",
        instructions="You coordinate a team to complete complex tasks efficiently.",
        client=client,
    )

    print("\nBuilding Magentic Workflow...")

    # intermediate_outputs=True: Enable intermediate outputs to observe the conversation as it unfolds
    # (Intermediate outputs will be emitted as WorkflowOutputEvent events)
    workflow = MagenticBuilder(
        participants=[researcher_agent, coder_agent],
        intermediate_outputs=True,
        manager_agent=manager_agent,
        max_round_count=10,
        max_stall_count=3,
        max_reset_count=2,
    ).build()

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
    last_response_id: str | None = None
    output_event: WorkflowEvent | None = None
    async for event in workflow.run(task, stream=True):
        if event.type == "output" and isinstance(event.data, AgentResponseUpdate):
            response_id = event.data.response_id
            if response_id != last_response_id:
                if last_response_id is not None:
                    print("\n")
                print(f"- {event.executor_id}:", end=" ", flush=True)
                last_response_id = response_id
            print(event.data, end="", flush=True)

        elif event.type == "magentic_orchestrator":
            print(f"\n[Magentic Orchestrator Event] Type: {event.data.event_type.name}")
            if isinstance(event.data.content, Message):
                print(f"Please review the plan:\n{event.data.content.text}")
            elif isinstance(event.data.content, MagenticProgressLedger):
                print(f"Please review progress ledger:\n{json.dumps(event.data.content.to_dict(), indent=2)}")
            else:
                print(f"Unknown data type in MagenticOrchestratorEvent: {type(event.data.content)}")

            # Block to allow user to read the plan/progress before continuing
            # Note: this is for demonstration only and is not the recommended way to handle human interaction.
            # Please refer to `with_plan_review` for proper human interaction during planning phases.
            await asyncio.get_event_loop().run_in_executor(None, input, "Press Enter to continue...")

        elif event.type == "group_chat" and isinstance(event.data, GroupChatRequestSentEvent):
            print(f"\n[REQUEST SENT ({event.data.round_index})] to agent: {event.data.participant_name}")

        elif event.type == "output":
            output_event = event

    if output_event:
        # The output of the magentic workflow is a collection of chat messages from all participants
        outputs = cast(list[Message], output_event.data)
        print("\n" + "=" * 80)
        print("\nFinal Conversation Transcript:\n")
        for message in outputs:
            print(f"{message.author_name or message.role}: {message.text}\n")


if __name__ == "__main__":
    asyncio.run(main())
