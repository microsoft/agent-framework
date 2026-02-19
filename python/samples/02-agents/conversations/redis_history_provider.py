# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
from uuid import uuid4

from agent_framework import AgentSession
from agent_framework.openai import OpenAIChatClient
from agent_framework.redis import RedisHistoryProvider
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

"""
Redis History Provider Session Example

This sample demonstrates how to use Redis as a history provider for session
management, enabling persistent conversation history storage across sessions
with Redis as the backend data store.
"""


# Default Redis URL for local Redis Stack.
# Override via the REDIS_URL environment variable for remote or authenticated instances.
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")


async def example_manual_memory_store() -> None:
    """Basic example of using Redis history provider."""
    print("=== Basic Redis History Provider Example ===")

    # Create Redis history provider
    redis_provider = RedisHistoryProvider(
        source_id="redis_basic_chat",
        redis_url=REDIS_URL,
    )

    # Create agent with Redis history provider
    agent = OpenAIChatClient().as_agent(
        name="RedisBot",
        instructions="You are a helpful assistant that remembers our conversation using Redis.",
        context_providers=[redis_provider],
    )

    # Create session
    session = agent.create_session()

    # Have a conversation
    print("\n--- Starting conversation ---")
    query1 = "Hello! My name is Alice and I love pizza."
    print(f"User: {query1}")
    response1 = await agent.run(query1, session=session)
    print(f"Agent: {response1.text}")

    query2 = "What do you remember about me?"
    print(f"User: {query2}")
    response2 = await agent.run(query2, session=session)
    print(f"Agent: {response2.text}")

    print("Done\n")


async def example_user_session_management() -> None:
    """Example of managing user sessions with Redis."""
    print("=== User Session Management Example ===")

    user_id = "alice_123"
    session_id = f"session_{uuid4()}"

    # Create Redis history provider for specific user session
    redis_provider = RedisHistoryProvider(
        source_id=f"redis_{user_id}",
        redis_url=REDIS_URL,
        max_messages=10,  # Keep only last 10 messages
    )

    # Create agent with history provider
    agent = OpenAIChatClient().as_agent(
        name="SessionBot",
        instructions="You are a helpful assistant. Keep track of user preferences.",
        context_providers=[redis_provider],
    )

    # Start conversation
    session = agent.create_session(session_id=session_id)

    print(f"Started session for user {user_id}")

    # Simulate conversation
    queries = [
        "Hi, I'm Alice and I prefer vegetarian food.",
        "What restaurants would you recommend?",
        "I also love Italian cuisine.",
        "Can you remember my food preferences?",
    ]

    for i, query in enumerate(queries, 1):
        print(f"\n--- Message {i} ---")
        print(f"User: {query}")
        response = await agent.run(query, session=session)
        print(f"Agent: {response.text}")

    print("Done\n")


async def example_conversation_persistence() -> None:
    """Example of conversation persistence across application restarts."""
    print("=== Conversation Persistence Example ===")

    # Phase 1: Start conversation
    print("--- Phase 1: Starting conversation ---")
    redis_provider = RedisHistoryProvider(
        source_id="redis_persistent_chat",
        redis_url=REDIS_URL,
    )

    agent = OpenAIChatClient().as_agent(
        name="PersistentBot",
        instructions="You are a helpful assistant. Remember our conversation history.",
        context_providers=[redis_provider],
    )

    session = agent.create_session()

    # Start conversation
    query1 = "Hello! I'm working on a Python project about machine learning."
    print(f"User: {query1}")
    response1 = await agent.run(query1, session=session)
    print(f"Agent: {response1.text}")

    query2 = "I'm specifically interested in neural networks."
    print(f"User: {query2}")
    response2 = await agent.run(query2, session=session)
    print(f"Agent: {response2.text}")

    # Serialize session state
    serialized = session.to_dict()

    # Phase 2: Resume conversation (simulating app restart)
    print("\n--- Phase 2: Resuming conversation (after 'restart') ---")
    restored_session = AgentSession.from_dict(serialized)

    # Continue conversation - agent should remember context
    query3 = "What was I working on before?"
    print(f"User: {query3}")
    response3 = await agent.run(query3, session=restored_session)
    print(f"Agent: {response3.text}")

    query4 = "Can you suggest some Python libraries for neural networks?"
    print(f"User: {query4}")
    response4 = await agent.run(query4, session=restored_session)
    print(f"Agent: {response4.text}")

    print("Done\n")


async def example_session_serialization() -> None:
    """Example of session state serialization and deserialization."""
    print("=== Session Serialization Example ===")

    redis_provider = RedisHistoryProvider(
        source_id="redis_serialization_chat",
        redis_url=REDIS_URL,
    )

    agent = OpenAIChatClient().as_agent(
        name="SerializationBot",
        instructions="You are a helpful assistant.",
        context_providers=[redis_provider],
    )

    session = agent.create_session()

    # Have initial conversation
    print("--- Initial conversation ---")
    query1 = "Hello! I'm testing serialization."
    print(f"User: {query1}")
    response1 = await agent.run(query1, session=session)
    print(f"Agent: {response1.text}")

    # Serialize session state
    serialized = session.to_dict()
    print(f"\nSerialized session state: {serialized}")

    # Deserialize session state (simulating loading from database/file)
    print("\n--- Deserializing session state ---")
    restored_session = AgentSession.from_dict(serialized)

    # Continue conversation with restored session
    query2 = "Do you remember what I said about testing?"
    print(f"User: {query2}")
    response2 = await agent.run(query2, session=restored_session)
    print(f"Agent: {response2.text}")

    print("Done\n")


async def example_message_limits() -> None:
    """Example of automatic message trimming with limits."""
    print("=== Message Limits Example ===")

    # Create provider with small message limit
    redis_provider = RedisHistoryProvider(
        source_id="redis_limited_chat",
        redis_url=REDIS_URL,
        max_messages=3,  # Keep only 3 most recent messages
    )

    agent = OpenAIChatClient().as_agent(
        name="LimitBot",
        instructions="You are a helpful assistant with limited memory.",
        context_providers=[redis_provider],
    )

    session = agent.create_session()

    # Send multiple messages to test trimming
    messages = [
        "Message 1: Hello!",
        "Message 2: How are you?",
        "Message 3: What's the weather?",
        "Message 4: Tell me a joke.",
        "Message 5: This should trigger trimming.",
    ]

    for i, query in enumerate(messages, 1):
        print(f"\n--- Sending message {i} ---")
        print(f"User: {query}")
        response = await agent.run(query, session=session)
        print(f"Agent: {response.text}")

    print("Done\n")


async def main() -> None:
    """Run all Redis history provider examples."""
    print("Redis History Provider Examples")
    print("=" * 50)
    print("Prerequisites:")
    print("- Redis server running (set REDIS_URL env var or default localhost:6379)")
    print("- OPENAI_API_KEY environment variable set")
    print("=" * 50)

    # Check prerequisites
    if not os.getenv("OPENAI_API_KEY"):
        print("ERROR: OPENAI_API_KEY environment variable not set")
        return

    try:
        # Run all examples
        await example_manual_memory_store()
        await example_user_session_management()
        await example_conversation_persistence()
        await example_session_serialization()
        await example_message_limits()

        print("All examples completed successfully!")

    except Exception as e:
        print(f"Error running examples: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
