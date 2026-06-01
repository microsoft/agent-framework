# Copyright (c) Microsoft. All rights reserved.

"""Redis Context Provider: Memory scoping examples

This sample demonstrates how conversational memory can be scoped when using the
Redis context provider. It covers three scenarios:

1) Global memory scope
   - Use application_id, agent_id, and user_id to share memories across
     all operations/sessions.

2) Hybrid vector search
   - Use a custom OpenAI vectorizer with the provider for hybrid vector search.
     Demonstrates combining full-text and semantic search for richer context
     retrieval.

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

from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from agent_framework.redis import RedisContextProvider
from azure.identity import AzureCliCredential
from dotenv import load_dotenv
from redisvl.extensions.cache.embeddings import EmbeddingsCache
from redisvl.utils.vectorize import OpenAITextVectorizer

# Load environment variables from .env file
load_dotenv()


# Default Redis URL for local Redis Stack.
# Override via the REDIS_URL environment variable for remote or authenticated instances.
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")


# Please set OPENAI_API_KEY to use the OpenAI vectorizer.
# For chat responses, also set FOUNDRY_PROJECT_ENDPOINT and FOUNDRY_MODEL.
def create_chat_client() -> FoundryChatClient:
    """Create a FoundryChatClient using a Foundry project endpoint."""
    return FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["FOUNDRY_MODEL"],
        credential=AzureCliCredential(),
    )


async def example_global_memory_scope() -> None:
    """Example 1: Global memory scope (memories shared across all operations)."""
    print("1. Global Memory Scope Example:")
    print("-" * 40)

    client = create_chat_client()

    provider = RedisContextProvider(
        source_id="redis_context",
        redis_url=REDIS_URL,
        index_name="redis_threads_global",
        application_id="threads_demo_app",
        agent_id="threads_demo_agent",
        user_id="threads_demo_user",
    )

    agent = Agent(
        client=client,
        name="GlobalMemoryAssistant",
        instructions=(
            "You are a helpful assistant. Personalize replies using provided context. "
            "Before answering, always check for stored context containing information"
        ),
        tools=[],
        context_providers=[provider],
    )

    # Store a preference in the global scope
    query = "Remember that I prefer technical responses with code examples when discussing programming."
    print(f"User: {query}")
    result = await agent.run(query)
    print(f"Agent: {result}\n")

    # Create a new session - memories should still be accessible due to global scope
    new_session = agent.create_session()
    query = "What technical responses do I prefer?"
    print(f"User (new session): {query}")
    result = await agent.run(query, session=new_session)
    print(f"Agent: {result}\n")

    # Clean up the Redis index
    await provider.redis_index.delete()


async def example_hybrid_vector_search() -> None:
    """Example 2: Hybrid vector search with custom vectorizer.

    Demonstrates using a custom OpenAI vectorizer for hybrid vector search,
    combining full-text and semantic search for richer context retrieval.
    """
    print("2. Hybrid Vector Search Example:")
    print("-" * 40)

    client = create_chat_client()

    vectorizer = OpenAITextVectorizer(
        model="text-embedding-ada-002",
        api_config={"api_key": os.getenv("OPENAI_API_KEY")},
        cache=EmbeddingsCache(name="openai_embeddings_cache", redis_url=REDIS_URL),
    )

    provider = RedisContextProvider(
        source_id="redis_context",
        redis_url=REDIS_URL,
        index_name="redis_threads_dynamic",
        application_id="threads_demo_app",
        agent_id="threads_demo_agent",
        user_id="threads_demo_user",
        redis_vectorizer=vectorizer,
        vector_field_name="vector",
        vector_algorithm="hnsw",
        vector_distance_metric="cosine",
    )

    agent = Agent(
        client=client,
        name="HybridSearchAssistant",
        instructions="You are an assistant with hybrid vector search for richer context retrieval.",
        context_providers=[provider],
    )

    # Store some information
    query = "Remember that for this conversation, I'm working on a Python project about data analysis."
    print(f"User: {query}")
    result = await agent.run(query)
    print(f"Agent: {result}\n")

    # Test memory retrieval via hybrid search
    query = "What project am I working on?"
    print(f"User: {query}")
    result = await agent.run(query)
    print(f"Agent: {result}\n")

    # Store more information
    query = "Also remember that I prefer using pandas and matplotlib for this project."
    print(f"User: {query}")
    result = await agent.run(query)
    print(f"Agent: {result}\n")

    # Test comprehensive memory retrieval
    query = "What do you know about my current project and preferences?"
    print(f"User: {query}")
    result = await agent.run(query)
    print(f"Agent: {result}\n")

    # Clean up the Redis index
    await provider.redis_index.delete()


async def example_multiple_agents() -> None:
    """Example 3: Multiple agents with different memory configurations (isolated via agent_id) but within 1 index."""
    print("3. Multiple Agents with Different Memory Configurations:")
    print("-" * 40)

    client = create_chat_client()

    vectorizer = OpenAITextVectorizer(
        model="text-embedding-ada-002",
        api_config={"api_key": os.getenv("OPENAI_API_KEY")},
        cache=EmbeddingsCache(name="openai_embeddings_cache", redis_url=REDIS_URL),
    )

    personal_provider = RedisContextProvider(
        source_id="redis_context",
        redis_url=REDIS_URL,
        index_name="redis_threads_agents",
        application_id="threads_demo_app",
        agent_id="agent_personal",
        user_id="threads_demo_user",
        redis_vectorizer=vectorizer,
        vector_field_name="vector",
        vector_algorithm="hnsw",
        vector_distance_metric="cosine",
    )

    personal_agent = Agent(
        client=client,
        name="PersonalAssistant",
        instructions="You are a personal assistant that helps with personal tasks.",
        context_providers=[personal_provider],
    )

    work_provider = RedisContextProvider(
        source_id="redis_context",
        redis_url=REDIS_URL,
        index_name="redis_threads_agents",
        application_id="threads_demo_app",
        agent_id="agent_work",
        user_id="threads_demo_user",
        redis_vectorizer=vectorizer,
        vector_field_name="vector",
        vector_algorithm="hnsw",
        vector_distance_metric="cosine",
    )

    work_agent = Agent(
        client=client,
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
    await example_global_memory_scope()
    await example_hybrid_vector_search()
    await example_multiple_agents()


if __name__ == "__main__":
    asyncio.run(main())
