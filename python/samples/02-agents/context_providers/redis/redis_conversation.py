# Copyright (c) Microsoft. All rights reserved.

"""Redis Context Provider: Basic usage and agent integration

This example demonstrates how to use the Redis context provider to persist
conversational details. Pass it as a constructor argument to create_agent.

Note: For session history persistence, see RedisHistoryProvider in the
conversations/redis_history_provider.py sample. RedisContextProvider is for
AI context (RAG, memories), while RedisHistoryProvider stores message history.

Requirements:
  - A Redis instance with RediSearch enabled (e.g., Redis Stack)
  - agent-framework with the Redis extra installed: pip install "agent-framework-redis"
  - Optionally an OpenAI API key if enabling embeddings for hybrid search

Run:
  python redis_conversation.py
"""

import asyncio
import os

from agent_framework.azure import AzureOpenAIResponsesClient
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


async def main() -> None:
    """Walk through provider and chat message store usage.

    Helpful debugging (uncomment when iterating):
      - print(await provider.redis_index.info())
      - print(await provider.search_all())
    """
    vectorizer = OpenAITextVectorizer(
        model="text-embedding-ada-002",
        api_config={"api_key": os.getenv("OPENAI_API_KEY")},
        cache=EmbeddingsCache(name="openai_embeddings_cache", redis_url=REDIS_URL),
    )

    provider = RedisContextProvider(
        source_id="redis_context",
        redis_url=REDIS_URL,
        index_name="redis_conversation",
        prefix="redis_conversation",
        application_id="matrix_of_kermits",
        agent_id="agent_kermit",
        user_id="kermit",
        redis_vectorizer=vectorizer,
        vector_field_name="vector",
        vector_algorithm="hnsw",
        vector_distance_metric="cosine",
    )

    # Create chat client for the agent
    client = AzureOpenAIResponsesClient(
        project_endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
        deployment_name=os.environ["AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME"],
        credential=AzureCliCredential(),
    )
    # Create agent wired to the Redis context provider. The provider automatically
    # persists conversational details and surfaces relevant context on each turn.
    agent = client.as_agent(
        name="MemoryEnhancedAssistant",
        instructions=(
            "You are a helpful assistant. Personalize replies using provided context. "
            "Before answering, always check for stored context"
        ),
        tools=[],
        context_providers=[provider],
    )

    # Create a session to manage conversation state
    session = agent.create_session()

    # Teach a user preference; the agent writes this to the provider's memory
    query = "Remember that I enjoy gumbo"
    result = await agent.run(query, session=session)
    print("User: ", query)
    print("Agent: ", result)

    # Ask the agent to recall the stored preference; it should retrieve from memory
    query = "What do I enjoy?"
    result = await agent.run(query, session=session)
    print("User: ", query)
    print("Agent: ", result)

    query = "What did I say to you just now?"
    result = await agent.run(query, session=session)
    print("User: ", query)
    print("Agent: ", result)

    query = "Remember that I have a meeting at 3pm tomorro"
    result = await agent.run(query, session=session)
    print("User: ", query)
    print("Agent: ", result)

    query = "Tulips are red"
    result = await agent.run(query, session=session)
    print("User: ", query)
    print("Agent: ", result)

    query = "What was the first thing I said to you this conversation?"
    result = await agent.run(query, session=session)
    print("User: ", query)
    print("Agent: ", result)
    # Drop / delete the provider index in Redis
    await provider.redis_index.delete()


if __name__ == "__main__":
    asyncio.run(main())
