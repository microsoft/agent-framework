# Copyright (c) Microsoft. All rights reserved.
# ruff: noqa: T201

"""Sample: Workflow Checkpointing with Cosmos DB and Azure AI Foundry.

Purpose:
This sample demonstrates how to use CosmosCheckpointStorage with agents built
on Azure AI Foundry (via FoundryChatClient). It shows a multi-agent
workflow where checkpoint state is persisted to Cosmos DB, enabling durable
pause-and-resume across process restarts.

What you learn:
- How to wire CosmosCheckpointStorage with FoundryChatClient agents
- How to combine session history with workflow checkpointing
- How to resume a workflow-as-agent from a Cosmos DB checkpoint

Key concepts:
- AgentSession: Maintains conversation history across agent invocations
- CosmosCheckpointStorage: Persists workflow execution state in Cosmos DB
- These are complementary: sessions track conversation, checkpoints track workflow state

Environment variables:
  FOUNDRY_PROJECT_ENDPOINT                - Azure AI Foundry project endpoint
  FOUNDRY_MODEL                           - Model deployment name
  AZURE_COSMOS_ENDPOINT                  - Cosmos DB account endpoint
  AZURE_COSMOS_DATABASE_NAME             - Database name
  AZURE_COSMOS_CONTAINER_NAME            - Container name for checkpoints
Optional:
  AZURE_COSMOS_KEY                       - Account key (if not using Azure credentials)
"""

import asyncio
import os
from typing import Any

from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from agent_framework.orchestrations import SequentialBuilder
from agent_framework_azure_cosmos import CosmosCheckpointStorage
from azure.identity.aio import AzureCliCredential
from dotenv import load_dotenv

load_dotenv()


async def main() -> None:
    """Run the Azure AI Foundry + Cosmos DB checkpointing sample."""
    project_endpoint = os.getenv("FOUNDRY_PROJECT_ENDPOINT")
    model = os.getenv("FOUNDRY_MODEL")
    cosmos_endpoint = os.getenv("AZURE_COSMOS_ENDPOINT")
    cosmos_database_name = os.getenv("AZURE_COSMOS_DATABASE_NAME")
    cosmos_container_name = os.getenv("AZURE_COSMOS_CONTAINER_NAME")
    cosmos_key = os.getenv("AZURE_COSMOS_KEY")

    if not project_endpoint or not model:
        print("Please set FOUNDRY_PROJECT_ENDPOINT and FOUNDRY_MODEL.")
        return

    if not cosmos_endpoint or not cosmos_database_name or not cosmos_container_name:
        print("Please set AZURE_COSMOS_ENDPOINT, AZURE_COSMOS_DATABASE_NAME, and AZURE_COSMOS_CONTAINER_NAME.")
        return

    # Use a single AzureCliCredential for both Cosmos and Foundry,
    # properly closed via async context manager.
    async with AzureCliCredential() as azure_credential:
        cosmos_credential: Any = cosmos_key if cosmos_key else azure_credential

        async with CosmosCheckpointStorage(
            endpoint=cosmos_endpoint,
            credential=cosmos_credential,
            database_name=cosmos_database_name,
            container_name=cosmos_container_name,
        ) as checkpoint_storage:
            # Create Azure AI Foundry agents
            client = FoundryChatClient(
                project_endpoint=project_endpoint,
                model=model,
                credential=azure_credential,
            )

            assistant = Agent(
                name="assistant",
                instructions="You are a helpful assistant. Keep responses brief.",
                client=client,
            )

            reviewer = Agent(
                name="reviewer",
                instructions="You are a reviewer. Provide a one-sentence summary of the assistant's response.",
                client=client,
            )

            # Build a sequential workflow and wrap it as an agent
            workflow = SequentialBuilder(participants=[assistant, reviewer]).build()
            agent = workflow.as_agent(name="FoundryCheckpointedAgent")

            # --- First run: execute with Cosmos DB checkpointing ---
            print("=== First Run ===\n")

            session = agent.create_session()
            query = "What are the benefits of renewable energy?"
            print(f"User: {query}")

            response = await agent.run(query, session=session, checkpoint_storage=checkpoint_storage)

            for msg in response.messages:
                speaker = msg.author_name or msg.role
                print(f"[{speaker}]: {msg.text}")

            # Show checkpoints persisted in Cosmos DB
            checkpoints = await checkpoint_storage.list_checkpoints(workflow_name=workflow.name)
            print(f"\nCheckpoints in Cosmos DB: {len(checkpoints)}")
            for i, cp in enumerate(checkpoints[:5], 1):
                print(f"  {i}. {cp.checkpoint_id} (iteration={cp.iteration_count})")

            # --- Second run: continue conversation with checkpoint history ---
            print("\n=== Second Run (continuing conversation) ===\n")

            query2 = "Can you elaborate on the economic benefits?"
            print(f"User: {query2}")

            response2 = await agent.run(query2, session=session, checkpoint_storage=checkpoint_storage)

            for msg in response2.messages:
                speaker = msg.author_name or msg.role
                print(f"[{speaker}]: {msg.text}")

            # Show total checkpoints
            all_checkpoints = await checkpoint_storage.list_checkpoints(workflow_name=workflow.name)
            print(f"\nTotal checkpoints after two runs: {len(all_checkpoints)}")

            # Get latest checkpoint
            latest = await checkpoint_storage.get_latest(workflow_name=workflow.name)
            if latest:
                print(f"Latest checkpoint: {latest.checkpoint_id}")
                print(f"  iteration_count: {latest.iteration_count}")
                print(f"  timestamp: {latest.timestamp}")


if __name__ == "__main__":
    asyncio.run(main())
