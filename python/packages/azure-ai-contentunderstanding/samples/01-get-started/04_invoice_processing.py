# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "agent-framework-azure-ai-contentunderstanding",
#     "agent-framework-foundry",
#     "azure-identity",
# ]
# ///
# Run with: uv run packages/azure-ai-contentunderstanding/samples/01-get-started/04_invoice_processing.py

# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
from pathlib import Path

from agent_framework import Agent, AgentSession, Content, Message
from agent_framework.foundry import FoundryChatClient
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

from agent_framework_azure_ai_contentunderstanding import (
    ContentUnderstandingContextProvider,
)

load_dotenv()

"""
Invoice Processing — Structured field extraction with prebuilt-invoice

This sample demonstrates CU's structured field extraction using the
prebuilt-invoice analyzer. Unlike plain text extraction, the prebuilt-invoice
model returns typed fields (VendorName, InvoiceTotal, DueDate, LineItems, etc.)
with confidence scores — enabling precise, schema-aware document processing.

Environment variables:
  AZURE_AI_PROJECT_ENDPOINT                — Azure AI Foundry project endpoint
  AZURE_OPENAI_DEPLOYMENT_NAME             — Model deployment name (e.g. gpt-4.1)
  AZURE_CONTENTUNDERSTANDING_ENDPOINT      — CU endpoint URL
"""

SAMPLE_PDF_PATH = Path(__file__).resolve().parents[1] / "shared" / "sample_assets" / "invoice.pdf"


async def main() -> None:
    # 1. Set up credentials and CU context provider
    credential = AzureCliCredential()

    # Default analyzer is prebuilt-documentSearch (RAG-optimized).
    # Per-file override via additional_properties["analyzer_id"] lets us
    # use prebuilt-invoice for structured field extraction on specific files.
    cu = ContentUnderstandingContextProvider(
        endpoint=os.environ["AZURE_CONTENTUNDERSTANDING_ENDPOINT"],
        credential=credential,
        analyzer_id="prebuilt-documentSearch",  # default for all files
        max_wait=None,  # wait until CU analysis finishes
        output_sections=[
            "markdown",
            "fields",
        ],
    )

    # 2. Set up the LLM client
    client = FoundryChatClient(
        project_endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
        model=os.environ["AZURE_OPENAI_DEPLOYMENT_NAME"],
        credential=credential,
    )

    # 3. Create agent and session
    async with cu:
        agent = Agent(
            client=client,
            name="InvoiceProcessor",
            instructions=(
                "You are an invoice processing assistant. Use the extracted fields "
                "(JSON with confidence scores) to answer precisely. When fields have "
                "low confidence (< 0.8), mention this to the user. Format currency "
                "values clearly."
            ),
            context_providers=[cu],
        )

        session = AgentSession()

        # 4. Upload an invoice PDF
        print("--- Upload Invoice ---")

        pdf_bytes = SAMPLE_PDF_PATH.read_bytes()

        response = await agent.run(
            Message(
                role="user",
                contents=[
                    Content.from_text(
                        "Process this invoice. What is the vendor name, total amount, "
                        "and due date? List all line items if available."
                    ),
                    Content.from_data(
                        pdf_bytes,
                        "application/pdf",
                        # Per-file analyzer override: use prebuilt-invoice for
                        # structured field extraction (VendorName, InvoiceTotal, etc.)
                        # instead of the provider default (prebuilt-documentSearch).
                        additional_properties={
                            "filename": SAMPLE_PDF_PATH.name,
                            "analyzer_id": "prebuilt-invoice",
                        },
                    ),
                ],
            ),
            session=session,
        )
        print(f"Agent: {response}\n")

        # 5. Follow-up: ask about specific fields
        print("--- Follow-up ---")
        response = await agent.run(
            "What is the payment term? Are there any fields with low confidence?",
            session=session,
        )
        print(f"Agent: {response}\n")


if __name__ == "__main__":
    asyncio.run(main())

"""
Sample output:

--- Upload Invoice ---
Agent: ## Key fields (invoice.pdf, page 1)
  - Vendor name: CONTOSO LTD. (low confidence: 0.513)
  - Total amount: USD $110.00 (low confidence: 0.782)
  - Due date: 2019-12-15 (confidence: 0.979)
  ## Line items:
  1) Consulting Services -- 2 hours @ $30.00, total $60.00
  2) Document Fee -- 3 @ $10.00, total $30.00
  3) Printing Fee -- 10 pages @ $1.00, total $10.00

--- Follow-up ---
Agent: Payment term: Not provided (null, confidence 0.872)
  Fields with low confidence (< 0.80): VendorName (0.513), CustomerName (0.436), ...
  Line item descriptions: Consulting Services (0.585), Document Fee (0.520), ...
"""
