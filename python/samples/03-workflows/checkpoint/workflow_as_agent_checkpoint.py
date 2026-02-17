# Copyright (c) Microsoft. All rights reserved.

"""
Sample: Workflow as Agent with Checkpointing

Purpose:
This sample demonstrates how to use checkpointing with a workflow wrapped as an agent.
It shows how to enable checkpoint storage when calling agent.run(),
allowing workflow execution state to be persisted and potentially resumed.

What you learn:
- How to pass checkpoint_storage to WorkflowAgent.run()
- How checkpoints are created during workflow-as-agent execution
- How to combine thread conversation history with workflow checkpointing
- How to resume a workflow-as-agent from a checkpoint

Key concepts:
- Thread (AgentSession): Maintains conversation history across agent invocations
- Checkpoint: Persists workflow execution state for pause/resume capability
- These are complementary: sessions track conversation, checkpoints track workflow state

Prerequisites:
- AZURE_AI_PROJECT_ENDPOINT must be your Azure AI Foundry Agent Service (V2) project endpoint.
- Environment variables configured for AzureOpenAIResponsesClient
"""

import asyncio
import os

from agent_framework import (
    InMemoryCheckpointStorage,
    InMemoryHistoryProvider,
)
from agent_framework.azure import AzureOpenAIResponsesClient
from agent_framework.orchestrations import SequentialBuilder
from azure.identity import AzureCliCredential


async def basic_checkpointing() -> None:
    """Demonstrate basic checkpoint storage with workflow-as-agent."""
    print("=" * 60)
    print("Basic Checkpointing with Workflow as Agent")
    print("=" * 60)

    client = AzureOpenAIResponsesClient(
        project_endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
        deployment_name=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        credential=AzureCliCredential(),
    )

    assistant = client.as_agent(
        name="assistant",
        instructions="You are a helpful assistant. Keep responses brief.",
    )

    reviewer = client.as_agent(
        name="reviewer",
        instructions="You are a reviewer. Provide a one-sentence summary of the assistant's response.",
    )

    workflow = SequentialBuilder(participants=[assistant, reviewer]).build()
    agent = workflow.as_agent(name="CheckpointedAgent")

    # Create checkpoint storage
    checkpoint_storage = InMemoryCheckpointStorage()

    # Run with checkpointing enabled
    query = "What are the benefits of renewable energy?"
    print(f"\nUser: {query}")

    response = await agent.run(query, checkpoint_storage=checkpoint_storage)

    for msg in response.messages:
        speaker = msg.author_name or msg.role
        print(f"[{speaker}]: {msg.text}")

    # Show checkpoints that were created
    checkpoints = await checkpoint_storage.list_checkpoints(workflow_name=workflow.name)
    print(f"\nCheckpoints created: {len(checkpoints)}")
    for i, cp in enumerate(checkpoints[:5], 1):
        print(f"  {i}. {cp.checkpoint_id}")


async def checkpointing_with_thread() -> None:
    """Demonstrate combining thread history with checkpointing."""
    print("\n" + "=" * 60)
    print("Checkpointing with Thread Conversation History")
    print("=" * 60)

    client = AzureOpenAIResponsesClient(
        project_endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
        deployment_name=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        credential=AzureCliCredential(),
    )

    assistant = client.as_agent(
        name="memory_assistant",
        instructions="You are a helpful assistant with good memory. Reference previous conversation when relevant.",
    )

    workflow = SequentialBuilder(participants=[assistant]).build()
    agent = workflow.as_agent(name="MemoryAgent")

    # Create both session (for conversation) and checkpoint storage (for workflow state)
    session = agent.create_session()
    checkpoint_storage = InMemoryCheckpointStorage()

    # First turn
    query1 = "My favorite color is blue. Remember that."
    print(f"\n[Turn 1] User: {query1}")
    response1 = await agent.run(query1, session=session, checkpoint_storage=checkpoint_storage)
    if response1.messages:
        print(f"[assistant]: {response1.messages[0].text}")

    # Second turn - agent should remember from session history
    query2 = "What's my favorite color?"
    print(f"\n[Turn 2] User: {query2}")
    response2 = await agent.run(query2, session=session, checkpoint_storage=checkpoint_storage)
    if response2.messages:
        print(f"[assistant]: {response2.messages[0].text}")

    # Show accumulated state
    checkpoints = await checkpoint_storage.list_checkpoints(workflow_name=workflow.name)
    print(f"\nTotal checkpoints across both turns: {len(checkpoints)}")

    memory_state = session.state.get(InMemoryHistoryProvider.DEFAULT_SOURCE_ID, {})
    history = memory_state.get("messages", [])
    print(f"Messages in session history: {len(history)}")


async def streaming_with_checkpoints() -> None:
    """Demonstrate streaming with checkpoint storage."""
    print("\n" + "=" * 60)
    print("Streaming with Checkpointing")
    print("=" * 60)

    client = AzureOpenAIResponsesClient(
        project_endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
        deployment_name=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        credential=AzureCliCredential(),
    )

    assistant = client.as_agent(
        name="streaming_assistant",
        instructions="You are a helpful assistant.",
    )

    workflow = SequentialBuilder(participants=[assistant]).build()
    agent = workflow.as_agent(name="StreamingCheckpointAgent")

    checkpoint_storage = InMemoryCheckpointStorage()

    query = "List three interesting facts about the ocean."
    print(f"\nUser: {query}")
    print("[assistant]: ", end="", flush=True)

    # Stream with checkpointing
    async for update in agent.run(query, checkpoint_storage=checkpoint_storage, stream=True):
        if update.text:
            print(update.text, end="", flush=True)

    print()  # Newline after streaming

    checkpoints = await checkpoint_storage.list_checkpoints(workflow_name=workflow.name)
    print(f"\nCheckpoints created during stream: {len(checkpoints)}")


async def main() -> None:
    """Run all checkpoint examples."""
    await basic_checkpointing()
    await checkpointing_with_thread()
    await streaming_with_checkpoints()


if __name__ == "__main__":
    asyncio.run(main())
