# Copyright (c) Microsoft. All rights reserved.

"""Redis Context Provider: Basic usage and agent integration

This example demonstrates how to use the Redis context provider to persist and
retrieve conversational memory for agents. It covers three progressively more
realistic scenarios:

1) Standalone provider usage ("basic cache")
   - Write messages to Redis and retrieve relevant context using full-text or
     hybrid vector search.

2) Agent + provider
   - Connect the provider to an agent so the agent can store user preferences
     and recall them across turns.

3) Agent + provider + tool memory
   - Expose a simple tool to the agent, then verify that details from the tool
     outputs are captured and retrievable as part of the agent's memory.

Requirements:
  - A Redis instance with RediSearch enabled (e.g., Redis Stack)
  - agent-framework with the Redis extra installed: pip install "agent-framework[redis]"
  - Optionally an OpenAI API key if enabling embeddings for hybrid search

Run:
  python redis_basics.py
"""

import os
import asyncio

from agent_framework import ChatMessage, Role
from agent_framework_redis._provider import RedisProvider
from agent_framework.openai import OpenAIChatClient
from redisvl.utils.vectorize import OpenAITextVectorizer
from redisvl.extensions.cache.embeddings import EmbeddingsCache


def search_flights(
    origin_airport_code: str,
    destination_airport_code: str,
    detailed: bool = False
) -> str:
    """Simulated flight-search tool to demonstrate tool memory.

    The agent can call this function, and the returned details can be stored
    by the Redis context provider. We later ask the agent to recall facts from
    these tool results to verify memory is working as expected.
    """
    # Minimal static catalog used to simulate a tool's structured output
    flights = {
        ("JFK", "LAX"): {"airline": "SkyJet", "duration": "6h 15m", "price": 325, "cabin": "Economy", "baggage": "1 checked bag"},
        ("SFO", "SEA"): {"airline": "Pacific Air", "duration": "2h 5m", "price": 129, "cabin": "Economy", "baggage": "Carry-on only"},
        ("LHR", "DXB"): {"airline": "EuroWings", "duration": "6h 50m", "price": 499, "cabin": "Business", "baggage": "2 bags included"},
    }

    route = (origin_airport_code.upper(), destination_airport_code.upper())
    if route not in flights:
        return f"No flights found between {origin_airport_code} and {destination_airport_code}"

    flight = flights[route]
    if not detailed:
        return f"Flights available from {origin_airport_code} to {destination_airport_code}."

    return (
        f"{flight['airline']} operates flights from {origin_airport_code} to {destination_airport_code}. "
        f"Duration: {flight['duration']}. "
        f"Price: ${flight['price']}. "
        f"Cabin: {flight['cabin']}. "
        f"Baggage policy: {flight['baggage']}."
    )


