# Copyright (c) Microsoft. All rights reserved.

"""Redis Context Provider: Memory scoping examples

This sample demonstrates how conversational memory can be scoped when using the
Redis context provider. It covers three scenarios:

1) Cross-session memory
   - Memories are shared across all sessions for a given app/agent/user.
   - New sessions can still retrieve memories stored in earlier sessions.

2) Session-specific memory
   - Demonstrates storing and retrieving memories within a single session,
     with memories also accessible from new sessions due to cross-session retrieval.

3) Multiple agents with isolated memory
   - Use different agent_id values to keep memories separated for different
     agent personas, even when the user_id is the same.

Requirements:
  - A Redis instance with RediSearch enabled (e.g., Redis Stack)
  - agent-framework with the Redis extra installed: pip install "agent-framework-redis"
  - Optionally an OpenAI API key for the chat client in this demo

Run:
  python redis_sessions.py
"""

import asyncio
import os

from agent_framework.openai import OpenAIChatClient
from agent_framework.redis import RedisContextProvider
from redisvl.extensions.cache.embeddings import EmbeddingsCache
from redisvl.utils.vectorize import OpenAITextVectorizer

# Please set the OPENAI_API_KEY and OPENAI_CHAT_MODEL_ID environment variables to use the OpenAI vectorizer
# Recommend default for OPENAI_CHAT_MODEL_ID is gpt-4o-mini


async def example_cross_session_memory() -> None:
    """Example 1: Cross-session memory (memories shared across all sessions for a user)."""
    print("1. Cross-Session Memory Example:")
    print("-" * 40)

    client = OpenAIChatClient(
        model_id=os.getenv("OPENAI_CHAT_MODEL_ID", "gpt-4o-mini"),
        api_key=os.getenv("OPENAI_API_KEY"),
    )

    provider = RedisContextProvider(
        redis_url="redis://localhost:6379",
        index_name="redis_threads_global",
        application_id="threads_demo_app",
        agent_id="threads_demo_agent",
        user_id="threads_demo_user",
    )

    agent = client.as_agent(
        name="MemoryAssistant",
        instructions=(
            "You are a helpful assistant. Personalize replies using provided context. "
            "Before answering, always check for stored context containing information"
        ),
        tools=[],
        context_providers=[provider],
    )

    # Store a preference
    query = "Remember that I prefer technical responses with code examples when discussing programming."
    print(f"User: {query}")
    result = await agent.run(query)
    print(f"Agent: {result}\n")

    # Create a new session - memories should still be accessible because
    # RedisContextProvider retrieves across all sessions for the same app/agent/user
    new_session = agent.create_session()
    query = "What technical responses do I prefer?"
    print(f"User (new session): {query}")
    result = await agent.run(query, session=new_session)
    print(f"Agent: {result}\n")

    # Clean up the Redis index
    await provider.redis_index.delete()


async def example_session_memory_with_vectorizer() -> None:
    """Example 2: Session memory with a custom vectorizer for hybrid search.

    Demonstrates storing and retrieving memories within a session using
    a custom OpenAI vectorizer for hybrid (text + vector) search. Memories
    are also accessible from new sessions due to cross-session retrieval.
    """
    print("2. Session Memory with Vectorizer Example:")
    print("-" * 40)

    client = OpenAIChatClient(
        model_id=os.getenv("OPENAI_CHAT_MODEL_ID", "gpt-4o-mini"),
        api_key=os.getenv("OPENAI_API_KEY"),
    )

    vectorizer = OpenAITextVectorizer(
        model="text-embedding-ada-002",
        api_config={"api_key": os.getenv("OPENAI_API_KEY")},
        cache=EmbeddingsCache(name="openai_embeddings_cache", redis_url="redis://localhost:6379"),
    )

    provider = RedisContextProvider(
        redis_url="redis://localhost:6379",
        index_name="redis_threads_dynamic",
        application_id="threads_demo_app",
        agent_id="threads_demo_agent",
        user_id="threads_demo_user",
        redis_vectorizer=vectorizer,
        vector_field_name="vector",
        vector_algorithm="hnsw",
        vector_distance_metric="cosine",
    )

    agent = client.as_agent(
        name="VectorizerMemoryAssistant",
        instructions="You are an assistant with hybrid search memory.",
        context_providers=[provider],
    )

    # Create a specific session for this scoped provider
    dedicated_session = agent.create_session()

    # Store some information in the dedicated session
    query = "Remember that for this conversation, I'm working on a Python project about data analysis."
    print(f"User (dedicated session): {query}")
    result = await agent.run(query, session=dedicated_session)
    print(f"Agent: {result}\n")

    # Test memory retrieval in the same dedicated session
    query = "What project am I working on?"
    print(f"User (same dedicated session): {query}")
    result = await agent.run(query, session=dedicated_session)
    print(f"Agent: {result}\n")

    # Store more information in the same session
    query = "Also remember that I prefer using pandas and matplotlib for this project."
    print(f"User (same dedicated session): {query}")
    result = await agent.run(query, session=dedicated_session)
    print(f"Agent: {result}\n")

    # Test comprehensive memory retrieval
    query = "What do you know about my current project and preferences?"
    print(f"User (same dedicated session): {query}")
    result = await agent.run(query, session=dedicated_session)
    print(f"Agent: {result}\n")

    # Clean up the Redis index
    await provider.redis_index.delete()


