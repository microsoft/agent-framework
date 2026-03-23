# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "agent-framework-azure-ai-contentunderstanding",
#     "agent-framework-core",
#     "azure-identity",
#     "openai",
# ]
# ///
# Run with: uv run packages/azure-ai-contentunderstanding/samples/large_doc_file_search.py

# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
from pathlib import Path
from typing import Any

from agent_framework import Content, Message
from agent_framework.azure import AzureOpenAIResponsesClient
from azure.core.credentials import AzureKeyCredential
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
  AZURE_AI_PROJECT_ENDPOINT                — Azure AI Foundry project endpoint
  AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME   — Model deployment name (e.g. gpt-4.1)
  AZURE_CONTENTUNDERSTANDING_ENDPOINT      — CU endpoint URL
"""

SAMPLE_PDF_PATH = Path(__file__).resolve().parents[3] / "samples" / "shared" / "sample_assets" / "sample.pdf"


async def main() -> None:
    # Support both API key and credential-based auth
    api_key = os.environ.get("AZURE_OPENAI_API_KEY")
    credential = AzureCliCredential() if not api_key else None

    # Create async OpenAI client for vector store operations
    openai_kwargs: dict[str, Any] = {
        "azure_endpoint": os.environ["AZURE_AI_PROJECT_ENDPOINT"],
        "api_version": "2025-03-01-preview",
    }
    if api_key:
        openai_kwargs["api_key"] = api_key
    else:
        token = credential.get_token("https://cognitiveservices.azure.com/.default").token  # type: ignore[union-attr]
        openai_kwargs["azure_ad_token"] = token
    openai_client = AsyncAzureOpenAI(**openai_kwargs)

    # Configure CU provider with file_search integration
    # When file_search is set, CU-extracted markdown is automatically uploaded
    # to a vector store and a file_search tool is registered on the context.
    cu_key = os.environ.get("AZURE_CONTENTUNDERSTANDING_API_KEY")
    cu_credential: AzureKeyCredential | AzureCliCredential = (
        AzureKeyCredential(cu_key) if cu_key else credential  # type: ignore[arg-type]
    )

    cu = ContentUnderstandingContextProvider(
        endpoint=os.environ["AZURE_CONTENTUNDERSTANDING_ENDPOINT"],
        credential=cu_credential,
        analyzer_id="prebuilt-documentSearch",
        max_wait=60.0,
        file_search=FileSearchConfig(
            openai_client=openai_client,
            vector_store_name="cu_large_doc_demo",
        ),
    )

    client_kwargs: dict[str, Any] = {
        "project_endpoint": os.environ["AZURE_AI_PROJECT_ENDPOINT"],
        "deployment_name": os.environ["AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME"],
    }
    if api_key:
        client_kwargs["api_key"] = api_key
    else:
        client_kwargs["credential"] = credential
    client = AzureOpenAIResponsesClient(**client_kwargs)

    if SAMPLE_PDF_PATH.exists():
        pdf_bytes = SAMPLE_PDF_PATH.read_bytes()
        filename = SAMPLE_PDF_PATH.name
    else:
        print(f"Note: {SAMPLE_PDF_PATH} not found. Using minimal test data.")
        pdf_bytes = b"%PDF-1.0\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        filename = "large_document.pdf"

    # The provider handles everything: CU extraction + vector store upload + file_search tool
    async with cu:
        agent = client.as_agent(
            name="LargeDocAgent",
            instructions=(
                "You are a document analyst. Use the file_search tool to find "
                "relevant sections from the document and answer precisely. "
                "Cite specific sections when answering."
            ),
            context_providers=[cu],
        )

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
                        additional_properties={"filename": filename},
                    ),
                ],
            )
        )
        print(f"Agent: {response}\n")

        # Turn 2: Follow-up — file_search retrieves relevant chunks (token efficient)
        print("--- Turn 2: Follow-up (RAG) ---")
        response = await agent.run("What numbers or financial metrics are mentioned?")
        print(f"Agent: {response}\n")

    # Vector store is automatically cleaned up when the provider closes
    await openai_client.close()
    print("Done. Vector store cleaned up automatically.")


if __name__ == "__main__":
    asyncio.run(main())
