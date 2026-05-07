# Copyright (c) Microsoft. All rights reserved.

"""Integration tests for ContentUnderstandingContextProvider.

These tests require a live Azure Content Understanding endpoint.
Set AZURE_CONTENTUNDERSTANDING_ENDPOINT to enable them.

To generate fixtures for unit tests, run these tests with --update-fixtures flag
and the resulting JSON files will be written to tests/cu/fixtures/.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

skip_if_cu_integration_tests_disabled = pytest.mark.skipif(
    not os.environ.get("AZURE_CONTENTUNDERSTANDING_ENDPOINT"),
    reason="CU integration tests disabled (AZURE_CONTENTUNDERSTANDING_ENDPOINT not set)",
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"

# Shared sample asset — same PDF used by samples and integration tests
INVOICE_PDF_PATH = Path(__file__).resolve().parents[2] / "samples" / "shared" / "sample_assets" / "invoice.pdf"


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_cu_integration_tests_disabled
async def test_analyze_pdf_binary() -> None:
    """Analyze a PDF via binary upload and optionally capture fixture."""
    from azure.ai.contentunderstanding.aio import ContentUnderstandingClient
    from azure.identity.aio import DefaultAzureCredential

    endpoint = os.environ["AZURE_CONTENTUNDERSTANDING_ENDPOINT"]
    analyzer_id = os.environ.get("AZURE_CONTENTUNDERSTANDING_ANALYZER_ID", "prebuilt-documentSearch")

    pdf_path = INVOICE_PDF_PATH
    assert pdf_path.exists(), f"Test fixture not found: {pdf_path}"
    pdf_bytes = pdf_path.read_bytes()

    async with DefaultAzureCredential() as credential, ContentUnderstandingClient(endpoint, credential) as client:
        poller = await client.begin_analyze_binary(
            analyzer_id,
            binary_input=pdf_bytes,
            content_type="application/pdf",
        )
        result = await poller.result()

    assert result.contents
    assert result.contents[0].markdown
    assert len(result.contents[0].markdown) > 10
    assert "CONTOSO LTD." in result.contents[0].markdown

    # Optionally capture fixture
    if os.environ.get("CU_UPDATE_FIXTURES"):
        FIXTURES_DIR.mkdir(exist_ok=True)
        fixture_path = FIXTURES_DIR / "analyze_pdf_result.json"
        fixture_path.write_text(json.dumps(result.as_dict(), indent=2, default=str))


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_cu_integration_tests_disabled
async def test_before_run_e2e() -> None:
    """End-to-end test: Content.from_data → before_run → state populated."""
    from agent_framework import Content, Message, SessionContext
    from agent_framework._sessions import AgentSession
    from azure.identity.aio import DefaultAzureCredential

    from agent_framework_azure_contentunderstanding import ContentUnderstandingContextProvider

    endpoint = os.environ["AZURE_CONTENTUNDERSTANDING_ENDPOINT"]

    pdf_path = INVOICE_PDF_PATH
    assert pdf_path.exists(), f"Test fixture not found: {pdf_path}"
    pdf_bytes = pdf_path.read_bytes()

    async with DefaultAzureCredential() as credential:
        cu = ContentUnderstandingContextProvider(
            endpoint=endpoint,
            credential=credential,
            max_wait=None,  # wait until analysis completes (no background deferral)
        )
        async with cu:
            msg = Message(
                role="user",
                contents=[
                    Content.from_text("What's in this document?"),
                    Content.from_data(
                        pdf_bytes,
                        "application/pdf",
                        additional_properties={"filename": "invoice.pdf"},
                    ),
                ],
            )
            context = SessionContext(input_messages=[msg])
            state: dict[str, object] = {}
            session = AgentSession()

            from unittest.mock import MagicMock

            await cu.before_run(agent=MagicMock(), session=session, context=context, state=state)

            docs = state.get("documents", {})
            assert isinstance(docs, dict)
            assert "invoice.pdf" in docs
            doc_entry = docs["invoice.pdf"]
            assert doc_entry["status"] == "ready"
            assert doc_entry["result"] is not None
            assert doc_entry["result"].get("markdown")
            assert len(doc_entry["result"]["markdown"]) > 10
            assert "CONTOSO LTD." in doc_entry["result"]["markdown"]


# Raw GitHub URL for a public invoice PDF from the CU samples repo
_INVOICE_PDF_URL = (
    "https://raw.githubusercontent.com/Azure-Samples/azure-ai-content-understanding-assets/main/document/invoice.pdf"
)


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_cu_integration_tests_disabled
async def test_before_run_uri_content() -> None:
    """End-to-end test: Content.from_uri with an external URL → before_run → state populated.

    Verifies that CU can analyze a file referenced by URL (not base64 data).
    Uses a public invoice PDF from the Azure CU samples repository.
    """
    from agent_framework import Content, Message, SessionContext
    from agent_framework._sessions import AgentSession
    from azure.identity.aio import DefaultAzureCredential

    from agent_framework_azure_contentunderstanding import ContentUnderstandingContextProvider

    endpoint = os.environ["AZURE_CONTENTUNDERSTANDING_ENDPOINT"]

    async with DefaultAzureCredential() as credential:
        cu = ContentUnderstandingContextProvider(
            endpoint=endpoint,
            credential=credential,
            max_wait=None,  # wait until analysis completes (no background deferral)
        )
        async with cu:
            msg = Message(
                role="user",
                contents=[
                    Content.from_text("What's on this invoice?"),
                    Content.from_uri(
                        uri=_INVOICE_PDF_URL,
                        media_type="application/pdf",
                        additional_properties={"filename": "invoice.pdf"},
                    ),
                ],
            )
            context = SessionContext(input_messages=[msg])
            state: dict[str, object] = {}
            session = AgentSession()

            from unittest.mock import MagicMock

            await cu.before_run(agent=MagicMock(), session=session, context=context, state=state)

            docs = state.get("documents", {})
            assert isinstance(docs, dict)
            assert "invoice.pdf" in docs

            doc_entry = docs["invoice.pdf"]
            assert doc_entry["status"] == "ready"
            assert doc_entry["result"] is not None
            assert doc_entry["result"].get("markdown")
            assert len(doc_entry["result"]["markdown"]) > 10
            assert "CONTOSO LTD." in doc_entry["result"]["markdown"]


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_cu_integration_tests_disabled
async def test_before_run_data_uri_content() -> None:
    """End-to-end test: Content.from_uri with a base64 data URI → before_run → state populated.

    Verifies that CU can analyze a file embedded as a data URI (data:application/pdf;base64,...).
    This tests the data URI path: from_uri with "data:" prefix → type="data" → begin_analyze_binary.
    """
    import base64

    from agent_framework import Content, Message, SessionContext
    from agent_framework._sessions import AgentSession
    from azure.identity.aio import DefaultAzureCredential

    from agent_framework_azure_contentunderstanding import ContentUnderstandingContextProvider

    endpoint = os.environ["AZURE_CONTENTUNDERSTANDING_ENDPOINT"]

    pdf_path = INVOICE_PDF_PATH
    assert pdf_path.exists(), f"Test fixture not found: {pdf_path}"
    pdf_bytes = pdf_path.read_bytes()
    b64 = base64.b64encode(pdf_bytes).decode("ascii")
    data_uri = f"data:application/pdf;base64,{b64}"

    async with DefaultAzureCredential() as credential:
        cu = ContentUnderstandingContextProvider(
            endpoint=endpoint,
            credential=credential,
            max_wait=None,  # wait until analysis completes
        )
        async with cu:
            msg = Message(
                role="user",
                contents=[
                    Content.from_text("What's on this invoice?"),
                    Content.from_uri(
                        uri=data_uri,
                        media_type="application/pdf",
                        additional_properties={"filename": "invoice_b64.pdf"},
                    ),
                ],
            )
            context = SessionContext(input_messages=[msg])
            state: dict[str, object] = {}
            session = AgentSession()

            from unittest.mock import MagicMock

            await cu.before_run(agent=MagicMock(), session=session, context=context, state=state)

            docs = state.get("documents", {})
            assert isinstance(docs, dict)
            assert "invoice_b64.pdf" in docs

            doc_entry = docs["invoice_b64.pdf"]
            assert doc_entry["status"] == "ready"
            assert doc_entry["result"] is not None
            assert doc_entry["result"].get("markdown")
            assert len(doc_entry["result"]["markdown"]) > 10
            assert "CONTOSO LTD." in doc_entry["result"]["markdown"]


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_cu_integration_tests_disabled
async def test_before_run_background_analysis() -> None:
    """End-to-end test: max_wait timeout → background analysis → resolved on next turn.

    Uses a short max_wait (0.5s) so CU analysis is deferred to background.
    Then waits for analysis to complete and calls before_run again to verify
    the background task resolves and the document becomes ready.
    """
    import asyncio

    from agent_framework import Content, Message, SessionContext
    from agent_framework._sessions import AgentSession
    from azure.identity.aio import DefaultAzureCredential

    from agent_framework_azure_contentunderstanding import ContentUnderstandingContextProvider

    endpoint = os.environ["AZURE_CONTENTUNDERSTANDING_ENDPOINT"]

    async with DefaultAzureCredential() as credential:
        cu = ContentUnderstandingContextProvider(
            endpoint=endpoint,
            credential=credential,
            max_wait=0.5,  # short timeout to force background deferral
        )
        async with cu:
            # Turn 1: upload file — should time out and defer to background
            msg = Message(
                role="user",
                contents=[
                    Content.from_text("What's on this invoice?"),
                    Content.from_uri(
                        uri=_INVOICE_PDF_URL,
                        media_type="application/pdf",
                        additional_properties={"filename": "invoice.pdf"},
                    ),
                ],
            )
            context = SessionContext(input_messages=[msg])
            state: dict[str, object] = {}
            session = AgentSession()

            from unittest.mock import MagicMock

            await cu.before_run(agent=MagicMock(), session=session, context=context, state=state)

            docs = state.get("documents", {})
            assert isinstance(docs, dict)
            assert "invoice.pdf" in docs
            assert docs["invoice.pdf"]["status"] == "analyzing", (
                f"Expected 'analyzing' but got '{docs['invoice.pdf']['status']}' — "
                "CU responded too fast for the 0.5s timeout"
            )
            assert docs["invoice.pdf"]["result"] is None

            # Wait for background analysis to complete
            await asyncio.sleep(30)

            # Turn 2: no new files — should resolve the background task
            msg2 = Message(role="user", contents=[Content.from_text("Is it ready?")])
            context2 = SessionContext(input_messages=[msg2])

            await cu.before_run(agent=MagicMock(), session=session, context=context2, state=state)

            assert docs["invoice.pdf"]["status"] == "ready"
            assert docs["invoice.pdf"]["result"] is not None
            assert docs["invoice.pdf"]["result"].get("markdown")
            assert "CONTOSO LTD." in docs["invoice.pdf"]["result"]["markdown"]
