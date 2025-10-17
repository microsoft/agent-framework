# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os

from agent_framework import ChatAgent
from agent_framework_azure_ai import AzureAIAgentClient, AzureAISearchContextProvider
from azure.core.credentials import AzureKeyCredential
from azure.identity.aio import DefaultAzureCredential

"""
The following sample demonstrates how to use Azure AI Search as a context provider
for RAG (Retrieval Augmented Generation) with Azure AI agents.

AzureAISearchContextProvider supports two modes:

1. **Semantic mode** (default, recommended):
   - Fast hybrid search combining vector and keyword search
   - Uses semantic ranking for improved relevance
   - Returns raw search results as context
   - Best for most RAG use cases

2. **Agentic mode** (slower, advanced):
   - Uses Knowledge Bases in Azure AI Search
   - Performs multi-hop reasoning across documents
   - Uses an LLM to synthesize answers
   - Best for complex queries requiring cross-document reasoning
   - Significantly slower (order of magnitude)

Prerequisites:
1. An Azure AI Search service with a search index
2. An Azure AI Foundry project
3. Set the following environment variables:

   For both modes:
   - AZURE_SEARCH_ENDPOINT: Your Azure AI Search endpoint
   - AZURE_SEARCH_API_KEY: Your search API key (or use Azure AD)
   - AZURE_SEARCH_INDEX_NAME: Your search index name
   - AZURE_AI_PROJECT_ENDPOINT: Your Azure AI Foundry project endpoint

   Additional for agentic mode (Knowledge Bases):
   - USE_AGENTIC_MODE: Set to "true" to use agentic retrieval
   - AZURE_OPENAI_ENDPOINT: Your Azure OpenAI endpoint
   - AZURE_OPENAI_DEPLOYMENT_NAME: Your GPT-4 deployment name (e.g., "gpt-4o")
"""

# Sample queries to demonstrate RAG
USER_INPUTS = [
    "What information is available in the knowledge base?",
    "Summarize the main topics from the documents",
    "Find specific details about the content",
]


async def main() -> None:
    """Main function demonstrating Azure AI Search context provider."""

    # Get configuration from environment
    search_endpoint = os.environ["AZURE_SEARCH_ENDPOINT"]
    search_key = os.environ.get("AZURE_SEARCH_API_KEY")
    index_name = os.environ["AZURE_SEARCH_INDEX_NAME"]

    # Check if agentic mode is requested
    use_agentic = os.environ.get("USE_AGENTIC_MODE", "false").lower() == "true"

    # Create credential
    search_credential = AzureKeyCredential(search_key) if search_key else DefaultAzureCredential()

    # Create Azure AI Search context provider
    if use_agentic:
        # Agentic mode: Multi-hop reasoning with Knowledge Bases (slower)
        print("Using AGENTIC mode (Knowledge Bases with multi-hop reasoning, slower)\n")
        search_provider = AzureAISearchContextProvider(
            endpoint=search_endpoint,
            index_name=index_name,
            credential=search_credential,
            mode="agentic",
            azure_openai_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
            azure_openai_deployment_name=os.environ["AZURE_OPENAI_DEPLOYMENT_NAME"],
            top_k=3,
        )
    else:
        # Semantic mode: Fast hybrid search + semantic ranking (recommended)
        print("Using SEMANTIC mode (hybrid search + semantic ranking, fast)\n")
        search_provider = AzureAISearchContextProvider(
            endpoint=search_endpoint,
            index_name=index_name,
            credential=search_credential,
            mode="semantic",
            top_k=3,  # Retrieve top 3 most relevant documents
        )

    # Get Azure AI configuration
    project_endpoint = os.environ["AZURE_AI_PROJECT_ENDPOINT"]
    model_deployment = os.environ.get("AZURE_AI_MODEL_DEPLOYMENT_NAME", "gpt-4o")

    # Create agent with search context provider
    async with (
        search_provider,
        AzureAIAgentClient(
            project_endpoint=project_endpoint,
            model_deployment_name=model_deployment,
            async_credential=DefaultAzureCredential(),
        ) as client,
        ChatAgent(
            chat_client=client,
            name="SearchAgent",
            instructions=(
                "You are a helpful assistant. Use the provided context from the "
                "knowledge base to answer questions accurately."
            ),
            context_providers=[search_provider],
        ) as agent,
    ):
        print("=== Azure AI Agent with Search Context ===\n")

        for user_input in USER_INPUTS:
            print(f"User: {user_input}")
            print("Agent: ", end="", flush=True)

            # Stream response
            async for chunk in agent.run_stream(user_input):
                if chunk.text:
                    print(chunk.text, end="", flush=True)

            print("\n")


if __name__ == "__main__":
    asyncio.run(main())