async def main() -> None:
    """Walk through provider-only, agent integration, and tool-memory scenarios.

    Helpful debugging (uncomment when iterating):
      - print(await provider.redis_index.info())
      - print(await provider.search_all())
    """

    print("1. Standalone provider usage:")
    print("-" * 40)
    # Create a provider with partition scope and OpenAI embeddings

    # Please set the OPENAI_API_KEY and OPENAI_CHAT_MODEL_ID environment variables to use the OpenAI vectorizer
    # Recommend default for OPENAI_CHAT_MODEL_ID is gpt-4o-mini

    # We attach an embedding vectorizer so the provider can perform hybrid (text + vector)
    # retrieval. If you prefer text-only retrieval, instantiate RedisProvider without the
    # 'vectorizer' and vector_* parameters.
    vectorizer = OpenAITextVectorizer(
        model="text-embedding-ada-002",
        api_config={"api_key": os.getenv("OPENAI_API_KEY")},
        cache=EmbeddingsCache(name="openai_embeddings_cache", redis_url="redis://localhost:6379"),
    )
    # The provider manages persistence and retrieval. application_id/agent_id/user_id
    # scope data for multi-tenant separation; thread_id (set later) narrows to a
    # specific conversation. 
    provider = RedisProvider(
        redis_url="redis://localhost:6379",
        index_name="redis_basics",
        application_id="matrix_of_kermits",
        agent_id="agent_kermit",
        user_id="kermit",
        redis_vectorizer=vectorizer,
        vector_field_name="vector",
        vector_algorithm="hnsw",
        vector_distance_metric="cosine",
    )
    
    # Build sample chat messages to persist to Redis
    messages = [
        ChatMessage(role=Role.USER, text="runA CONVO: User Message"),
        ChatMessage(role=Role.ASSISTANT, text="runA CONVO: Assistant Message"),
        ChatMessage(role=Role.SYSTEM, text="runA CONVO: System Message"),
    ]

    # Declare/start a conversation/thread and write messages under 'runA'.
    # Threads are logical boundaries used by the provider to group and retrieve
    # conversation-specific context.
    await provider.thread_created(thread_id="runA")
    await provider.messages_adding(thread_id="runA", new_messages=messages)

    # Retrieve relevant memories for a hypothetical model call. The provider uses
    # the current request messages as the retrieval query and returns context to
    # be injected into the model's instructions.
    ctx = await provider.model_invoking([
        ChatMessage(role=Role.SYSTEM, text="B: Assistant Message")
    ])

    # Inspect retrieved memories that would be injected into instructions
    # (Debug-only output so you can verify retrieval works as expected.)
    print("Model Invoking Result:")
    print(ctx)

    # Drop / delete the provider index in Redis
    await provider.redis_index.delete()

    # --- Agent + provider: teach and recall a preference ---

    print("\n2. Agent + provider: teach and recall a preference")
    print("-" * 40)
    # Fresh provider for the agent demo (recreates index)
    vectorizer = OpenAITextVectorizer(
        model="text-embedding-ada-002",
        api_config={"api_key": os.getenv("OPENAI_API_KEY")},
        cache=EmbeddingsCache(name="openai_embeddings_cache", redis_url="redis://localhost:6379"),
    )
    # Recreate a clean index so the next scenario starts fresh
    provider = RedisProvider(
        redis_url="redis://localhost:6379",
        index_name="redis_basics_2",
        prefix="context_2",
        application_id="matrix_of_kermits",
        agent_id="agent_kermit",
        user_id="kermit",
        redis_vectorizer=vectorizer,
        vector_field_name="vector",
        vector_algorithm="hnsw",
        vector_distance_metric="cosine",
    )

    # Create chat client for the agent
    client = OpenAIChatClient(ai_model_id=os.getenv("OPENAI_CHAT_MODEL_ID"), api_key=os.getenv("OPENAI_API_KEY"))
    # Create agent wired to the Redis context provider. The provider automatically
    # persists conversational details and surfaces relevant context on each turn.
    agent = client.create_agent(
            name="MemoryEnhancedAssistant",
            instructions=(
                "You are a helpful assistant. Personalize replies using provided context. "
                "Before answering, always check for stored context"
            ),
            tools=[],
            context_providers=provider)

    # Teach a user preference; the agent writes this to the provider's memory
    query = "Remember that I enjoy glugenflorgle"
    result = await agent.run(query)
    print("User: ", query)
    print("Agent: ", result)

    # Ask the agent to recall the stored preference; it should retrieve from memory
    query = "What do I enjoy?"
    result = await agent.run(query)
    print("User: ", query)
    print("Agent: ", result)

    # Drop / delete the provider index in Redis
    await provider.redis_index.delete()

    # --- Agent + provider + tool: store and recall tool-derived context ---

    print("\n3. Agent + provider + tool: store and recall tool-derived context")
    print("-" * 40)
    # Text-only provider (full-text search only). Omits vectorizer and related params.
    provider = RedisProvider(
        redis_url="redis://localhost:6379",
        index_name="redis_basics_3",
        prefix="context_3",
        application_id="matrix_of_kermits",
        agent_id="agent_kermit",
        user_id="kermit"
    )

    # Create agent exposing the flight search tool. Tool outputs are captured by the
    # provider and become retrievable context for later turns.
    client = OpenAIChatClient(ai_model_id=os.getenv("OPENAI_CHAT_MODEL_ID"), api_key=os.getenv("OPENAI_API_KEY"))
    agent = client.create_agent(
            name="MemoryEnhancedAssistant",
            instructions=(
                "You are a helpful assistant. Personalize replies using provided context. "
                "Before answering, always check for stored context"
            ),
            tools=search_flights,
            context_providers=provider)
    # Invoke the tool; outputs become part of memory/context
    query = "Are there any flights from new york city (jfk) to la? Give me details"
    result = await agent.run(query)
    print("User: ", query)
    print("Agent: ", result)
    # Verify the agent can recall tool-derived context
    query = "Which flight did I ask about?"
    result = await agent.run(query)
    print("User: ", query)
    print("Agent: ", result)

    # Drop / delete the provider index in Redis
    await provider.redis_index.delete()

if __name__ == "__main__":
    asyncio.run(main())
