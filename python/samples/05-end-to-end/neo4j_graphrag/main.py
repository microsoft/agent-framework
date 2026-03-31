# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "agent-framework-foundry",
#     "agent-framework-neo4j",
# ]
# ///

# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os

from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from agent_framework_neo4j import Neo4jContextProvider, Neo4jSettings
from azure.identity.aio import AzureCliCredential
from dotenv import load_dotenv

load_dotenv()

"""
This sample demonstrates how to use the Neo4j GraphRAG context provider with
Agent Framework and Azure AI Foundry.

Environment variables:
    FOUNDRY_PROJECT_ENDPOINT — Azure AI Foundry project endpoint
    FOUNDRY_MODEL            — Model deployment name (e.g. gpt-4o)
    NEO4J_URI              — Neo4j connection URI
    NEO4J_USERNAME         — Neo4j username
    NEO4J_PASSWORD         — Neo4j password
    NEO4J_FULLTEXT_INDEX_NAME — Optional fulltext index name (defaults to search_chunks)
"""

USER_INPUTS = [
    "What products does Microsoft offer?",
    "What risks does Apple face?",
    "Tell me about NVIDIA's AI business and risk factors.",
]

# Optional graph-enrichment query: retrieval works without this, but supplying
# a query lets the sample attach related company, product, and risk metadata to
# each retrieved chunk.
RETRIEVAL_QUERY = """
MATCH (node)-[:FROM_DOCUMENT]->(doc:Document)<-[:FILED]-(company:Company)
OPTIONAL MATCH (company)-[:FACES_RISK]->(risk:RiskFactor)
WITH node, score, company, doc, collect(DISTINCT risk.name)[0..5] AS risks
OPTIONAL MATCH (company)-[:MENTIONS]->(product:Product)
WITH node, score, company, doc, risks, collect(DISTINCT product.name)[0..5] AS products
RETURN
    node.text AS text,
    score,
    company.name AS company,
    company.ticker AS ticker,
    doc.title AS title,
    risks,
    products
ORDER BY score DESC
"""


async def main() -> None:
    # 1. Load and validate the Neo4j connection settings.
    settings = Neo4jSettings()
    if not settings.is_configured:
        raise RuntimeError("Set NEO4J_URI, NEO4J_USERNAME, and NEO4J_PASSWORD before running this sample.")

    # 2. Read the Azure AI Foundry project endpoint and model configuration.
    project_endpoint = os.environ.get("FOUNDRY_PROJECT_ENDPOINT")
    if not project_endpoint:
        raise RuntimeError("Set FOUNDRY_PROJECT_ENDPOINT before running this sample.")

    model = os.environ.get("FOUNDRY_MODEL") or "gpt-4o"

    # 3. Create the Neo4j context provider and Foundry-backed agent, then ask sample questions.
    async with (
        AzureCliCredential() as credential,
        Neo4jContextProvider(
            source_id="neo4j_graphrag",
            uri=settings.uri,
            username=settings.username,
            password=settings.get_password(),
            index_name=settings.fulltext_index_name,
            index_type="fulltext",
            retrieval_query=RETRIEVAL_QUERY,
            top_k=5,
        ) as provider,
        Agent(
            client=FoundryChatClient(
                project_endpoint=project_endpoint,
                model=model,
                credential=credential,
            ),
            name="Neo4jGraphRAGAgent",
            instructions=(
                "You are a helpful assistant. Use the Neo4j context provider results to answer accurately. "
                "If the retrieved context is insufficient, say so plainly."
            ),
            context_providers=[provider],
        ) as agent,
    ):
        session = agent.create_session()
        print("=== Neo4j GraphRAG Context Provider ===\n")

        for user_input in USER_INPUTS:
            print(f"User: {user_input}")
            result = await agent.run(user_input, session=session)
            print(f"Agent: {getattr(result, 'text', result)}\n")


if __name__ == "__main__":
    asyncio.run(main())
