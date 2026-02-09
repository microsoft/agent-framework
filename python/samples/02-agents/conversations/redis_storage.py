# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os

from agent_framework import AgentThread
from agent_framework.openai import OpenAIChatClient
from agent_framework.redis import RedisChatMessageStore

"""
Redis-Backed Conversation Storage

Demonstrates using Redis as a persistent message store for conversation threads.
Messages are stored in Redis and survive application restarts.

Prerequisites:
- Redis server running on localhost:6379
- pip install agent-framework[redis]

For more on Redis storage:
- Full examples: getting_started/threads/redis_chat_message_store_thread.py
- Redis context providers: getting_started/context_providers/redis/
- Docs: https://learn.microsoft.com/agent-framework/concepts/threads
"""


# <basic_redis>
async def basic_redis_example() -> None:
    """Basic Redis-backed conversation."""
    print("=== Basic Redis Storage ===\n")

    redis_store = RedisChatMessageStore(redis_url="redis://localhost:6379")
    print(f"Thread ID: {redis_store.thread_id}")

    thread = AgentThread(message_store=redis_store)

    agent = OpenAIChatClient().as_agent(
        name="RedisBot",
        instructions="You are a helpful assistant.",
    )

    query = "Hello! My name is Alice and I love pizza."
    print(f"User: {query}")
    response = await agent.run(query, thread=thread)
    print(f"Agent: {response.text}\n")

    query = "What do you remember about me?"
    print(f"User: {query}")
    response = await agent.run(query, thread=thread)
    print(f"Agent: {response.text}\n")

    messages = await redis_store.list_messages()
    print(f"Total messages in Redis: {len(messages)}")

    await redis_store.clear()
    await redis_store.aclose()
# </basic_redis>


# <persistence>
async def persistence_example() -> None:
    """Conversation that survives 'restarts' via Redis."""
    print("\n=== Persistence Across Restarts ===\n")

    conversation_id = "persistent_chat_001"

    # Phase 1: Start a conversation
    print("--- Phase 1: Starting conversation ---")
    store1 = RedisChatMessageStore(redis_url="redis://localhost:6379", thread_id=conversation_id)
    thread1 = AgentThread(message_store=store1)

    agent = OpenAIChatClient().as_agent(
        name="PersistentBot",
        instructions="You are a helpful assistant. Remember our conversation history.",
    )

    query = "I'm working on a Python machine learning project."
    print(f"User: {query}")
    response = await agent.run(query, thread=thread1)
    print(f"Agent: {response.text}")
    await store1.aclose()

    # Phase 2: Resume after "restart" — same conversation_id reconnects
    print("\n--- Phase 2: Resuming after restart ---")
    store2 = RedisChatMessageStore(redis_url="redis://localhost:6379", thread_id=conversation_id)
    thread2 = AgentThread(message_store=store2)

    query = "What was I working on?"
    print(f"User: {query}")
    response = await agent.run(query, thread=thread2)
    print(f"Agent: {response.text}")

    await store2.clear()
    await store2.aclose()
# </persistence>


async def main() -> None:
    if not os.getenv("OPENAI_API_KEY"):
        print("ERROR: OPENAI_API_KEY not set")
        return

    try:
        test_store = RedisChatMessageStore(redis_url="redis://localhost:6379")
        connection_ok = await test_store.ping()
        await test_store.aclose()
        if not connection_ok:
            raise Exception("Redis ping failed")
        print("✓ Redis connection successful\n")
    except Exception as e:
        print(f"ERROR: Cannot connect to Redis: {e}")
        print("Please ensure Redis is running on localhost:6379")
        return

    await basic_redis_example()
    await persistence_example()


if __name__ == "__main__":
    asyncio.run(main())
