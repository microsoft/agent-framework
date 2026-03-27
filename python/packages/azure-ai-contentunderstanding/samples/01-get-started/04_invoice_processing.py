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
    AnalysisSection,
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
    credential = AzureCliCredential()

    # Use prebuilt-invoice analyzer for structured field extraction
    cu = ContentUnderstandingContextProvider(
        endpoint=os.environ["AZURE_CONTENTUNDERSTANDING_ENDPOINT"],
        credential=credential,
        analyzer_id="prebuilt-invoice",
        max_wait=None,  # wait until CU analysis finishes
        output_sections=[
            AnalysisSection.MARKDOWN,
            AnalysisSection.FIELDS,
        ],
    )

    client = FoundryChatClient(
        project_endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
        model=os.environ["AZURE_OPENAI_DEPLOYMENT_NAME"],
        credential=credential,
    )

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

        # --- Upload an invoice PDF ---
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
                        # Always provide filename — used as the document key
                        additional_properties={"filename": SAMPLE_PDF_PATH.name},
                    ),
                ],
            ),
            session=session,
        )
        print(f"Agent: {response}\n")

        # --- Follow-up: ask about specific fields ---
        print("--- Follow-up ---")
        response = await agent.run(
            "What is the payment term? Are there any fields with low confidence?",
            session=session,
        )
        print(f"Agent: {response}\n")


if __name__ == "__main__":
    asyncio.run(main())
