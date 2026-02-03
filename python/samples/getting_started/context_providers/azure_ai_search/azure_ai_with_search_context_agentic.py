# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os

from agent_framework import ChatAgent
from agent_framework.azure import AzureAIAgentClient, AzureAISearchContextProvider
from azure.identity.aio import AzureCliCredential
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

"""
This sample demonstrates how to use Azure AI Search with agentic mode for RAG
(Retrieval Augmented Generation) with Azure AI agents.

**Agentic mode** is recommended for most scenarios:
- Uses Knowledge Bases in Azure AI Search for query planning
- Performs multi-hop reasoning across documents
- Provides more accurate results through intelligent retrieval
- Slightly slower with more token consumption for query planning
- See: https://techcommunity.microsoft.com/blog/azure-ai-foundry-blog/foundry-iq-boost-response-relevance-by-36-with-agentic-retrieval/4470720

For simple queries where speed is critical, use semantic mode instead (see azure_ai_with_search_context_semantic.py).

Prerequisites:
1. An Azure AI Search service
2. An Azure AI Foundry project with a model deployment
3. Either an existing Knowledge Base OR a search index (to auto-create a KB)

Environment variables:
   - AZURE_SEARCH_ENDPOINT: Your Azure AI Search endpoint
   - AZURE_SEARCH_API_KEY: (Optional) API key - if not provided, uses DefaultAzureCredential
   - AZURE_AI_PROJECT_ENDPOINT: Your Azure AI Foundry project endpoint
   - AZURE_AI_MODEL_DEPLOYMENT_NAME: Your model deployment name (e.g., "gpt-4o")

For using an existing Knowledge Base (recommended):
   - AZURE_SEARCH_KNOWLEDGE_BASE_NAME: Your Knowledge Base name

For auto-creating a Knowledge Base from an index:
   - AZURE_SEARCH_INDEX_NAME: Your search index name
   - AZURE_OPENAI_RESOURCE_URL: Azure OpenAI resource URL (e.g., "https://myresource.openai.azure.com")
"""

# Sample queries to demonstrate agentic RAG
USER_INPUTS = [
    "What information is available in the knowledge base?",
    "Analyze and compare the main topics from different documents",
    "What connections can you find across different sections?",
]


async def main() -> None:
    """Main function demonstrating Azure AI Search agentic mode."""

    # Get configuration from environment
    search_endpoint = os.environ["AZURE_SEARCH_ENDPOINT"]
    search_key = os.environ.get("AZURE_SEARCH_API_KEY")
    project_endpoint = os.environ["AZURE_AI_PROJECT_ENDPOINT"]
    model_deployment = os.environ.get("AZURE_AI_MODEL_DEPLOYMENT_NAME", "gpt-4o")

    # Agentic mode requires exactly ONE of: knowledge_base_name OR index_name
    # Option 1: Use existing Knowledge Base (recommended)
    knowledge_base_name = os.environ.get("AZURE_SEARCH_KNOWLEDGE_BASE_NAME")
    # Option 2: Auto-create KB from index (requires azure_openai_resource_url)
    index_name = os.environ.get("AZURE_SEARCH_INDEX_NAME")
    azure_openai_resource_url = os.environ.get("AZURE_OPENAI_RESOURCE_URL")

    # Create Azure AI Search context provider with agentic mode (recommended for accuracy)
    print("Using AGENTIC mode (Knowledge Bases with query planning, recommended)\n")
    print("This mode is slightly slower but provides more accurate results.\n")

    # Configure based on whether using existing KB or auto-creating from index
    if knowledge_base_name:
        # Use existing Knowledge Base - simplest approach
        search_provider = AzureAISearchContextProvider(
            endpoint=search_endpoint,
            api_key=search_key,
            credential=AzureCliCredential() if not search_key else None,
            mode="agentic",
            knowledge_base_name=knowledge_base_name,
            # Optional: Configure retrieval behavior
            knowledge_base_output_mode="extractive_data",  # or "answer_synthesis"
            retrieval_reasoning_effort="minimal",  # or "medium", "low"
        )
    else:
        # Auto-create Knowledge Base from index
        if not index_name:
            raise ValueError("Set AZURE_SEARCH_KNOWLEDGE_BASE_NAME or AZURE_SEARCH_INDEX_NAME")
        if not azure_openai_resource_url:
            raise ValueError("AZURE_OPENAI_RESOURCE_URL required when using index_name")
        search_provider = AzureAISearchContextProvider(
            endpoint=search_endpoint,
            index_name=index_name,
            api_key=search_key,
            credential=AzureCliCredential() if not search_key else None,
            mode="agentic",
            azure_openai_resource_url=azure_openai_resource_url,
            model_deployment_name=model_deployment,
            # Optional: Configure retrieval behavior
            knowledge_base_output_mode="extractive_data",  # or "answer_synthesis"
            retrieval_reasoning_effort="minimal",  # or "medium", "low"
            top_k=3,
        )

    # Create agent with search context provider
    async with (
        search_provider,
        AzureAIAgentClient(
            project_endpoint=project_endpoint,
            model_deployment_name=model_deployment,
            credential=AzureCliCredential(),
        ) as client,
        ChatAgent(
            chat_client=client,
            name="SearchAgent",
            instructions=(
                "You are a helpful assistant with advanced reasoning capabilities. "
                "Use the provided context from the knowledge base to answer complex "
                "questions that may require synthesizing information from multiple sources."
            ),
            context_provider=search_provider,
        ) as agent,
    ):
        print("=== Azure AI Agent with Search Context (Agentic Mode) ===\n")

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
