# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os

from agent_framework import Agent
from agent_framework.azure import AzureOpenAIResponsesClient
from agent_framework.orchestrations import GroupChatBuilder
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

"""
Sample: Group Chat Orchestration

What it does:
- Demonstrates the generic GroupChatBuilder with a agent orchestrator directing two agents.
- The orchestrator coordinates a researcher (chat completions) and a writer (responses API) to solve a task.

Prerequisites:
- AZURE_AI_PROJECT_ENDPOINT must be your Azure AI Foundry Agent Service (V2) project endpoint.
- Environment variables configured for `AzureOpenAIResponsesClient`.
"""


async def main() -> None:
    researcher = Agent(
        name="Researcher",
        description="Collects relevant background information.",
        instructions="Gather concise facts that help a teammate answer the question.",
        client=AzureOpenAIResponsesClient(
            project_endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
            deployment_name=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
            credential=AzureCliCredential(),
        ),
    )

    writer = Agent(
        name="Writer",
        description="Synthesizes a polished answer using the gathered notes.",
        instructions="Compose clear and structured answers using any notes provided.",
        client=AzureOpenAIResponsesClient(
            project_endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
            deployment_name=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
            credential=AzureCliCredential(),
        ),
    )

    # intermediate_outputs=True: Enable intermediate outputs to observe the conversation as it unfolds
    # (Intermediate outputs will be emitted as WorkflowOutputEvent events)
    workflow = GroupChatBuilder(
        participants=[researcher, writer],
        intermediate_outputs=True,
        orchestrator_agent=AzureOpenAIResponsesClient(
            project_endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
            deployment_name=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
            credential=AzureCliCredential(),
        ).as_agent(
            name="Orchestrator",
            instructions="You coordinate a team conversation to solve the user's task.",
        ),
    ).build()

    task = "Outline the core considerations for planning a community hackathon, and finish with a concise action plan."

    print("\nStarting Group Chat Workflow...\n")
    print(f"Input: {task}\n")

    try:
        workflow_agent = workflow.as_agent(name="GroupChatWorkflowAgent")
        agent_result = await workflow_agent.run(task)

        if agent_result.messages:
            # The output should contain a message from the researcher, a message from the writer,
            # and a final synthesized answer from the orchestrator.
            print("\n===== as_agent() Transcript =====")
            for i, msg in enumerate(agent_result.messages, start=1):
                role_value = getattr(msg.role, "value", msg.role)
                speaker = msg.author_name or role_value
                print(f"{'-' * 50}\n{i:02d} [{speaker}]\n{msg.text}")

    except Exception as e:
        print(f"Workflow execution failed: {e}")


if __name__ == "__main__":
    asyncio.run(main())
