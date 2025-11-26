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
1. An Azure AI Search service with a search index
2. An Azure AI Foundry project with a model deployment
3. An Azure OpenAI resource (for Knowledge Base model calls)
4. Set the following environment variables:
   - AZURE_SEARCH_ENDPOINT: Your Azure AI Search endpoint
   - AZURE_SEARCH_API_KEY: (Optional) Your search API key - if not provided, uses DefaultAzureCredential for Entra ID
   - AZURE_SEARCH_INDEX_NAME: Your search index name
   - AZURE_AI_PROJECT_ENDPOINT: Your Azure AI Foundry project endpoint
   - AZURE_AI_MODEL_DEPLOYMENT_NAME: Your model deployment name (e.g., "gpt-4o")
   - AZURE_SEARCH_KNOWLEDGE_BASE_NAME: Your Knowledge Base name
   - AZURE_OPENAI_RESOURCE_URL: Your Azure OpenAI resource URL (e.g., "https://myresource.openai.azure.com")
     Note: This is different from AZURE_AI_PROJECT_ENDPOINT - Knowledge Base needs the OpenAI endpoint for model calls
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
    index_name = os.environ["AZURE_SEARCH_INDEX_NAME"]
    project_endpoint = os.environ["AZURE_AI_PROJECT_ENDPOINT"]
    model_deployment = os.environ.get("AZURE_AI_MODEL_DEPLOYMENT_NAME", "gpt-4o")
    knowledge_base_name = os.environ["AZURE_SEARCH_KNOWLEDGE_BASE_NAME"]
    azure_openai_resource_url = os.environ["AZURE_OPENAI_RESOURCE_URL"]

    # Create Azure AI Search context provider with agentic mode (recommended for accuracy)
    print("Using AGENTIC mode (Knowledge Bases with query planning, recommended)\n")
    print("ℹ️  This mode is slightly slower but provides more accurate results.\n")
    search_provider = AzureAISearchContextProvider(
        endpoint=search_endpoint,
        index_name=index_name,
        api_key=search_key,  # Use api_key for API key auth, or credential for managed identity
        credential=AzureCliCredential() if not search_key else None,
        mode="agentic",  # Advanced mode for multi-hop reasoning
        # Agentic mode configuration
        azure_ai_project_endpoint=project_endpoint,
        azure_openai_resource_url=azure_openai_resource_url,
        model_deployment_name=model_deployment,
        knowledge_base_name=knowledge_base_name,
        # Optional: Configure retrieval behavior
        knowledge_base_output_mode="extractive_data",  # or "answer_synthesis"
        retrieval_reasoning_effort="minimal",  # or "medium", "low"
        top_k=3,  # Note: In agentic mode, the server-side Knowledge Base determines final retrieval
    )

    # Create agent with search context provider
    async with (
        search_provider,
        AzureAIAgentClient(
            project_endpoint=project_endpoint,
            model_deployment_name=model_deployment,
            async_credential=AzureCliCredential(),
        ) as client,
        ChatAgent(
            chat_client=client,
            name="SearchAgent",
            instructions=(
                "You are a helpful assistant with advanced reasoning capabilities. "
                "Use the provided context from the knowledge base to answer complex "
                "questions that may require synthesizing information from multiple sources."
            ),
            context_providers=[search_provider],
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
