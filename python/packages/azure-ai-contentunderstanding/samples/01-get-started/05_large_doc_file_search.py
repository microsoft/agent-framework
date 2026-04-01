# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "agent-framework-azure-ai-contentunderstanding",
#     "agent-framework-foundry",
#     "azure-identity",
#     "openai",
# ]
# ///
# Run with: uv run packages/azure-ai-contentunderstanding/samples/01-get-started/05_large_doc_file_search.py

# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
from pathlib import Path

from agent_framework import Agent, AgentSession, Content, Message
from agent_framework.foundry import FoundryChatClient
from azure.identity import AzureCliCredential
from dotenv import load_dotenv
from openai import AsyncAzureOpenAI

from agent_framework_azure_ai_contentunderstanding import (
    ContentUnderstandingContextProvider,
    FileSearchConfig,
)

load_dotenv()

"""
Large Document + file_search RAG — CU extraction + OpenAI vector store

For large documents (100+ pages) or long audio/video, injecting the full
CU-extracted content into the LLM context is impractical. This sample shows
how to use the built-in file_search integration: CU extracts markdown and
automatically uploads it to an OpenAI vector store for token-efficient RAG.

When ``FileSearchConfig`` is provided, the provider:
  1. Extracts markdown via CU (handles scanned PDFs, audio, video)
  2. Uploads the extracted markdown to a vector store
  3. Registers a ``file_search`` tool on the agent context
  4. Cleans up the vector store on close

Architecture:
  Large PDF -> CU extracts markdown -> auto-upload to vector store -> file_search
  Follow-up -> file_search retrieves top-k chunks -> LLM answers

NOTE: Requires an async OpenAI client for vector store operations.

Environment variables:
  FOUNDRY_PROJECT_ENDPOINT                — Azure AI Foundry project endpoint
  FOUNDRY_MODEL             — Model deployment name (e.g. gpt-4.1)
  AZURE_CONTENTUNDERSTANDING_ENDPOINT      — CU endpoint URL
"""

SAMPLE_PDF_PATH = Path(__file__).resolve().parents[1] / "shared" / "sample_assets" / "invoice.pdf"


async def main() -> None:
    # 1. Set up credentials
    credential = AzureCliCredential()

    # 2. Create async OpenAI client for vector store operations
    token = credential.get_token("https://cognitiveservices.azure.com/.default").token
    openai_client = AsyncAzureOpenAI(
        azure_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        api_version="2025-03-01-preview",
        azure_ad_token=token,
    )

    # 3. Create LLM client (needed for get_file_search_tool)
    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["FOUNDRY_MODEL"],
        credential=credential,
    )

    # 4. Create vector store and file_search tool
    vector_store = await openai_client.vector_stores.create(
        name="cu_large_doc_demo",
        expires_after={"anchor": "last_active_at", "days": 1},
    )
    file_search_tool = client.get_file_search_tool(vector_store_ids=[vector_store.id])

    # 5. Configure CU provider with file_search integration
    # When file_search is set, CU-extracted markdown is automatically uploaded
    # to the vector store and the file_search tool is registered on the context.
    cu = ContentUnderstandingContextProvider(
        endpoint=os.environ["AZURE_CONTENTUNDERSTANDING_ENDPOINT"],
        credential=credential,
        analyzer_id="prebuilt-documentSearch",
        max_wait=None,  # wait until CU analysis + vector store upload finishes
        file_search=FileSearchConfig.from_foundry(
            openai_client,
            vector_store_id=vector_store.id,
            file_search_tool=file_search_tool,
        ),
    )

    pdf_bytes = SAMPLE_PDF_PATH.read_bytes()

    # The provider handles everything: CU extraction + vector store upload + file_search tool
    async with cu:
        agent = Agent(
            client=client,
            name="LargeDocAgent",
            instructions=(
                "You are a document analyst. Use the file_search tool to find "
                "relevant sections from the document and answer precisely. "
                "Cite specific sections when answering."
            ),
            context_providers=[cu],
        )

        session = AgentSession()

        # Turn 1: Upload — CU extracts and uploads to vector store automatically
        print("--- Turn 1: Upload document ---")
        response = await agent.run(
            Message(
                role="user",
                contents=[
                    Content.from_text("What are the key points in this document?"),
                    Content.from_data(
                        pdf_bytes,
                        "application/pdf",
                        additional_properties={"filename": SAMPLE_PDF_PATH.name},
                    ),
                ],
            ),
            session=session,
        )
        print(f"Agent: {response}\n")

        # Turn 2: Follow-up — file_search retrieves relevant chunks (token efficient)
        print("--- Turn 2: Follow-up (RAG) ---")
        response = await agent.run(
            "What numbers or financial metrics are mentioned?",
            session=session,
        )
        print(f"Agent: {response}\n")

    # Explicitly delete the vector store created for this sample
    await openai_client.vector_stores.delete(vector_store.id)
    await openai_client.close()
    print("Done. Vector store deleted and client closed.")


if __name__ == "__main__":
    asyncio.run(main())

"""
Sample output:

--- Turn 1: Upload document ---
Agent: An invoice from Contoso Ltd. to Microsoft Corporation (INV-100).
  Line items: Consulting Services $60, Document Fee $30, Printing Fee $10.
  Subtotal $100, Sales tax $10, Total $110, Previous balance $500, Amount due $610.

--- Turn 2: Follow-up (RAG) ---
Agent: Subtotal $100.00, Sales tax $10.00, Total $110.00,
  Previous unpaid balance $500.00, Amount due $610.00.
  Line items: 2 hours @ $30 = $60, 3 @ $10 = $30, 10 pages @ $1 = $10.

Done. Vector store cleaned up automatically.
"""
