# Copyright (c) Microsoft. All rights reserved.
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "agent-framework-azure-contentunderstanding",
#     "agent-framework-foundry",
#     "azure-identity",
# ]
# ///
# Run with: uv run packages/azure-contentunderstanding/samples/01-get-started/01_document_qa.py


import asyncio
import os
from pathlib import Path

from agent_framework import Agent, Content, Message
from agent_framework.foundry import FoundryChatClient
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

from agent_framework.foundry import ContentUnderstandingContextProvider

load_dotenv()

"""
Document Q&A — PDF upload with CU-powered extraction

This sample demonstrates the simplest CU integration: upload a PDF and
ask questions about it. Azure Content Understanding extracts structured
markdown with table preservation — superior to LLM-only vision for
scanned PDFs, handwritten content, and complex layouts.

Environment variables:
  FOUNDRY_PROJECT_ENDPOINT                — Azure AI Foundry project endpoint
  FOUNDRY_MODEL             — Model deployment name (e.g. gpt-4.1)
  AZURE_CONTENTUNDERSTANDING_ENDPOINT      — CU endpoint URL
"""

# Path to a sample PDF — uses the shared sample asset if available,
# otherwise falls back to a public URL
SAMPLE_PDF_PATH = Path(__file__).resolve().parents[1] / "shared" / "sample_assets" / "invoice.pdf"


async def main() -> None:
    credential = AzureCliCredential()

    # Set up Azure Content Understanding context provider
    cu = ContentUnderstandingContextProvider(
        endpoint=os.environ["AZURE_CONTENTUNDERSTANDING_ENDPOINT"],
        credential=credential,
        analyzer_id="prebuilt-documentSearch",  # RAG-optimized document analyzer
        max_wait=None,  # wait until CU analysis finishes (no background deferral)
    )

    # Set up the LLM client
    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["FOUNDRY_MODEL"],
        credential=credential,
    )

    # Create agent with CU context provider.
    # The provider extracts document content via CU and injects it into the
    # LLM context so the agent can answer questions about the document.
    async with cu:
        agent = Agent(
            client=client,
            name="DocumentQA",
            instructions=(
                "You are a helpful document analyst. Use the analyzed document "
                "content and extracted fields to answer questions precisely."
            ),
            context_providers=[cu],
        )

        # --- Turn 1: Upload PDF and ask a question ---
        # 4. Upload PDF and ask questions
        # The CU provider extracts markdown + fields from the PDF and injects
        # the full content into context so the agent can answer precisely.
        print("--- Upload PDF and ask questions ---")

        pdf_bytes = SAMPLE_PDF_PATH.read_bytes()

        response = await agent.run(
            Message(
                role="user",
                contents=[
                    Content.from_text(
                        "What is this document about? Who is the vendor, and what is the total amount due?"
                    ),
                    Content.from_data(
                        pdf_bytes,
                        "application/pdf",
                        # Always provide filename — used as the document key
                        additional_properties={"filename": SAMPLE_PDF_PATH.name},
                    ),
                ],
            )
        )
        usage = response.usage_details or {}
        print(f"Agent: {response}")
        print(f"  [Input tokens: {usage.get('input_token_count', 'N/A')}]\n")


if __name__ == "__main__":
    asyncio.run(main())

"""
Sample output:

--- Upload PDF and ask questions ---
Agent: This document is an **invoice** for services and fees billed to
  **MICROSOFT CORPORATION** (Invoice **INV-100**), including line items
  (e.g., Consulting Services, Document Fee, Printing Fee) and a billing summary.
  - **Vendor:** **CONTOSO LTD.**
  - **Total amount due:** **$610.00**
  [Input tokens: 988]
"""
