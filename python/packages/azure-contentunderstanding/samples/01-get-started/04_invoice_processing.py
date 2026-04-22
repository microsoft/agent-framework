# Copyright (c) Microsoft. All rights reserved.
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "agent-framework-azure-contentunderstanding",
#     "agent-framework-foundry",
#     "azure-identity",
#     "pydantic",
# ]
# ///
# Run with: uv run packages/azure-contentunderstanding/samples/01-get-started/04_invoice_processing.py


import asyncio
import os
from pathlib import Path

from agent_framework import Agent, AgentSession, Content, Message
from agent_framework.foundry import FoundryChatClient
from azure.identity import AzureCliCredential
from dotenv import load_dotenv
from pydantic import BaseModel, Field

from agent_framework.foundry import ContentUnderstandingContextProvider

load_dotenv()

"""
Invoice Processing — Structured output with prebuilt-invoice analyzer

This sample demonstrates CU's structured field extraction combined with
LLM structured output (Pydantic model). The prebuilt-invoice analyzer extracts
typed fields (VendorName, InvoiceTotal, DueDate, LineItems, etc.) with
confidence scores. We use output_sections=["fields"] only (no markdown needed)
since we want the LLM to produce a structured JSON response from the extracted
fields, not summarize document text.

Environment variables:
  FOUNDRY_PROJECT_ENDPOINT                — Azure AI Foundry project endpoint
  FOUNDRY_MODEL             — Model deployment name (e.g. gpt-4.1)
  AZURE_CONTENTUNDERSTANDING_ENDPOINT      — CU endpoint URL
"""

SAMPLE_PDF_PATH = Path(__file__).resolve().parents[1] / "shared" / "sample_assets" / "invoice.pdf"


# Structured output model — the LLM will return JSON matching this schema
# Structured output models — the LLM returns JSON matching this schema.
#
# Note: the prebuilt-invoice analyzer extracts an extensive set of fields
# (VendorName, BillingAddress, ShippingAddress, TaxDetails, PONumber, etc.).
# This sample defines a simplified schema to extract only the fields of
# interest to the caller. The LLM maps the full CU field output to this
# subset automatically.
# Learn more about prebuilt analyzers: https://learn.microsoft.com/azure/ai-services/content-understanding/concepts/prebuilt-analyzers


class LineItem(BaseModel):
    description: str
    quantity: float | None = None
    unit_price: float | None = None
    amount: float | None = None


class LowConfidenceField(BaseModel):
    field_name: str
    confidence: float


class InvoiceResult(BaseModel):
    vendor_name: str
    total_amount: float | None = None
    currency: str = "USD"
    due_date: str | None = None
    line_items: list[LineItem] = Field(default_factory=list)
    low_confidence_fields: list[LowConfidenceField] = Field(
        default_factory=list,
        description="Fields with confidence < 0.8, including their confidence score",
    )


async def main() -> None:
    # 1. Set up credentials and CU context provider
    credential = AzureCliCredential()

    # Default analyzer is prebuilt-documentSearch (RAG-optimized).
    # Per-file override via additional_properties["analyzer_id"] lets us
    # use prebuilt-invoice for structured field extraction on specific files.
    #
    # Only request "fields" (not "markdown") — we want the extracted typed
    # fields for structured output, not the raw document text.
    cu = ContentUnderstandingContextProvider(
        endpoint=os.environ["AZURE_CONTENTUNDERSTANDING_ENDPOINT"],
        credential=credential,
        analyzer_id="prebuilt-documentSearch",  # default for all files
        max_wait=None,  # wait until CU analysis finishes
        output_sections=["fields"],  # fields only — structured output doesn't need markdown
    )

    # 2. Set up the LLM client
    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["FOUNDRY_MODEL"],
        credential=credential,
    )

    # 3. Create agent and session
    async with cu:
        agent = Agent(
            client=client,
            name="InvoiceProcessor",
            instructions=(
                "You are an invoice processing assistant. Extract invoice data from "
                "the provided CU fields (JSON with confidence scores). Return structured "
                "output matching the requested schema. Flag fields with confidence < 0.8 "
                "in the low_confidence_fields list."
            ),
            context_providers=[cu],
        )

        session = AgentSession()

        # 4. Upload an invoice PDF — uses structured output (Pydantic model)
        print("--- Upload Invoice (Structured Output) ---")

        pdf_bytes = SAMPLE_PDF_PATH.read_bytes()

        response = await agent.run(
            Message(
                role="user",
                contents=[
                    Content.from_text(
                        "Process this invoice. Extract the vendor name, total amount, due date, and all line items."
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
            options={"response_format": InvoiceResult},
        )

        # Parse the structured output from JSON text
        try:
            invoice = InvoiceResult.model_validate_json(response.text)
            print(f"Vendor: {invoice.vendor_name}")
            print(f"Total: {invoice.currency} {invoice.total_amount}")
            print(f"Due date: {invoice.due_date}")
            print(f"Line items ({len(invoice.line_items)}):")
            for item in invoice.line_items:
                print(f"  - {item.description}: {item.amount}")
            if invoice.low_confidence_fields:
                print("⚠ Low confidence fields:")
                for f in invoice.low_confidence_fields:
                    print(f"  - {f.field_name}: {f.confidence:.3f}")
        except Exception:
            print(f"Agent (raw): {response.text}\n")

        # 5. Follow-up: free-text question about the invoice
        print("\n--- Follow-up (Free Text) ---")
        response = await agent.run(
            "What is the payment term? Are there any fields with low confidence?",
            session=session,
        )
        print(f"Agent: {response}\n")


if __name__ == "__main__":
    asyncio.run(main())

"""
Sample output:

--- Upload Invoice (Structured Output) ---
Vendor: CONTOSO LTD.
Total: USD 110.0
Due date: 2019-12-15
Line items (3):
  - Consulting Services: 60.0
  - Document Fee: 30.0
  - Printing Fee: 10.0
⚠ Low confidence: VendorName, CustomerName

--- Follow-up (Free Text) ---
Agent: The payment terms are not explicitly stated on the invoice...
"""
