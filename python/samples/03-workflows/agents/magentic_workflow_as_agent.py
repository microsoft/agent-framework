# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os

from agent_framework import (
    Agent,
)
from agent_framework.azure import AzureOpenAIResponsesClient
from agent_framework.orchestrations import MagenticBuilder
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

"""
Sample: Build a Magentic orchestration and wrap it as an agent.

The script configures a Magentic workflow with streaming callbacks, then invokes the
orchestration through `workflow.as_agent(...)` so the entire Magentic loop can be reused
like any other agent while still emitting callback telemetry.

Prerequisites:
- AZURE_AI_PROJECT_ENDPOINT must be your Azure AI Foundry Agent Service (V2) project endpoint.
- OpenAI credentials configured for `AzureOpenAIResponsesClient` and `AzureOpenAIResponsesClient`.
"""


async def main() -> None:
    researcher_agent = Agent(
        name="ResearcherAgent",
        description="Specialist in research and information gathering",
        instructions=(
            "You are a Researcher. You find information without additional computation or quantitative analysis."
        ),
        # This agent requires the gpt-4o-search-preview model to perform web searches.
        client=AzureOpenAIResponsesClient(
            project_endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
            deployment_name=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
            credential=AzureCliCredential(),
        ),
    )

    # Create code interpreter tool using instance method
    coder_client = AzureOpenAIResponsesClient(
        project_endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
        deployment_name=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        credential=AzureCliCredential(),
    )
    code_interpreter_tool = coder_client.get_code_interpreter_tool()

    coder_agent = Agent(
        name="CoderAgent",
        description="A helpful assistant that writes and executes code to process and analyze data.",
        instructions="You solve questions using code. Please provide detailed analysis and computation process.",
        client=coder_client,
        tools=code_interpreter_tool,
    )

    # Create a manager agent for orchestration
    manager_agent = Agent(
        name="MagenticManager",
        description="Orchestrator that coordinates the research and coding workflow",
        instructions="You coordinate a team to complete complex tasks efficiently.",
        client=AzureOpenAIResponsesClient(
            project_endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
            deployment_name=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
            credential=AzureCliCredential(),
        ),
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

    try:
        # Wrap the workflow as an agent for composition scenarios
        print("\nWrapping workflow as an agent and running...")
        workflow_agent = workflow.as_agent(name="MagenticWorkflowAgent")

        last_response_id: str | None = None
        async for update in workflow_agent.run(task, stream=True):
            # Fallback for any other events with text
            if last_response_id != update.response_id:
                if last_response_id is not None:
                    print()  # Newline between different responses
                print(f"{update.author_name}: ", end="", flush=True)
                last_response_id = update.response_id
            else:
                print(update.text, end="", flush=True)

    except Exception as e:
        print(f"Workflow execution failed: {e}")


if __name__ == "__main__":
    asyncio.run(main())
