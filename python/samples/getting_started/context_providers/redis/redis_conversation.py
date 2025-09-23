# Copyright (c) Microsoft. All rights reserved.

"""Redis Context Provider: Basic usage and agent integration

This example demonstrates how to use the Redis ChatMessageStore to persist
conversational details. Pass it as a constructor argument to create_agent.

Requirements:
  - A Redis instance with RediSearch enabled (e.g., Redis Stack)
  - agent-framework with the Redis extra installed: pip install "agent-framework[redis]"
  - Optionally an OpenAI API key if enabling embeddings for hybrid search

Run:
  python redis_conversation.py
"""

import os
import asyncio

from agent_framework_redis._provider import RedisProvider
from agent_framework_redis._chat_message_store import RedisChatMessageStore
from agent_framework.openai import OpenAIChatClient
from redisvl.utils.vectorize import OpenAITextVectorizer
from redisvl.extensions.cache.embeddings import EmbeddingsCache



async def main() -> None:
    """Walk through provider and chat message store usage.

    Helpful debugging (uncomment when iterating):
      - print(await provider.redis_index.info())
      - print(await provider.search_all())
    """
    vectorizer = OpenAITextVectorizer(
        model="text-embedding-ada-002",
        api_config={"api_key": os.getenv("OPENAI_API_KEY")},
        cache=EmbeddingsCache(name="openai_embeddings_cache", redis_url="redis://localhost:6379"),
    )

    thread_id = "test_thread"

    provider = RedisProvider(
        redis_url="redis://localhost:6379",
        index_name="redis_conversation",
        prefix="redis_conversation",
        application_id="matrix_of_kermits",
        agent_id="agent_kermit",
        user_id="kermit",
        redis_vectorizer=vectorizer,
        vector_field_name="vector",
        vector_algorithm="hnsw",
        vector_distance_metric="cosine",
        thread_id=thread_id,
    )
    chat_message_store_factory = lambda: RedisChatMessageStore(
        redis_url="redis://localhost:6379",
        thread_id=thread_id,
        key_prefix="chat_messages",
        max_messages=100,
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
            context_providers=provider,
            chat_message_store_factory=chat_message_store_factory,
        )

    # Teach a user preference; the agent writes this to the provider's memory
    query = "Remember that I enjoy gumbo"
    result = await agent.run(query)
    print("User: ", query)
    print("Agent: ", result)

    # Ask the agent to recall the stored preference; it should retrieve from memory
    query = "What do I enjoy?"
    result = await agent.run(query)
    print("User: ", query)
    print("Agent: ", result)

    query = "What did I say to you just now?"
    result = await agent.run(query)
    print("User: ", query)
    print("Agent: ", result)

    query = "Remember that anyone who does not clean shrimp will be eaten by a shark"
    result = await agent.run(query)
    print("User: ", query)
    print("Agent: ", result)

    query = "Tulips are red"
    result = await agent.run(query)
    print("User: ", query)
    print("Agent: ", result)

    query = "What was the first thing I said to you this conversation?"
    result = await agent.run(query)
    print("User: ", query)
    print("Agent: ", result)
    # Drop / delete the provider index in Redis
    await provider.redis_index.delete()

if __name__ == "__main__":
    asyncio.run(main())
