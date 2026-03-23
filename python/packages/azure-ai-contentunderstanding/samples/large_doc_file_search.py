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
import io
import os
from pathlib import Path
from unittest.mock import MagicMock

from agent_framework import Content, Message
from agent_framework._sessions import AgentSession, SessionContext
from agent_framework.azure import AzureOpenAIResponsesClient
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

from agent_framework_azure_ai_contentunderstanding import ContentUnderstandingContextProvider

load_dotenv()

"""
Large Document + file_search RAG — CU extraction + OpenAI vector store

For large documents (100+ pages) or long audio/video, injecting the full
CU-extracted content into the LLM context is impractical. This sample shows
how to combine CU extraction with OpenAI's file_search tool for token-efficient
RAG retrieval.

Architecture:
  Large PDF -> CU extracts markdown -> Upload to vector store -> file_search
  Follow-up -> file_search retrieves top-k chunks -> LLM answers

CU adds value even for formats file_search supports (PDF): CU-extracted markdown
produces better vector store chunks than raw PDF parsing (85% vs 75% accuracy).

NOTE: Requires OpenAI Responses API for file_search (not available with Anthropic/Ollama).

Environment variables:
  AZURE_AI_PROJECT_ENDPOINT                — Azure AI Foundry project endpoint
  AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME   — Model deployment name (e.g. gpt-4.1)
  AZURE_CONTENTUNDERSTANDING_ENDPOINT      — CU endpoint URL
"""

SAMPLE_PDF_PATH = Path(__file__).resolve().parents[3] / "samples" / "shared" / "sample_assets" / "sample.pdf"


async def main() -> None:
    credential = AzureCliCredential()

    # Step 1: Use CU to extract high-quality markdown
    cu = ContentUnderstandingContextProvider(
        endpoint=os.environ["AZURE_CONTENTUNDERSTANDING_ENDPOINT"],
        credential=credential,
        analyzer_id="prebuilt-documentSearch",
        max_wait=60.0,
    )

    client = AzureOpenAIResponsesClient(
        project_endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
        deployment_name=os.environ["AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME"],
        credential=credential,
    )

    if SAMPLE_PDF_PATH.exists():
        pdf_bytes = SAMPLE_PDF_PATH.read_bytes()
        filename = SAMPLE_PDF_PATH.name
    else:
        print(f"Note: {SAMPLE_PDF_PATH} not found. Using minimal test data.")
        pdf_bytes = b"%PDF-1.0\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        filename = "large_document.pdf"

    print("--- Step 1: CU Extraction ---")
    async with cu:
        msg = Message(
            role="user",
            contents=[
                Content.from_text("Extract content from this document."),
                Content.from_data(pdf_bytes, "application/pdf", additional_properties={"filename": filename}),
            ],
        )
        context = SessionContext(input_messages=[msg])
        state: dict = {}
        session = AgentSession()

        await cu.before_run(agent=MagicMock(), session=session, context=context, state=state)

        docs = state.get("documents", {})
        if not docs:
            print("No documents were analyzed.")
            return

        doc_entry = next(iter(docs.values()))
        if doc_entry["status"] != "ready":
            print(f"Document not ready: {doc_entry['status']}")
            return

        markdown = doc_entry["result"].get("markdown", "")
        print(f"Extracted {len(markdown)} chars of markdown from '{filename}'")

    # Step 2: Upload CU-extracted markdown to OpenAI vector store for RAG
    print("\n--- Step 2: Upload to Vector Store ---")
    from openai import AzureOpenAI

    token = credential.get_token("https://cognitiveservices.azure.com/.default").token
    openai_client = AzureOpenAI(
        azure_endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
        azure_ad_token=token,
        api_version="2025-03-01-preview",
    )

    try:
        md_bytes = markdown.encode("utf-8")
        file = openai_client.files.create(file=("extracted.md", io.BytesIO(md_bytes)), purpose="assistants")
        print(f"Uploaded file: {file.id}")

        vector_store = openai_client.vector_stores.create(name="cu_extracted_docs")
        openai_client.vector_stores.files.create(vector_store_id=vector_store.id, file_id=file.id)
        print(f"Vector store: {vector_store.id}")

        # Step 3: Use file_search for token-efficient follow-up Q&A
        print("\n--- Step 3: RAG Q&A with file_search ---")
        agent = client.as_agent(
            name="LargeDocAgent",
            instructions=(
                "You are a document analyst. Use the file_search tool to find "
                "relevant sections from the document and answer precisely."
            ),
            tools=[{"type": "file_search", "vector_store_ids": [vector_store.id]}],
        )

        response = await agent.run("What are the key points in this document?")
        print(f"Agent: {response}\n")

        response = await agent.run("What numbers or metrics are mentioned?")
        print(f"Agent: {response}\n")

    finally:
        try:
            openai_client.vector_stores.delete(vector_store.id)
            openai_client.files.delete(file.id)
        except Exception:
            pass
        print("Cleaned up vector store and files.")


if __name__ == "__main__":
    asyncio.run(main())
