# Copyright (c) Microsoft. All rights reserved.

"""Redis Context Provider: Thread scoping examples

This sample demonstrates how conversational memory can be scoped when using the
Redis context provider. It covers three scenarios:

1) Global thread scope
   - Provide a fixed thread_id to share memories across operations/threads.

2) Per-operation thread scope
   - Enable scope_to_per_operation_thread_id to bind the provider to a single
     thread for the lifetime of that provider instance. Use the same thread
     object for reads/writes with that provider.

3) Multiple agents with isolated memory
   - Use different agent_id values to keep memories separated for different
     agent personas, even when the user_id is the same.

Requirements:
  - A Redis instance with RediSearch enabled (e.g., Redis Stack)
  - agent-framework with the Redis extra installed: pip install "agent-framework-redis"
  - Optionally an OpenAI API key for the chat client in this demo

Run:
  python redis_threads.py
"""

import asyncio
import os

from agent_framework.azure import AzureOpenAIResponsesClient
from agent_framework.redis import RedisContextProvider
from azure.identity import AzureCliCredential
from redisvl.extensions.cache.embeddings import EmbeddingsCache
from redisvl.utils.vectorize import OpenAITextVectorizer

# Default Redis URL for local Redis Stack.
# Override via the REDIS_URL environment variable for remote or authenticated instances.
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

# Please set OPENAI_API_KEY to use the OpenAI vectorizer.
# For chat responses, also set AZURE_AI_PROJECT_ENDPOINT and AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME.


def create_chat_client() -> AzureOpenAIResponsesClient:
    """Create an Azure OpenAI Responses client using a Foundry project endpoint."""
    return AzureOpenAIResponsesClient(
        project_endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
        deployment_name=os.environ["AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME"],
        credential=AzureCliCredential(),
    )


async def example_global_thread_scope() -> None:
    """Example 1: Global thread_id scope (memories shared across all operations)."""
    print("1. Global Thread Scope Example:")
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

    agent = client.as_agent(
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


async def example_per_operation_thread_scope() -> None:
    """Example 2: Per-operation thread scope (memories isolated per session).

    Note: When scope_to_per_operation_thread_id=True, the provider is bound to a single session
    throughout its lifetime. Use the same session object for all operations with that provider.
    """
    print("2. Per-Operation Thread Scope Example:")
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

    agent = client.as_agent(
        name="ScopedMemoryAssistant",
        instructions="You are an assistant with thread-scoped memory.",
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
    """Example 3: Multiple agents with different thread configurations (isolated via agent_id) but within 1 index."""
    print("3. Multiple Agents with Different Thread Configurations:")
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

    personal_agent = client.as_agent(
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
    print("=== Redis Thread Scoping Examples ===\n")
    await example_global_thread_scope()
    await example_per_operation_thread_scope()
    await example_multiple_agents()


if __name__ == "__main__":
    asyncio.run(main())
