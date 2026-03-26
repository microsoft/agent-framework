# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "agent-framework-azure-ai-contentunderstanding",
#     "agent-framework-core",
#     "azure-identity",
# ]
# ///
# Run with: uv run packages/azure-ai-contentunderstanding/samples/01-get-started/01_document_qa.py

# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
from pathlib import Path

from agent_framework import Content, Message
from agent_framework.azure import AzureOpenAIResponsesClient
from azure.core.credentials import AzureKeyCredential
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

from agent_framework_azure_ai_contentunderstanding import ContentUnderstandingContextProvider

load_dotenv()

"""
Document Q&A — Single PDF upload with CU-powered extraction

This sample demonstrates the simplest CU integration: upload a PDF,
ask questions about it, then ask follow-up questions using cached results.

Azure Content Understanding extracts structured markdown with table
preservation and field extraction — superior to LLM-only vision for
scanned PDFs, handwritten content, and complex layouts.

Environment variables:
  AZURE_AI_PROJECT_ENDPOINT                — Azure AI Foundry project endpoint
  AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME   — Model deployment name (e.g. gpt-4.1)
  AZURE_CONTENTUNDERSTANDING_ENDPOINT      — CU endpoint URL
"""

# Path to a sample PDF — uses the shared sample asset if available,
# otherwise falls back to a public URL
SAMPLE_PDF_PATH = Path(__file__).resolve().parents[1] / "shared" / "sample_assets" / "invoice.pdf"


async def main() -> None:
    # Auth: use API key if set, otherwise fall back to Azure CLI credential
    api_key = os.environ.get("AZURE_OPENAI_API_KEY")
    credential = AzureKeyCredential(api_key) if api_key else AzureCliCredential()

    # Set up Azure Content Understanding context provider
    cu = ContentUnderstandingContextProvider(
        endpoint=os.environ["AZURE_CONTENTUNDERSTANDING_ENDPOINT"],
        credential=credential,
        analyzer_id="prebuilt-documentSearch",  # RAG-optimized document analyzer
    )

    # Set up the LLM client
    client = AzureOpenAIResponsesClient(
        project_endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
        deployment_name=os.environ["AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME"],
        credential=credential,
    )

    # Create agent with CU context provider
    async with cu:
        agent = client.as_agent(
            name="DocumentQA",
            instructions=(
                "You are a helpful document analyst. Use the analyzed document "
                "content and extracted fields to answer questions precisely."
            ),
            context_providers=[cu],
        )

        # --- Turn 1: Upload PDF and ask a question ---
        print("--- Turn 1: Upload PDF ---")

        if SAMPLE_PDF_PATH.exists():
            pdf_bytes = SAMPLE_PDF_PATH.read_bytes()
            filename = SAMPLE_PDF_PATH.name
        else:
            print(f"Note: {SAMPLE_PDF_PATH} not found. Using a minimal test PDF.")
            # Minimal valid PDF for demonstration
            pdf_bytes = b"%PDF-1.0\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
            filename = "test.pdf"

        response = await agent.run(
            Message(
                role="user",
                contents=[
                    Content.from_text("What is this document about? Summarize the key points."),
                    Content.from_data(
                        pdf_bytes,
                        "application/pdf",
                        # Always provide filename — used as the document key in list_documents()
                        # and get_analyzed_document(). Without it, a hash-based key is generated.
                        additional_properties={"filename": filename},
                    ),
                ],
            )
        )
        print(f"Agent: {response}\n")

        # --- Turn 2: Follow-up question (uses cached result, no re-analysis) ---
        print("--- Turn 2: Follow-up ---")
        response = await agent.run("What are the most important numbers or figures mentioned?")
        print(f"Agent: {response}\n")


if __name__ == "__main__":
    asyncio.run(main())
