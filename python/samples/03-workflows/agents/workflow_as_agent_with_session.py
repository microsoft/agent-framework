# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os

from agent_framework import AgentSession, InMemoryHistoryProvider
from agent_framework.azure import AzureOpenAIResponsesClient
from agent_framework.orchestrations import SequentialBuilder
from azure.identity import AzureCliCredential

"""
Sample: Workflow as Agent with Session Conversation History and Checkpointing

This sample demonstrates how to use AgentSession with a workflow wrapped as an agent
to maintain conversation history across multiple invocations. When using as_agent(),
the session's history is included in each workflow run, enabling
the workflow participants to reference prior conversation context.

It also demonstrates how to enable checkpointing for workflow execution state
persistence, allowing workflows to be paused and resumed.

Key concepts:
- Workflows can be wrapped as agents using workflow.as_agent()
- AgentSession preserves conversation history
- Each call to agent.run() includes session history + new message
- Participants in the workflow see the full conversation context
- checkpoint_storage parameter enables workflow state persistence

Use cases:
- Multi-turn conversations with workflow-based orchestrations
- Stateful workflows that need context from previous interactions
- Building conversational agents that leverage workflow patterns
- Long-running workflows that need pause/resume capability

Prerequisites:
- AZURE_AI_PROJECT_ENDPOINT must be your Azure AI Foundry Agent Service (V2) project endpoint.
- Environment variables configured for AzureOpenAIResponsesClient
"""


async def main() -> None:
    # Create a chat client
    client = AzureOpenAIResponsesClient(
        project_endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
        deployment_name=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        credential=AzureCliCredential(),
    )

    assistant = client.as_agent(
        name="assistant",
        instructions=(
            "You are a helpful assistant. Answer questions based on the conversation "
            "history. If the user asks about something mentioned earlier, reference it."
        ),
    )

    summarizer = client.as_agent(
        name="summarizer",
        instructions=(
            "You are a summarizer. After the assistant responds, provide a brief "
            "one-sentence summary of the key point from the conversation so far."
        ),
    )

    # Build a sequential workflow: assistant -> summarizer
    workflow = SequentialBuilder(participants=[assistant, summarizer]).build()

    # Wrap the workflow as an agent
    agent = workflow.as_agent(name="ConversationalWorkflowAgent")

    # Create a session to maintain history
    session = agent.create_session()

    print("=" * 60)
    print("Workflow as Agent with Session - Multi-turn Conversation")
    print("=" * 60)

    # First turn: Introduce a topic
    query1 = "My name is Alex and I'm learning about machine learning."
    print(f"\n[Turn 1] User: {query1}")

    response1 = await agent.run(query1, session=session)
    if response1.messages:
        for msg in response1.messages:
            speaker = msg.author_name or msg.role
            print(f"[{speaker}]: {msg.text}")

    # Second turn: Reference the previous topic
    query2 = "What was my name again, and what am I learning about?"
    print(f"\n[Turn 2] User: {query2}")

    response2 = await agent.run(query2, session=session)
    if response2.messages:
        for msg in response2.messages:
            speaker = msg.author_name or msg.role
            print(f"[{speaker}]: {msg.text}")

    # Third turn: Ask a follow-up question
    query3 = "Can you suggest a good first project for me to try?"
    print(f"\n[Turn 3] User: {query3}")

    response3 = await agent.run(query3, session=session)
    if response3.messages:
        for msg in response3.messages:
            speaker = msg.author_name or msg.role
            print(f"[{speaker}]: {msg.text}")

    # Show the accumulated conversation history
    print("\n" + "=" * 60)
    print("Full Session History")
    print("=" * 60)
    memory_state = session.state.get(InMemoryHistoryProvider.DEFAULT_SOURCE_ID, {})
    history = memory_state.get("messages", [])
    for i, msg in enumerate(history, start=1):
        role = msg.role if hasattr(msg.role, "value") else str(msg.role)
        speaker = msg.author_name or role
        text_preview = msg.text[:80] + "..." if len(msg.text) > 80 else msg.text
        print(f"{i:02d}. [{speaker}]: {text_preview}")


async def demonstrate_session_serialization() -> None:
    """
    Demonstrates serializing and resuming a session with a workflow agent.

    This shows how conversation history can be persisted and restored,
    enabling long-running conversational workflows.
    """
    client = AzureOpenAIResponsesClient(
        project_endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
        deployment_name=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        credential=AzureCliCredential(),
    )

    memory_assistant = client.as_agent(
        name="memory_assistant",
        instructions="You are a helpful assistant with good memory. Remember details from our conversation.",
    )

    workflow = SequentialBuilder(participants=[memory_assistant]).build()
    agent = workflow.as_agent(name="MemoryWorkflowAgent")

    # Create initial session and have a conversation
    session = agent.create_session()

    print("\n" + "=" * 60)
    print("Session Serialization Demo")
    print("=" * 60)

    # First interaction
    query = "Remember this: the secret code is ALPHA-7."
    print(f"\n[Session 1] User: {query}")
    response = await agent.run(query, session=session)
    if response.messages:
        print(f"[assistant]: {response.messages[0].text}")

    # Serialize session state (could be saved to database/file)
    serialized_state = session.to_dict()
    print("\n[Serialized session state for persistence]")

    # Simulate a new session by creating a new session from serialized state
    restored_session = AgentSession.from_dict(serialized_state)

    # Continue conversation with restored session
    query = "What was the secret code I told you?"
    print(f"\n[Session 2 - Restored] User: {query}")
    response = await agent.run(query, session=restored_session)
    if response.messages:
        print(f"[assistant]: {response.messages[0].text}")


if __name__ == "__main__":
    asyncio.run(main())
    asyncio.run(demonstrate_session_serialization())