async def example_multiple_agents() -> None:
    """Example 3: Multiple agents with isolated memory (isolated via agent_id) but within 1 index."""
    print("3. Multiple Agents with Isolated Memory:")
    print("-" * 40)

    client = OpenAIChatClient(
        model_id=os.getenv("OPENAI_CHAT_MODEL_ID", "gpt-4o-mini"),
        api_key=os.getenv("OPENAI_API_KEY"),
    )

    vectorizer = OpenAITextVectorizer(
        model="text-embedding-ada-002",
        api_config={"api_key": os.getenv("OPENAI_API_KEY")},
        cache=EmbeddingsCache(name="openai_embeddings_cache", redis_url="redis://localhost:6379"),
    )

    personal_provider = RedisContextProvider(
        redis_url="redis://localhost:6379",
        index_name="redis_threads_agents",
        application_id="threads_demo_app",
        agent_id="agent_personal",
        user_id="threads_demo_user",
        redis_vectorizer=vectorizer,
        vector_field_name="vector",
        vector_algorithm="hnsw",
        vector_distance_metric="cosine",
    )

    personal_agent = client.as_agent(
        name="PersonalAssistant",
        instructions="You are a personal assistant that helps with personal tasks.",
        context_providers=[personal_provider],
    )

    work_provider = RedisContextProvider(
        redis_url="redis://localhost:6379",
        index_name="redis_threads_agents",
        application_id="threads_demo_app",
        agent_id="agent_work",
        user_id="threads_demo_user",
        redis_vectorizer=vectorizer,
        vector_field_name="vector",
        vector_algorithm="hnsw",
        vector_distance_metric="cosine",
    )

    work_agent = client.as_agent(
        name="WorkAssistant",
        instructions="You are a work assistant that helps with professional tasks.",
        context_providers=[work_provider],
    )

    # Store personal information
    query = "Remember that I like to exercise at 6 AM and prefer outdoor activities."
    print(f"User to Personal Agent: {query}")
    result = await personal_agent.run(query)
    print(f"Personal Agent: {result}\n")

    # Store work information
    query = "Remember that I have team meetings every Tuesday at 2 PM."
    print(f"User to Work Agent: {query}")
    result = await work_agent.run(query)
    print(f"Work Agent: {result}\n")

    # Test memory isolation
    query = "What do you know about my schedule?"
    print(f"User to Personal Agent: {query}")
    result = await personal_agent.run(query)
    print(f"Personal Agent: {result}\n")

    print(f"User to Work Agent: {query}")
    result = await work_agent.run(query)
    print(f"Work Agent: {result}\n")

    # Clean up the Redis index (shared)
    await work_provider.redis_index.delete()


async def main() -> None:
    print("=== Redis Memory Scoping Examples ===\n")
    await example_cross_session_memory()
    await example_session_memory_with_vectorizer()
    await example_multiple_agents()


if __name__ == "__main__":
    asyncio.run(main())
