# Copyright (c) Microsoft. All rights reserved.

"""Sample usage of CosmosMemoryContextProvider.

This example demonstrates:
1. Creating a provider with Azure credentials
2. Using it with an OpenAI agent
3. Multi-turn conversation with memory
4. Combining with history providers

Prerequisites:
    Install the package in development mode first:
        pip install -e .
    
    Then run this sample:
        python samples/basic_usage.py
"""

import asyncio
import os

from agent_framework import Message
from agent_framework._sessions import AgentSession, SessionContext
from agent_framework_azure_cosmos_memory import CosmosMemoryContextProvider
from azure.identity.aio import DefaultAzureCredential


async def basic_example() -> None:
    """Basic example with environment variables."""
    # Create provider - reads from environment
    async with CosmosMemoryContextProvider(
        cosmos_endpoint=os.environ["COSMOS_DB_ENDPOINT"],
        ai_foundry_endpoint=os.environ["AI_FOUNDRY_ENDPOINT"],
        credential=DefaultAzureCredential(),
    ) as provider:
        # Use with agent session
        session = AgentSession(session_id="user-session-123")
        session.state["user_id"] = "alice"
        session.state["thread_id"] = "conversation-1"

        # Simulate agent run - before_run searches memories
        ctx = SessionContext(
            input_messages=[Message(role="user", contents=["What do you know about my preferences?"])],
            session_id=session.session_id,
        )

        await provider.before_run(
            agent=None, session=session, context=ctx, state=session.state.setdefault(provider.source_id, {})
        )  # type: ignore

        print(f"Retrieved {len(ctx.context_messages.get(provider.source_id, []))} memory messages")

        # After agent responds, store the conversation
        await provider.after_run(
            agent=None, session=session, context=ctx, state=session.state.setdefault(provider.source_id, {})
        )  # type: ignore

        print("Conversation stored for future memory extraction")


async def custom_config_example() -> None:
    """Example with custom configuration."""
    provider = CosmosMemoryContextProvider(
        source_id="custom_memory",
        cosmos_endpoint=os.environ["COSMOS_DB_ENDPOINT"],
        cosmos_database="my_agent_memory",
        ai_foundry_endpoint=os.environ["AI_FOUNDRY_ENDPOINT"],
        embedding_deployment_name="text-embedding-3-large",
        chat_deployment_name="gpt-4o-mini",
        credential=DefaultAzureCredential(),
        top_k=10,  # Retrieve more memories
        min_confidence=0.8,  # Higher confidence threshold
        memory_types=["fact", "procedural", "episodic"],  # Include episodic memories
        context_prompt="## What I Remember About You",
        processor_config={
            "FACT_EXTRACTION_EVERY_N": "1",  # Extract facts every message
            "USER_SUMMARY_EVERY_N": "5",  # Update user profile every 5 messages
        },
    )

    async with provider:
        session = AgentSession(session_id="demo-session")
        session.state["user_id"] = "bob"

        ctx = SessionContext(
            input_messages=[Message(role="user", contents=["I'm learning Rust programming"])],
            session_id=session.session_id,
        )

        await provider.before_run(
            agent=None, session=session, context=ctx, state=session.state.setdefault(provider.source_id, {})
        )  # type: ignore
        await provider.after_run(
            agent=None, session=session, context=ctx, state=session.state.setdefault(provider.source_id, {})
        )  # type: ignore

        print("Custom configured provider executed successfully")


async def multi_provider_example() -> None:
    """Example combining memory with other providers."""
    from agent_framework_azure_cosmos_memory import CosmosMemoryContextProvider

    # Combine semantic memory with conversation history
    memory_provider = CosmosMemoryContextProvider(
        source_id="semantic_memory",
        cosmos_endpoint=os.environ["COSMOS_DB_ENDPOINT"],
        ai_foundry_endpoint=os.environ["AI_FOUNDRY_ENDPOINT"],
        credential=DefaultAzureCredential(),
        memory_types=["fact", "procedural"],  # Long-term facts
    )

    # Note: In real usage, you'd also add a history provider like:
    # from agent_framework_azure_cosmos import CosmosHistoryProvider
    # history_provider = CosmosHistoryProvider(...)

    async with memory_provider:
        session = AgentSession(session_id="multi-provider-session")
        session.state["user_id"] = "charlie"
        session.state["thread_id"] = "support-thread-456"

        ctx = SessionContext(
            input_messages=[Message(role="user", contents=["How do I configure authentication?"])],
            session_id=session.session_id,
        )

        # Both providers would be called in agent run
        await memory_provider.before_run(
            agent=None, session=session, context=ctx, state=session.state.setdefault(memory_provider.source_id, {})
        )  # type: ignore

        print("Multi-provider setup ready")


if __name__ == "__main__":
    print("=== Basic Example ===")
    asyncio.run(basic_example())

    print("\n=== Custom Config Example ===")
    asyncio.run(custom_config_example())

    print("\n=== Multi-Provider Example ===")
    asyncio.run(multi_provider_example())
