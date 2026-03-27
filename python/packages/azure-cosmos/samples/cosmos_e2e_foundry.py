# Copyright (c) Microsoft. All rights reserved.
# ruff: noqa: T201

"""Sample: Combined History Provider + Checkpoint Storage with Azure AI Foundry.

Purpose:
This sample demonstrates using both CosmosHistoryProvider (conversation memory)
and CosmosCheckpointStorage (workflow pause/resume) together in a single Azure AI
Foundry agent application. This is the recommended production pattern for customers
who need both durable conversations and durable workflow execution.

What you learn:
- How to wire both CosmosHistoryProvider and CosmosCheckpointStorage in one app
- How conversation history and workflow checkpoints serve complementary roles
- How to resume both conversation context and workflow execution state

Key concepts:
- CosmosHistoryProvider: Persists conversation messages across sessions
- CosmosCheckpointStorage: Persists workflow execution state for pause/resume
- Together they enable fully durable agent workflows

Environment variables:
  AZURE_AI_PROJECT_ENDPOINT              - Azure AI Foundry project endpoint
  AZURE_AI_MODEL_DEPLOYMENT_NAME         - Model deployment name
  AZURE_COSMOS_ENDPOINT                  - Cosmos DB account endpoint
  AZURE_COSMOS_DATABASE_NAME             - Database name
Optional:
  AZURE_COSMOS_KEY                       - Account key (if not using Azure credentials)
"""

import asyncio
import os
from typing import Any

from agent_framework import WorkflowAgent, WorkflowCheckpoint
from agent_framework.azure import AzureOpenAIResponsesClient
from agent_framework.orchestrations import SequentialBuilder
from azure.identity.aio import AzureCliCredential
from dotenv import load_dotenv

from agent_framework_azure_cosmos import CosmosCheckpointStorage, CosmosHistoryProvider

load_dotenv()


async def main() -> None:
    """Run the combined history + checkpoint sample."""
    project_endpoint = os.getenv("AZURE_AI_PROJECT_ENDPOINT")
    deployment_name = os.getenv("AZURE_AI_MODEL_DEPLOYMENT_NAME")
    cosmos_endpoint = os.getenv("AZURE_COSMOS_ENDPOINT")
    cosmos_database_name = os.getenv("AZURE_COSMOS_DATABASE_NAME")
    cosmos_key = os.getenv("AZURE_COSMOS_KEY")

    if not project_endpoint or not deployment_name:
        print("Please set AZURE_AI_PROJECT_ENDPOINT and AZURE_AI_MODEL_DEPLOYMENT_NAME.")
        return

    if not cosmos_endpoint or not cosmos_database_name:
        print("Please set AZURE_COSMOS_ENDPOINT and AZURE_COSMOS_DATABASE_NAME.")
        return

    async with AzureCliCredential() as azure_credential:
        cosmos_credential: Any = cosmos_key if cosmos_key else azure_credential

        # CosmosHistoryProvider: stores conversation messages
        # CosmosCheckpointStorage: stores workflow execution state
        async with (
            CosmosHistoryProvider(
                endpoint=cosmos_endpoint,
                database_name=cosmos_database_name,
                container_name="conversation-history",
                credential=cosmos_credential,
            ) as history_provider,
            CosmosCheckpointStorage(
                endpoint=cosmos_endpoint,
                credential=cosmos_credential,
                database_name=cosmos_database_name,
                container_name="workflow-checkpoints",
            ) as checkpoint_storage,
        ):
            # Create Azure AI Foundry agents
            client = AzureOpenAIResponsesClient(
                project_endpoint=project_endpoint,
                deployment_name=deployment_name,
                credential=azure_credential,
            )

            assistant = client.as_agent(
                name="assistant",
                instructions="You are a helpful assistant. Keep responses brief.",
            )

            reviewer = client.as_agent(
                name="reviewer",
                instructions=(
                    "You are a reviewer. Provide a one-sentence "
                    "summary of the assistant's response."
                ),
            )

            # Build a workflow with both history and checkpointing.
            # Attach the history provider to the WorkflowAgent (outer agent)
            # so conversation messages are persisted at the agent level.
            workflow = SequentialBuilder(
                participants=[assistant, reviewer],
            ).build()
            agent = WorkflowAgent(
                workflow,
                name="DurableAgent",
                context_providers=[history_provider],
            )

            # --- First run ---
            print("=== First Run ===\n")
            session = agent.create_session()

            response = await agent.run(
                "What are three benefits of cloud computing?",
                session=session,
                checkpoint_storage=checkpoint_storage,
            )

            for msg in response.messages:
                speaker = msg.author_name or msg.role
                print(f"[{speaker}]: {msg.text}")

            # Show what's persisted
            checkpoints = await checkpoint_storage.list_checkpoints(
                workflow_name=workflow.name,
            )
            history = await history_provider.get_messages(session.session_id)

            print(f"\nConversation messages in Cosmos DB: {len(history)}")
            print(f"Workflow checkpoints in Cosmos DB: {len(checkpoints)}")

            # --- Second run: conversation context is loaded from history ---
            print("\n=== Second Run (with conversation context) ===\n")

            response2 = await agent.run(
                "Can you elaborate on the first benefit?",
                session=session,
                checkpoint_storage=checkpoint_storage,
            )

            for msg in response2.messages:
                speaker = msg.author_name or msg.role
                print(f"[{speaker}]: {msg.text}")

            # Show updated state
            latest: WorkflowCheckpoint | None = await checkpoint_storage.get_latest(
                workflow_name=workflow.name,
            )
            history2 = await history_provider.get_messages(session.session_id)

            print(f"\nConversation messages after 2 runs: {len(history2)}")
            if latest:
                print(f"Latest checkpoint: {latest.checkpoint_id}")
                print(f"  iteration_count: {latest.iteration_count}")


if __name__ == "__main__":
    asyncio.run(main())
