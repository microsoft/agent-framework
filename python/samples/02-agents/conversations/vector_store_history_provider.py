# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework import Agent, InMemoryStore, SlidingWindowStrategy, VectorStoreHistoryProvider
from agent_framework.openai import OpenAIChatClient, OpenAIEmbeddingClient
from dotenv import load_dotenv

load_dotenv()

"""
This sample demonstrates a vector-store-backed conversation history provider.

The provider owns its history collection and data model. It stores the full
conversation, loads a compacted window into each model invocation, and exposes
a search tool over the full transcript. Every storage and search operation is
scoped to the application, tenant, agent, provider source, and current session.

Set `OPENAI_API_KEY` before running this sample.
"""


async def main() -> None:
    """Run a compacted conversation backed by an in-memory vector store."""
    # 1. The history provider takes a store rather than a collection because it
    #    owns the history record model and collection definition.
    history = VectorStoreHistoryProvider(
        InMemoryStore(),
        application_id="release-planning",
        tenant_id="contoso",
        agent_id="release-assistant",
        collection_name="release_planning_history_text_embedding_3_small",
        contents_format="json",
        embedding_generator=OpenAIEmbeddingClient(
            model="text-embedding-3-small",
        ),
        embedding_options={
            "dimensions": 1536,
            "encoding_format": "float",
        },
        compaction_strategy=SlidingWindowStrategy(
            keep_last_groups=2,
            preserve_system=True,
        ),
        include_search_tool=True,
    )

    # 2. Only the compacted projection is loaded into the model context. The
    #    provider-owned search tool can still retrieve older scoped messages.
    async with Agent(
        client=OpenAIChatClient(model="gpt-5.4-nano"),
        name="ReleaseAssistant",
        instructions=(
            "Help with release planning. Use the history search tool when an "
            "older detail is not present in the loaded conversation."
        ),
        context_providers=[history],
    ) as agent:
        session = agent.create_session()

        for prompt in (
            "Remember that the deployment region is westus3.",
            "Remember that the release ring is canary.",
            "Remember that the rollback owner is Mira.",
            "Remember that release alerts go to the operations channel.",
            "Which deployment region did I choose? Search the full history if needed.",
        ):
            response = await agent.run(prompt, session=session)
            print(f"User: {prompt}")
            print(f"Assistant: {response.text}\n")


if __name__ == "__main__":
    asyncio.run(main())


"""
Sample output:
User: Which deployment region did I choose? Search the full history if needed.
Assistant: You chose westus3 as the deployment region.
"""
