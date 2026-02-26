# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os

from agent_framework import Agent
from agent_framework.azure import AzureAIAgentClient, AzureAISearchContextProvider, AzureOpenAIEmbeddingClient
from azure.identity.aio import AzureCliCredential
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

"""
This sample demonstrates how to use Azure AI Search with semantic mode for RAG
(Retrieval Augmented Generation) with Azure AI agents.

**Semantic mode** is the recommended default mode:
- Fast hybrid search combining vector and keyword search
- Uses semantic ranking for improved relevance
- Returns raw search results as context
- Best for most RAG use cases

Prerequisites:
1. An Azure AI Search service with a search index
2. An Azure AI Foundry project with a model deployment
3. Set the following environment variables:
   - AZURE_SEARCH_ENDPOINT: Your Azure AI Search endpoint
   - AZURE_SEARCH_API_KEY: (Optional) Your search API key - if not provided, uses DefaultAzureCredential for Entra ID
   - AZURE_SEARCH_INDEX_NAME: Your search index name
   - AZURE_AI_PROJECT_ENDPOINT: Your Azure AI Foundry project endpoint
   - AZURE_AI_MODEL_DEPLOYMENT_NAME: Your model deployment name (e.g., "gpt-4o")
   - AZURE_OPENAI_EMBEDDING_MODEL_ID: (Optional) Your embedding model for hybrid search (e.g., "text-embedding-3-small")
   - AZURE_OPENAI_ENDPOINT: (Optional) Your Azure OpenAI resource URL, required if using an OpenAI embedding model for hybrid search
"""

# Sample queries to demonstrate RAG
USER_INPUTS = [
    "What information is available in the knowledge base?",
    "Summarize the main topics from the documents",
    "Find specific details about the content",
]


async def main() -> None:
    """Main function demonstrating Azure AI Search semantic mode."""

    credential = AzureCliCredential()

    # Get configuration from environment
    search_endpoint = os.environ["AZURE_SEARCH_ENDPOINT"]
    search_key = os.environ.get("AZURE_SEARCH_API_KEY")
    index_name = os.environ["AZURE_SEARCH_INDEX_NAME"]
    project_endpoint = os.environ["AZURE_AI_PROJECT_ENDPOINT"]
    model_deployment = os.environ.get("AZURE_AI_MODEL_DEPLOYMENT_NAME", "gpt-4o")
    openai_endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT")
    embedding_model = os.environ.get("AZURE_OPENAI_EMBEDDING_MODEL_ID", "text-embedding-3-small")

    embedding_client = None
    if openai_endpoint and embedding_model:
        embedding_client = AzureOpenAIEmbeddingClient(
            endpoint=openai_endpoint,
            deployment_name=embedding_model,
            credential=credential,
        )

    # Create Azure AI Search context provider with semantic mode (recommended, fast)
    print("Using SEMANTIC mode (hybrid search + semantic ranking, fast)\n")
    search_provider = AzureAISearchContextProvider(
        source_id="search_provider",
        endpoint=search_endpoint,
        index_name=index_name,
        api_key=search_key,  # Use api_key for API key auth, or credential for managed identity
        credential=credential if not search_key else None,
        mode="semantic",  # Default mode
        top_k=3,  # Retrieve top 3 most relevant documents
        embedding_function=embedding_client,  # Provide embedding function for hybrid search
        vector_field_name="DescriptionVector"
        if embedding_client
        else None,  # Set vector field for hybrid search if using embeddings
    )

    # Create agent with search context provider
    async with (
        search_provider,
        AzureAIAgentClient(
            project_endpoint=project_endpoint,
            model_deployment_name=model_deployment,
            credential=credential,
        ) as client,
        Agent(
            client=client,
            name="SearchAgent",
            instructions=(
                "You are a helpful assistant. Use the provided context from the "
                "knowledge base to answer questions accurately."
            ),
            context_providers=[search_provider],
        ) as agent,
    ):
        print("=== Azure AI Agent with Search Context (Semantic Mode) ===\n")

        for user_input in USER_INPUTS:
            print(f"User: {user_input}")
            print("Agent: ", end="", flush=True)

            # Stream response
            async for chunk in agent.run(user_input, stream=True):
                if chunk.text:
                    print(chunk.text, end="", flush=True)

            print("\n")


if __name__ == "__main__":
    asyncio.run(main())
