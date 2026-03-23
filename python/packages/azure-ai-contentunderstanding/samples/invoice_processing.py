# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "agent-framework-azure-ai-contentunderstanding",
#     "agent-framework-core",
#     "azure-identity",
# ]
# ///
# Run with: uv run packages/azure-ai-contentunderstanding/samples/invoice_processing.py

# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
from pathlib import Path

from agent_framework import Content, Message
from agent_framework.azure import AzureOpenAIResponsesClient
from azure.core.credentials import AzureKeyCredential
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
  AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME   — Model deployment name (e.g. gpt-4.1)
  AZURE_CONTENTUNDERSTANDING_ENDPOINT      — CU endpoint URL
"""

SAMPLE_PDF_PATH = Path(__file__).resolve().parents[3] / "samples" / "shared" / "sample_assets" / "sample.pdf"


async def main() -> None:
    # Support both API key and credential-based auth
    api_key = os.environ.get("AZURE_OPENAI_API_KEY")
    credential = AzureCliCredential() if not api_key else None
    cu_key = os.environ.get("AZURE_CONTENTUNDERSTANDING_API_KEY")
    cu_credential = AzureKeyCredential(cu_key) if cu_key else credential

    # Use prebuilt-invoice analyzer for structured field extraction
    cu = ContentUnderstandingContextProvider(
        endpoint=os.environ["AZURE_CONTENTUNDERSTANDING_ENDPOINT"],
        credential=cu_credential,
        analyzer_id="prebuilt-invoice",
        output_sections=[
            AnalysisSection.MARKDOWN,
            AnalysisSection.FIELDS,
        ],
    )

    client_kwargs = {
        "project_endpoint": os.environ["AZURE_AI_PROJECT_ENDPOINT"],
        "deployment_name": os.environ["AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME"],
    }
    if api_key:
        client_kwargs["api_key"] = api_key
    else:
        client_kwargs["credential"] = credential
    client = AzureOpenAIResponsesClient(**client_kwargs)

    async with cu:
        agent = client.as_agent(
            name="InvoiceProcessor",
            instructions=(
                "You are an invoice processing assistant. Use the extracted fields "
                "(JSON with confidence scores) to answer precisely. When fields have "
                "low confidence (< 0.8), mention this to the user. Format currency "
                "values clearly."
            ),
            context_providers=[cu],
        )

        # --- Upload an invoice PDF ---
        print("--- Upload Invoice ---")

        if SAMPLE_PDF_PATH.exists():
            pdf_bytes = SAMPLE_PDF_PATH.read_bytes()
            filename = SAMPLE_PDF_PATH.name
        else:
            print(f"Note: {SAMPLE_PDF_PATH} not found. Using a minimal test PDF.")
            pdf_bytes = b"%PDF-1.0\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
            filename = "test_invoice.pdf"

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
                        additional_properties={"filename": filename},
                    ),
                ],
            )
        )
        print(f"Agent: {response}\n")

        # --- Follow-up: ask about specific fields ---
        print("--- Follow-up ---")
        response = await agent.run("What is the payment term? Are there any fields with low confidence?")
        print(f"Agent: {response}\n")


if __name__ == "__main__":
    asyncio.run(main())
