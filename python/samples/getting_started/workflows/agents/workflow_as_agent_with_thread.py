# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework import AgentThread, ChatAgent, ChatMessageStore, SequentialBuilder
from agent_framework.openai import OpenAIChatClient

"""
Sample: Workflow as Agent with Thread Conversation History and Checkpointing

This sample demonstrates how to use AgentThread with a workflow wrapped as an agent
to maintain conversation history across multiple invocations. When using as_agent(),
the thread's message store history is included in each workflow run, enabling
the workflow participants to reference prior conversation context.

It also demonstrates how to enable checkpointing for workflow execution state
persistence, allowing workflows to be paused and resumed.

Key concepts:
- Workflows can be wrapped as agents using workflow.as_agent()
- AgentThread with ChatMessageStore preserves conversation history
- Each call to agent.run() includes thread history + new message
- Participants in the workflow see the full conversation context
- checkpoint_storage parameter enables workflow state persistence

Use cases:
- Multi-turn conversations with workflow-based orchestrations
- Stateful workflows that need context from previous interactions
- Building conversational agents that leverage workflow patterns
- Long-running workflows that need pause/resume capability

Prerequisites:
- OpenAI environment variables configured for OpenAIChatClient
"""


async def main() -> None:
    # Create a chat client
    chat_client = OpenAIChatClient()

    # Define factory functions for workflow participants
    def create_assistant() -> ChatAgent:
        return chat_client.as_agent(
            name="assistant",
            instructions=(
                "You are a helpful assistant. Answer questions based on the conversation "
                "history. If the user asks about something mentioned earlier, reference it."
            ),
        )

    def create_summarizer() -> ChatAgent:
        return chat_client.as_agent(
            name="summarizer",
            instructions=(
                "You are a summarizer. After the assistant responds, provide a brief "
                "one-sentence summary of the key point from the conversation so far."
            ),
        )

    # Build a sequential workflow: assistant -> summarizer
    workflow = SequentialBuilder().register_participants([create_assistant, create_summarizer]).build()

    # Wrap the workflow as an agent
    agent = workflow.as_agent(name="ConversationalWorkflowAgent")

    # Create a thread with a ChatMessageStore to maintain history
    message_store = ChatMessageStore()
    thread = AgentThread(message_store=message_store)

    print("=" * 60)
    print("Workflow as Agent with Thread - Multi-turn Conversation")
    print("=" * 60)

    # First turn: Introduce a topic
    query1 = "My name is Alex and I'm learning about machine learning."
    print(f"\n[Turn 1] User: {query1}")

    response1 = await agent.run(query1, thread=thread)
    if response1.messages:
        for msg in response1.messages:
            speaker = msg.author_name or msg.role.value
            print(f"[{speaker}]: {msg.text}")

    # Second turn: Reference the previous topic
    query2 = "What was my name again, and what am I learning about?"
    print(f"\n[Turn 2] User: {query2}")

    response2 = await agent.run(query2, thread=thread)
    if response2.messages:
        for msg in response2.messages:
            speaker = msg.author_name or msg.role.value
            print(f"[{speaker}]: {msg.text}")

    # Third turn: Ask a follow-up question
    query3 = "Can you suggest a good first project for me to try?"
    print(f"\n[Turn 3] User: {query3}")

    response3 = await agent.run(query3, thread=thread)
    if response3.messages:
        for msg in response3.messages:
            speaker = msg.author_name or msg.role.value
            print(f"[{speaker}]: {msg.text}")

    # Show the accumulated conversation history
    print("\n" + "=" * 60)
    print("Full Thread History")
    print("=" * 60)
    if thread.message_store:
        history = await thread.message_store.list_messages()
        for i, msg in enumerate(history, start=1):
            role = msg.role.value if hasattr(msg.role, "value") else str(msg.role)
            speaker = msg.author_name or role
            text_preview = msg.text[:80] + "..." if len(msg.text) > 80 else msg.text
            print(f"{i:02d}. [{speaker}]: {text_preview}")


async def demonstrate_thread_serialization() -> None:
    """
    Demonstrates serializing and resuming a thread with a workflow agent.

    This shows how conversation history can be persisted and restored,
    enabling long-running conversational workflows.
    """
    chat_client = OpenAIChatClient()

    def create_assistant() -> ChatAgent:
        return chat_client.as_agent(
            name="memory_assistant",
            instructions="You are a helpful assistant with good memory. Remember details from our conversation.",
        )

    workflow = SequentialBuilder().register_participants([create_assistant]).build()
    agent = workflow.as_agent(name="MemoryWorkflowAgent")

    # Create initial thread and have a conversation
    thread = AgentThread(message_store=ChatMessageStore())

    print("\n" + "=" * 60)
    print("Thread Serialization Demo")
    print("=" * 60)

    # First interaction
    query = "Remember this: the secret code is ALPHA-7."
    print(f"\n[Session 1] User: {query}")
    response = await agent.run(query, thread=thread)
    if response.messages:
        print(f"[assistant]: {response.messages[0].text}")

    # Serialize thread state (could be saved to database/file)
    serialized_state = await thread.serialize()
    print("\n[Serialized thread state for persistence]")

    # Simulate a new session by creating a new thread from serialized state
    restored_thread = AgentThread(message_store=ChatMessageStore())
    await restored_thread.update_from_thread_state(serialized_state)

    # Continue conversation with restored thread
    query = "What was the secret code I told you?"
    print(f"\n[Session 2 - Restored] User: {query}")
    response = await agent.run(query, thread=restored_thread)
    if response.messages:
        print(f"[assistant]: {response.messages[0].text}")


if __name__ == "__main__":
    asyncio.run(main())
    asyncio.run(demonstrate_thread_serialization())
