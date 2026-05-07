# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
import base64
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from agent_framework import Content, Message, SessionContext
from agent_framework._sessions import AgentSession
from azure.ai.contentunderstanding.models import AnalysisResult

from agent_framework_azure_contentunderstanding import (
    ContentUnderstandingContextProvider,
    DocumentStatus,
)
from agent_framework_azure_contentunderstanding._detection import SUPPORTED_MEDIA_TYPES, derive_doc_key
from agent_framework_azure_contentunderstanding._extraction import format_result

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SAMPLE_PDF_BYTES = b"%PDF-1.4 fake content for testing"


def _make_mock_poller(result: AnalysisResult) -> AsyncMock:
    """Create a mock poller that returns the given result immediately."""
    poller = AsyncMock()
    poller.result = AsyncMock(return_value=result)
    return poller


def _make_slow_poller(result: AnalysisResult, delay: float = 10.0) -> MagicMock:
    """Create a mock poller that simulates a timeout then eventually returns."""
    poller = MagicMock()

    async def slow_result() -> AnalysisResult:
        await asyncio.sleep(delay)
        return result

    poller.result = slow_result
    poller.continuation_token = MagicMock(return_value="mock_slow_continuation_token")
    return poller


def _make_failing_poller(error: Exception) -> AsyncMock:
    """Create a mock poller that raises an exception."""
    poller = AsyncMock()
    poller.result = AsyncMock(side_effect=error)
    return poller


def _make_data_uri(data: bytes, media_type: str) -> str:
    return f"data:{media_type};base64,{base64.b64encode(data).decode('ascii')}"


def _make_content_from_data(data: bytes, media_type: str, filename: str | None = None) -> Content:
    props = {"filename": filename} if filename else None
    return Content.from_data(data, media_type, additional_properties=props)


def _make_context(messages: list[Message]) -> SessionContext:
    return SessionContext(input_messages=messages)


def _make_provider(
    mock_client: AsyncMock | None = None,
    **kwargs: Any,
) -> ContentUnderstandingContextProvider:
    provider = ContentUnderstandingContextProvider(
        endpoint="https://test.cognitiveservices.azure.com/",
        credential=AsyncMock(),
        **kwargs,
    )
    if mock_client:
        provider._client = mock_client  # type: ignore[assignment]
    return provider


def _make_mock_agent() -> MagicMock:
    return MagicMock()


# ===========================================================================
# Test Classes
# ===========================================================================


class TestInit:
    def test_default_values(self) -> None:
        provider = ContentUnderstandingContextProvider(
            endpoint="https://test.cognitiveservices.azure.com/",
            credential=AsyncMock(),
        )
        assert provider.analyzer_id is None
        assert provider.max_wait == 5.0
        assert provider.output_sections == ["markdown", "fields"]
        assert provider.source_id == "azure_contentunderstanding"

    def test_custom_values(self) -> None:
        provider = ContentUnderstandingContextProvider(
            endpoint="https://custom.cognitiveservices.azure.com/",
            credential=AsyncMock(),
            analyzer_id="prebuilt-invoice",
            max_wait=10.0,
            output_sections=["markdown"],
            source_id="custom_cu",
        )
        assert provider.analyzer_id == "prebuilt-invoice"
        assert provider.max_wait == 10.0
        assert provider.output_sections == ["markdown"]
        assert provider.source_id == "custom_cu"

    def test_max_wait_none(self) -> None:
        provider = ContentUnderstandingContextProvider(
            endpoint="https://test.cognitiveservices.azure.com/",
            credential=AsyncMock(),
            max_wait=None,
        )
        assert provider.max_wait is None

    def test_endpoint_from_env_var(self, monkeypatch: Any) -> None:
        """Endpoint can be loaded from AZURE_CONTENTUNDERSTANDING_ENDPOINT env var."""
        monkeypatch.setenv(
            "AZURE_CONTENTUNDERSTANDING_ENDPOINT",
            "https://env-test.cognitiveservices.azure.com/",
        )
        provider = ContentUnderstandingContextProvider(credential=AsyncMock())
        assert provider._endpoint == "https://env-test.cognitiveservices.azure.com/"

    def test_explicit_endpoint_overrides_env_var(self, monkeypatch: Any) -> None:
        """Explicit endpoint kwarg takes priority over env var."""
        monkeypatch.setenv(
            "AZURE_CONTENTUNDERSTANDING_ENDPOINT",
            "https://env-test.cognitiveservices.azure.com/",
        )
        provider = ContentUnderstandingContextProvider(
            endpoint="https://explicit.cognitiveservices.azure.com/",
            credential=AsyncMock(),
        )
        assert provider._endpoint == "https://explicit.cognitiveservices.azure.com/"

    def test_missing_endpoint_raises(self) -> None:
        """Missing endpoint (no kwarg, no env var) raises an error."""
        # Clear env var to ensure load_settings raises
        import os

        import pytest as _pytest
        from agent_framework.exceptions import SettingNotFoundError

        env_key = "AZURE_CONTENTUNDERSTANDING_ENDPOINT"
        old_val = os.environ.pop(env_key, None)
        try:
            with _pytest.raises(SettingNotFoundError, match="endpoint"):
                ContentUnderstandingContextProvider(credential=AsyncMock())
        finally:
            if old_val is not None:
                os.environ[env_key] = old_val

    def test_missing_credential_raises(self) -> None:
        """Missing credential raises ValueError."""
        import pytest as _pytest

        with _pytest.raises(ValueError, match="credential is required"):
            ContentUnderstandingContextProvider(
                endpoint="https://test.cognitiveservices.azure.com/",
            )


class TestAsyncContextManager:
    async def test_aenter_returns_self(self) -> None:
        provider = ContentUnderstandingContextProvider(
            endpoint="https://test.cognitiveservices.azure.com/",
            credential=AsyncMock(),
        )
        result = await provider.__aenter__()
        assert result is provider
        await provider.__aexit__(None, None, None)

    async def test_aexit_closes_client(self) -> None:
        provider = ContentUnderstandingContextProvider(
            endpoint="https://test.cognitiveservices.azure.com/",
            credential=AsyncMock(),
        )
        mock_client = AsyncMock()
        provider._client = mock_client  # type: ignore[assignment]
        await provider.__aexit__(None, None, None)
        mock_client.close.assert_called_once()


class TestBeforeRunNewFile:
    async def test_single_pdf_analyzed(
        self,
        mock_cu_client: AsyncMock,
        pdf_analysis_result: AnalysisResult,
    ) -> None:
        mock_cu_client.begin_analyze_binary = AsyncMock(return_value=_make_mock_poller(pdf_analysis_result))
        provider = _make_provider(mock_client=mock_cu_client)

        msg = Message(
            role="user",
            contents=[
                Content.from_text("What's on this invoice?"),
                _make_content_from_data(_SAMPLE_PDF_BYTES, "application/pdf", "invoice.pdf"),
            ],
        )
        context = _make_context([msg])
        state: dict[str, Any] = {}
        session = AgentSession()

        await provider.before_run(agent=_make_mock_agent(), session=session, context=context, state=state)

        # Document should be in state
        assert "documents" in state
        assert "invoice.pdf" in state["documents"]
        assert state["documents"]["invoice.pdf"]["status"] == DocumentStatus.READY

        # Binary should be stripped from input
        for m in context.input_messages:
            for c in m.contents:
                assert c.media_type != "application/pdf"

        # Context should have messages injected
        assert len(context.context_messages) > 0

    async def test_url_input_analyzed(
        self,
        mock_cu_client: AsyncMock,
        pdf_analysis_result: AnalysisResult,
    ) -> None:
        mock_cu_client.begin_analyze = AsyncMock(return_value=_make_mock_poller(pdf_analysis_result))
        provider = _make_provider(mock_client=mock_cu_client)

        msg = Message(
            role="user",
            contents=[
                Content.from_text("Analyze this document"),
                Content.from_uri("https://example.com/report.pdf", media_type="application/pdf"),
            ],
        )
        context = _make_context([msg])
        state: dict[str, Any] = {}
        session = AgentSession()

        await provider.before_run(agent=_make_mock_agent(), session=session, context=context, state=state)

        # URL input should use begin_analyze
        mock_cu_client.begin_analyze.assert_called_once()
        assert "report.pdf" in state["documents"]
        assert state["documents"]["report.pdf"]["status"] == DocumentStatus.READY

    async def test_text_only_skipped(self, mock_cu_client: AsyncMock) -> None:
        provider = _make_provider(mock_client=mock_cu_client)

        msg = Message(role="user", contents=[Content.from_text("What's the weather?")])
        context = _make_context([msg])
        state: dict[str, Any] = {}
        session = AgentSession()

        await provider.before_run(agent=_make_mock_agent(), session=session, context=context, state=state)

        # No CU calls
        mock_cu_client.begin_analyze.assert_not_called()
        mock_cu_client.begin_analyze_binary.assert_not_called()
        # No documents
        assert state.get("documents", {}) == {}


class TestBeforeRunMultiFile:
    async def test_two_files_both_analyzed(
        self,
        mock_cu_client: AsyncMock,
        pdf_analysis_result: AnalysisResult,
        image_analysis_result: AnalysisResult,
    ) -> None:
        mock_cu_client.begin_analyze_binary = AsyncMock(
            side_effect=[
                _make_mock_poller(pdf_analysis_result),
                _make_mock_poller(image_analysis_result),
            ]
        )
        provider = _make_provider(mock_client=mock_cu_client)

        msg = Message(
            role="user",
            contents=[
                Content.from_text("Compare these documents"),
                _make_content_from_data(_SAMPLE_PDF_BYTES, "application/pdf", "doc1.pdf"),
                _make_content_from_data(b"\x89PNG fake", "image/png", "chart.png"),
            ],
        )
        context = _make_context([msg])
        state: dict[str, Any] = {}
        session = AgentSession()

        await provider.before_run(agent=_make_mock_agent(), session=session, context=context, state=state)

        assert len(state["documents"]) == 2
        assert state["documents"]["doc1.pdf"]["status"] == DocumentStatus.READY
        assert state["documents"]["chart.png"]["status"] == DocumentStatus.READY


class TestBeforeRunTimeout:
    async def test_exceeds_max_wait_defers_to_background(
        self,
        mock_cu_client: AsyncMock,
        pdf_analysis_result: AnalysisResult,
    ) -> None:
        mock_cu_client.begin_analyze_binary = AsyncMock(return_value=_make_slow_poller(pdf_analysis_result, delay=10.0))
        provider = _make_provider(mock_client=mock_cu_client, max_wait=0.1)

        msg = Message(
            role="user",
            contents=[
                Content.from_text("Analyze this"),
                _make_content_from_data(_SAMPLE_PDF_BYTES, "application/pdf", "big_doc.pdf"),
            ],
        )
        context = _make_context([msg])
        state: dict[str, Any] = {}
        session = AgentSession()

        await provider.before_run(agent=_make_mock_agent(), session=session, context=context, state=state)

        assert state["documents"]["big_doc.pdf"]["status"] == DocumentStatus.ANALYZING
        assert "big_doc.pdf" in state.get("_pending_tokens", {})
        token_info = state["_pending_tokens"]["big_doc.pdf"]
        assert "continuation_token" in token_info
        assert "analyzer_id" in token_info

        # Context messages should mention analyzing
        assert any("being analyzed" in m.text for msgs in context.context_messages.values() for m in msgs)


class TestBeforeRunPendingResolution:
    async def test_pending_completes_on_next_turn(
        self,
        mock_cu_client: AsyncMock,
        pdf_analysis_result: AnalysisResult,
    ) -> None:
        # Mock begin_analyze to return a completed poller when called with continuation_token
        mock_poller = _make_mock_poller(pdf_analysis_result)
        mock_poller.done = MagicMock(return_value=True)
        mock_cu_client.begin_analyze = AsyncMock(return_value=mock_poller)
        provider = _make_provider(mock_client=mock_cu_client)

        state: dict[str, Any] = {
            "_pending_tokens": {
                "report.pdf": {"continuation_token": "tok_123", "analyzer_id": "prebuilt-documentSearch"}
            },
            "documents": {
                "report.pdf": {
                    "status": DocumentStatus.ANALYZING,
                    "filename": "report.pdf",
                    "media_type": "application/pdf",
                    "analyzer_id": "prebuilt-documentSearch",
                    "analyzed_at": None,
                    "analysis_duration_s": None,
                    "upload_duration_s": None,
                    "result": None,
                    "error": None,
                },
            },
        }

        msg = Message(role="user", contents=[Content.from_text("Is the report ready?")])
        context = _make_context([msg])
        session = AgentSession()

        await provider.before_run(agent=_make_mock_agent(), session=session, context=context, state=state)

        assert state["documents"]["report.pdf"]["status"] == DocumentStatus.READY
        assert state["documents"]["report.pdf"]["result"] is not None
        assert "report.pdf" not in state.get("_pending_tokens", {})


class TestBeforeRunPendingFailure:
    async def test_pending_task_failure_updates_state(
        self,
        mock_cu_client: AsyncMock,
    ) -> None:
        # Mock begin_analyze to raise when resuming from continuation token
        mock_cu_client.begin_analyze = AsyncMock(side_effect=RuntimeError("CU service unavailable"))
        provider = _make_provider(mock_client=mock_cu_client)

        state: dict[str, Any] = {
            "_pending_tokens": {
                "bad_doc.pdf": {"continuation_token": "tok_fail", "analyzer_id": "prebuilt-documentSearch"}
            },
            "documents": {
                "bad_doc.pdf": {
                    "status": DocumentStatus.ANALYZING,
                    "filename": "bad_doc.pdf",
                    "media_type": "application/pdf",
                    "analyzer_id": "prebuilt-documentSearch",
                    "analyzed_at": None,
                    "analysis_duration_s": None,
                    "upload_duration_s": None,
                    "result": None,
                    "error": None,
                },
            },
        }

        msg = Message(role="user", contents=[Content.from_text("Check status")])
        context = _make_context([msg])
        session = AgentSession()

        await provider.before_run(agent=_make_mock_agent(), session=session, context=context, state=state)

        assert state["documents"]["bad_doc.pdf"]["status"] == DocumentStatus.FAILED
        assert "CU service unavailable" in (state["documents"]["bad_doc.pdf"]["error"] or "")


class TestDocumentKeyDerivation:
    def test_filename_from_additional_properties(self) -> None:
        content = _make_content_from_data(_SAMPLE_PDF_BYTES, "application/pdf", "my_report.pdf")
        key = derive_doc_key(content)
        assert key == "my_report.pdf"

    def test_url_basename(self) -> None:
        content = Content.from_uri("https://example.com/docs/annual_report.pdf", media_type="application/pdf")
        key = derive_doc_key(content)
        assert key == "annual_report.pdf"

    def test_content_hash_fallback(self) -> None:
        content = Content.from_data(_SAMPLE_PDF_BYTES, "application/pdf")
        key = derive_doc_key(content)
        assert key.startswith("doc_")
        assert len(key) == 12  # "doc_" + 8 hex chars


class TestSessionState:
    async def test_documents_persist_across_turns(
        self,
        mock_cu_client: AsyncMock,
        pdf_analysis_result: AnalysisResult,
    ) -> None:
        mock_cu_client.begin_analyze_binary = AsyncMock(return_value=_make_mock_poller(pdf_analysis_result))
        provider = _make_provider(mock_client=mock_cu_client)

        state: dict[str, Any] = {}
        session = AgentSession()

        # Turn 1: upload
        msg1 = Message(
            role="user",
            contents=[
                Content.from_text("Analyze this"),
                _make_content_from_data(_SAMPLE_PDF_BYTES, "application/pdf", "doc.pdf"),
            ],
        )
        ctx1 = _make_context([msg1])
        await provider.before_run(agent=_make_mock_agent(), session=session, context=ctx1, state=state)

        assert "doc.pdf" in state["documents"]

        # Turn 2: follow-up (no file)
        msg2 = Message(role="user", contents=[Content.from_text("What's the total?")])
        ctx2 = _make_context([msg2])
        await provider.before_run(agent=_make_mock_agent(), session=session, context=ctx2, state=state)

        # Document should still be there
        assert "doc.pdf" in state["documents"]
        assert state["documents"]["doc.pdf"]["status"] == DocumentStatus.READY


class TestListDocumentsTool:
    async def test_returns_all_docs_with_status(
        self,
        mock_cu_client: AsyncMock,
        pdf_analysis_result: AnalysisResult,
    ) -> None:
        mock_cu_client.begin_analyze_binary = AsyncMock(return_value=_make_mock_poller(pdf_analysis_result))
        provider = _make_provider(mock_client=mock_cu_client)

        state: dict[str, Any] = {}
        session = AgentSession()

        msg = Message(
            role="user",
            contents=[
                Content.from_text("Analyze this"),
                _make_content_from_data(_SAMPLE_PDF_BYTES, "application/pdf", "test.pdf"),
            ],
        )
        context = _make_context([msg])
        await provider.before_run(agent=_make_mock_agent(), session=session, context=context, state=state)

        # Find the list_documents tool
        list_tool = None
        for tool in context.tools:
            if getattr(tool, "name", None) == "list_documents":
                list_tool = tool
                break

        assert list_tool is not None
        result = list_tool.func()  # type: ignore[union-attr]
        parsed = json.loads(result)
        assert len(parsed) == 1
        assert parsed[0]["name"] == "test.pdf"
        assert parsed[0]["status"] == DocumentStatus.READY


class TestOutputFiltering:
    def test_default_markdown_and_fields(self, pdf_analysis_result: AnalysisResult) -> None:
        provider = _make_provider()
        result = provider._extract_sections(pdf_analysis_result)

        assert "markdown" in result
        assert "fields" in result
        assert "Contoso" in str(result["markdown"])

    def test_markdown_only(self, pdf_analysis_result: AnalysisResult) -> None:
        provider = _make_provider(output_sections=["markdown"])
        result = provider._extract_sections(pdf_analysis_result)

        assert "markdown" in result
        assert "fields" not in result

    def test_fields_only(self, invoice_analysis_result: AnalysisResult) -> None:
        provider = _make_provider(output_sections=["fields"])
        result = provider._extract_sections(invoice_analysis_result)

        assert "markdown" not in result
        assert "fields" in result
        fields = result["fields"]
        assert isinstance(fields, dict)
        assert "VendorName" in fields

    def test_field_values_extracted(self, invoice_analysis_result: AnalysisResult) -> None:
        provider = _make_provider()
        result = provider._extract_sections(invoice_analysis_result)

        fields = result.get("fields")
        assert isinstance(fields, dict)
        assert "VendorName" in fields
        assert fields["VendorName"]["value"] is not None
        assert fields["VendorName"]["confidence"] is not None

    def test_invoice_field_extraction_matches_expected(self, invoice_analysis_result: AnalysisResult) -> None:
        """Full invoice field extraction should match expected JSON structure.

        This test defines the complete expected output for all fields in the
        invoice fixture, making it easy to review the extraction behavior at
        a glance. Confidence is only present when the CU service provides it.
        """
        provider = _make_provider()
        result = provider._extract_sections(invoice_analysis_result)
        fields = result.get("fields")

        expected_fields = {
            "VendorName": {
                "type": "string",
                "value": "TechServe Global Partners",
                "confidence": 0.71,
            },
            "DueDate": {
                "type": "date",
                # SDK .value returns datetime.date for date fields
                "value": fields["DueDate"]["value"],  # dynamic — date object
                "confidence": 0.793,
            },
            "InvoiceDate": {
                "type": "date",
                "value": fields["InvoiceDate"]["value"],
                "confidence": 0.693,
            },
            "InvoiceId": {
                "type": "string",
                "value": "INV-100",
                "confidence": 0.489,
            },
            "AmountDue": {
                "type": "object",
                # No confidence — object types don't have it
                "value": {
                    "Amount": {"type": "number", "value": 610.0, "confidence": 0.758},
                    "CurrencyCode": {"type": "string", "value": "USD"},
                },
            },
            "SubtotalAmount": {
                "type": "object",
                "value": {
                    "Amount": {"type": "number", "value": 100.0, "confidence": 0.902},
                    "CurrencyCode": {"type": "string", "value": "USD"},
                },
            },
            "LineItems": {
                "type": "array",
                "value": [
                    {
                        "type": "object",
                        "value": {
                            "Description": {"type": "string", "value": "Consulting Services", "confidence": 0.664},
                            "Quantity": {"type": "number", "value": 2.0, "confidence": 0.957},
                            "UnitPrice": {
                                "type": "object",
                                "value": {
                                    "Amount": {"type": "number", "value": 30.0, "confidence": 0.956},
                                    "CurrencyCode": {"type": "string", "value": "USD"},
                                },
                            },
                        },
                    },
                    {
                        "type": "object",
                        "value": {
                            "Description": {"type": "string", "value": "Document Fee", "confidence": 0.712},
                            "Quantity": {"type": "number", "value": 3.0, "confidence": 0.939},
                        },
                    },
                ],
            },
        }

        assert fields == expected_fields


class TestDuplicateDocumentKey:
    async def test_duplicate_filename_rejected(
        self,
        mock_cu_client: AsyncMock,
        pdf_analysis_result: AnalysisResult,
    ) -> None:
        """Uploading the same filename twice in the same session should reject the second."""
        mock_cu_client.begin_analyze_binary = AsyncMock(return_value=_make_mock_poller(pdf_analysis_result))
        provider = _make_provider(mock_client=mock_cu_client)

        # Turn 1: upload invoice.pdf
        msg1 = Message(
            role="user",
            contents=[
                Content.from_text("Analyze this"),
                _make_content_from_data(_SAMPLE_PDF_BYTES, "application/pdf", "invoice.pdf"),
            ],
        )
        context1 = _make_context([msg1])
        state: dict[str, Any] = {}
        session = AgentSession()

        await provider.before_run(agent=_make_mock_agent(), session=session, context=context1, state=state)
        assert "invoice.pdf" in state["documents"]
        assert state["documents"]["invoice.pdf"]["status"] == DocumentStatus.READY

        # Turn 2: upload invoice.pdf again (different content but same filename)
        msg2 = Message(
            role="user",
            contents=[
                Content.from_text("Analyze this too"),
                _make_content_from_data(b"different-content", "application/pdf", "invoice.pdf"),
            ],
        )
        context2 = _make_context([msg2])

        await provider.before_run(agent=_make_mock_agent(), session=session, context=context2, state=state)

        # Should still have only one document, not re-analyzed
        assert mock_cu_client.begin_analyze_binary.call_count == 1
        # Context messages should mention duplicate
        assert any("already uploaded" in m.text for msgs in context2.context_messages.values() for m in msgs)

    async def test_duplicate_in_same_turn_rejected(
        self,
        mock_cu_client: AsyncMock,
        pdf_analysis_result: AnalysisResult,
    ) -> None:
        """Two files with the same filename in the same turn: first wins, second rejected."""
        mock_cu_client.begin_analyze_binary = AsyncMock(return_value=_make_mock_poller(pdf_analysis_result))
        provider = _make_provider(mock_client=mock_cu_client)

        msg = Message(
            role="user",
            contents=[
                Content.from_text("Analyze both"),
                _make_content_from_data(_SAMPLE_PDF_BYTES, "application/pdf", "report.pdf"),
                _make_content_from_data(b"other-content", "application/pdf", "report.pdf"),
            ],
        )
        context = _make_context([msg])
        state: dict[str, Any] = {}
        session = AgentSession()

        await provider.before_run(agent=_make_mock_agent(), session=session, context=context, state=state)

        # Only analyzed once (first one wins)
        assert mock_cu_client.begin_analyze_binary.call_count == 1
        assert "report.pdf" in state["documents"]
        assert any("already uploaded" in m.text for msgs in context.context_messages.values() for m in msgs)


class TestBinaryStripping:
    async def test_supported_files_stripped(
        self,
        mock_cu_client: AsyncMock,
        pdf_analysis_result: AnalysisResult,
    ) -> None:
        mock_cu_client.begin_analyze_binary = AsyncMock(return_value=_make_mock_poller(pdf_analysis_result))
        provider = _make_provider(mock_client=mock_cu_client)

        msg = Message(
            role="user",
            contents=[
                Content.from_text("What's in here?"),
                _make_content_from_data(_SAMPLE_PDF_BYTES, "application/pdf", "doc.pdf"),
            ],
        )
        context = _make_context([msg])
        state: dict[str, Any] = {}
        session = AgentSession()

        await provider.before_run(agent=_make_mock_agent(), session=session, context=context, state=state)

        # PDF should be stripped; text should remain
        for m in context.input_messages:
            for c in m.contents:
                assert c.media_type != "application/pdf"
            assert any(c.text and "What's in here?" in c.text for c in m.contents)

    async def test_unsupported_files_left_in_place(self, mock_cu_client: AsyncMock) -> None:
        provider = _make_provider(mock_client=mock_cu_client)

        msg = Message(
            role="user",
            contents=[
                Content.from_text("What's in this zip?"),
                Content.from_data(
                    b"PK\x03\x04fake",
                    "application/zip",
                    additional_properties={"filename": "archive.zip"},
                ),
            ],
        )
        context = _make_context([msg])
        state: dict[str, Any] = {}
        session = AgentSession()

        await provider.before_run(agent=_make_mock_agent(), session=session, context=context, state=state)

        # Zip should NOT be stripped (unsupported)
        found_zip = False
        for m in context.input_messages:
            for c in m.contents:
                if c.media_type == "application/zip":
                    found_zip = True
        assert found_zip


# Real magic-byte headers for binary sniffing tests
_MP4_MAGIC = b"\x00\x00\x00\x1cftypisom" + b"\x00" * 250
_WAV_MAGIC = b"RIFF\x00\x00\x00\x00WAVE" + b"\x00" * 250
_MP3_MAGIC = b"ID3\x04\x00\x00" + b"\x00" * 250
_FLAC_MAGIC = b"fLaC\x00\x00\x00\x00" + b"\x00" * 250
_OGG_MAGIC = b"OggS\x00\x02" + b"\x00" * 250
_AVI_MAGIC = b"RIFF\x00\x00\x00\x00AVI " + b"\x00" * 250
_MOV_MAGIC = b"\x00\x00\x00\x14ftypqt  " + b"\x00" * 250


class TestMimeSniffing:
    """Tests for binary MIME sniffing via filetype when upstream MIME is unreliable."""

    async def test_octet_stream_mp4_detected_and_stripped(
        self,
        mock_cu_client: AsyncMock,
        pdf_analysis_result: AnalysisResult,
    ) -> None:
        """MP4 uploaded as application/octet-stream should be sniffed, corrected, and stripped."""
        mock_cu_client.begin_analyze_binary = AsyncMock(return_value=_make_mock_poller(pdf_analysis_result))
        provider = _make_provider(mock_client=mock_cu_client)

        msg = Message(
            role="user",
            contents=[
                Content.from_text("What's in this file?"),
                _make_content_from_data(_MP4_MAGIC, "application/octet-stream", "video.mp4"),
            ],
        )
        context = _make_context([msg])
        state: dict[str, Any] = {}
        session = AgentSession()

        await provider.before_run(agent=_make_mock_agent(), session=session, context=context, state=state)

        # MP4 should be stripped from input
        for m in context.input_messages:
            for c in m.contents:
                assert c.media_type != "application/octet-stream", "octet-stream content should be stripped"

        # CU should have been called
        assert mock_cu_client.begin_analyze_binary.called

    async def test_octet_stream_wav_detected_via_sniff(
        self,
        mock_cu_client: AsyncMock,
        pdf_analysis_result: AnalysisResult,
    ) -> None:
        """WAV uploaded as application/octet-stream should be detected via filetype sniffing."""
        mock_cu_client.begin_analyze_binary = AsyncMock(return_value=_make_mock_poller(pdf_analysis_result))
        provider = _make_provider(mock_client=mock_cu_client)

        msg = Message(
            role="user",
            contents=[
                Content.from_text("Transcribe"),
                _make_content_from_data(_WAV_MAGIC, "application/octet-stream", "audio.wav"),
            ],
        )
        context = _make_context([msg])
        state: dict[str, Any] = {}
        session = AgentSession()

        await provider.before_run(agent=_make_mock_agent(), session=session, context=context, state=state)

        # Should be detected and analyzed
        assert "audio.wav" in state["documents"]
        # The media_type should be corrected to audio/wav (via _MIME_ALIASES)
        assert state["documents"]["audio.wav"]["media_type"] == "audio/wav"

    async def test_octet_stream_mp3_detected_via_sniff(
        self,
        mock_cu_client: AsyncMock,
        pdf_analysis_result: AnalysisResult,
    ) -> None:
        """MP3 uploaded as application/octet-stream should be detected as audio/mpeg."""
        mock_cu_client.begin_analyze_binary = AsyncMock(return_value=_make_mock_poller(pdf_analysis_result))
        provider = _make_provider(mock_client=mock_cu_client)

        msg = Message(
            role="user",
            contents=[
                Content.from_text("Transcribe"),
                _make_content_from_data(_MP3_MAGIC, "application/octet-stream", "song.mp3"),
            ],
        )
        context = _make_context([msg])
        state: dict[str, Any] = {}
        session = AgentSession()

        await provider.before_run(agent=_make_mock_agent(), session=session, context=context, state=state)

        assert "song.mp3" in state["documents"]
        assert state["documents"]["song.mp3"]["media_type"] == "audio/mpeg"

    async def test_octet_stream_flac_alias_normalized(
        self,
        mock_cu_client: AsyncMock,
        pdf_analysis_result: AnalysisResult,
    ) -> None:
        """FLAC sniffed as audio/x-flac should be normalized to audio/flac."""
        mock_cu_client.begin_analyze_binary = AsyncMock(return_value=_make_mock_poller(pdf_analysis_result))
        provider = _make_provider(mock_client=mock_cu_client)

        msg = Message(
            role="user",
            contents=[
                Content.from_text("Transcribe"),
                _make_content_from_data(_FLAC_MAGIC, "application/octet-stream", "music.flac"),
            ],
        )
        context = _make_context([msg])
        state: dict[str, Any] = {}
        session = AgentSession()

        await provider.before_run(agent=_make_mock_agent(), session=session, context=context, state=state)

        assert "music.flac" in state["documents"]
        assert state["documents"]["music.flac"]["media_type"] == "audio/flac"

    async def test_octet_stream_unknown_binary_not_stripped(
        self,
        mock_cu_client: AsyncMock,
    ) -> None:
        """Unknown binary with application/octet-stream should NOT be stripped."""
        provider = _make_provider(mock_client=mock_cu_client)

        unknown_bytes = b"\x00\x01\x02\x03random garbage" + b"\x00" * 250
        msg = Message(
            role="user",
            contents=[
                Content.from_text("What is this?"),
                _make_content_from_data(unknown_bytes, "application/octet-stream", "mystery.bin"),
            ],
        )
        context = _make_context([msg])
        state: dict[str, Any] = {}
        session = AgentSession()

        await provider.before_run(agent=_make_mock_agent(), session=session, context=context, state=state)

        # Unknown file should NOT be stripped
        found_octet = False
        for m in context.input_messages:
            for c in m.contents:
                if c.media_type == "application/octet-stream":
                    found_octet = True
        assert found_octet

    async def test_missing_mime_falls_back_to_filename(
        self,
        mock_cu_client: AsyncMock,
        pdf_analysis_result: AnalysisResult,
    ) -> None:
        """Content with empty MIME but a .mp4 filename should be detected via mimetypes fallback."""
        mock_cu_client.begin_analyze_binary = AsyncMock(return_value=_make_mock_poller(pdf_analysis_result))
        provider = _make_provider(mock_client=mock_cu_client)

        # Use garbage binary (filetype won't detect) but filename has .mp4
        garbage = b"\x00" * 300
        content = Content.from_data(garbage, "", additional_properties={"filename": "recording.mp4"})
        msg = Message(
            role="user",
            contents=[Content.from_text("Analyze"), content],
        )
        context = _make_context([msg])
        state: dict[str, Any] = {}
        session = AgentSession()

        await provider.before_run(agent=_make_mock_agent(), session=session, context=context, state=state)

        # Should be detected via filename and analyzed
        assert "recording.mp4" in state["documents"]

    async def test_correct_mime_not_sniffed(
        self,
        mock_cu_client: AsyncMock,
        pdf_analysis_result: AnalysisResult,
    ) -> None:
        """Files with correct MIME type should go through fast path without sniffing."""
        mock_cu_client.begin_analyze_binary = AsyncMock(return_value=_make_mock_poller(pdf_analysis_result))
        provider = _make_provider(mock_client=mock_cu_client)

        msg = Message(
            role="user",
            contents=[
                Content.from_text("Analyze"),
                _make_content_from_data(_SAMPLE_PDF_BYTES, "application/pdf", "doc.pdf"),
            ],
        )
        context = _make_context([msg])
        state: dict[str, Any] = {}
        session = AgentSession()

        await provider.before_run(agent=_make_mock_agent(), session=session, context=context, state=state)

        assert "doc.pdf" in state["documents"]
        assert state["documents"]["doc.pdf"]["media_type"] == "application/pdf"

    async def test_sniffed_video_uses_correct_analyzer(
        self,
        mock_cu_client: AsyncMock,
        pdf_analysis_result: AnalysisResult,
    ) -> None:
        """MP4 sniffed from octet-stream should use prebuilt-videoSearch analyzer."""
        mock_cu_client.begin_analyze_binary = AsyncMock(return_value=_make_mock_poller(pdf_analysis_result))
        provider = _make_provider(mock_client=mock_cu_client)  # analyzer_id=None → auto-detect

        msg = Message(
            role="user",
            contents=[
                Content.from_text("What's in this video?"),
                _make_content_from_data(_MP4_MAGIC, "application/octet-stream", "demo.mp4"),
            ],
        )
        context = _make_context([msg])
        state: dict[str, Any] = {}
        session = AgentSession()

        await provider.before_run(agent=_make_mock_agent(), session=session, context=context, state=state)

        assert state["documents"]["demo.mp4"]["analyzer_id"] == "prebuilt-videoSearch"


class TestErrorHandling:
    async def test_cu_service_error(self, mock_cu_client: AsyncMock) -> None:
        mock_cu_client.begin_analyze_binary = AsyncMock(
            return_value=_make_failing_poller(RuntimeError("Service unavailable"))
        )
        provider = _make_provider(mock_client=mock_cu_client)

        msg = Message(
            role="user",
            contents=[
                Content.from_text("Analyze this"),
                _make_content_from_data(_SAMPLE_PDF_BYTES, "application/pdf", "error.pdf"),
            ],
        )
        context = _make_context([msg])
        state: dict[str, Any] = {}
        session = AgentSession()

        await provider.before_run(agent=_make_mock_agent(), session=session, context=context, state=state)

        assert state["documents"]["error.pdf"]["status"] == DocumentStatus.FAILED
        assert "Service unavailable" in (state["documents"]["error.pdf"]["error"] or "")

    async def test_lazy_initialization_on_before_run(self) -> None:
        """before_run works with eagerly-initialized client."""
        provider = ContentUnderstandingContextProvider(
            endpoint="https://test.cognitiveservices.azure.com/",
            credential=AsyncMock(),
        )
        assert provider._client is not None

        mock_client = AsyncMock()
        mock_client.begin_analyze_binary = AsyncMock(
            side_effect=Exception("mock error"),
        )
        provider._client = mock_client  # type: ignore[assignment]

        msg = Message(
            role="user",
            contents=[
                Content.from_text("Analyze this"),
                _make_content_from_data(_SAMPLE_PDF_BYTES, "application/pdf", "doc.pdf"),
            ],
        )
        context = _make_context([msg])
        state: dict[str, Any] = {}
        session = AgentSession()

        await provider.before_run(agent=_make_mock_agent(), session=session, context=context, state=state)
        # Client should still be set
        assert provider._client is not None


class TestMultiModalFixtures:
    def test_pdf_fixture_loads(self, pdf_analysis_result: AnalysisResult) -> None:
        provider = _make_provider()
        result = provider._extract_sections(pdf_analysis_result)
        assert "markdown" in result
        assert "Contoso" in str(result["markdown"])

    def test_audio_fixture_loads(self, audio_analysis_result: AnalysisResult) -> None:
        provider = _make_provider()
        result = provider._extract_sections(audio_analysis_result)
        assert "markdown" in result
        assert "Call Center" in str(result["markdown"])

    def test_video_fixture_loads(self, video_analysis_result: AnalysisResult) -> None:
        provider = _make_provider()
        result = provider._extract_sections(video_analysis_result)
        assert "markdown" in result
        # All 3 segments should be concatenated at top level (for file_search)
        md = str(result["markdown"])
        assert "Contoso Product Demo" in md
        assert "real-time monitoring" in md
        assert "contoso.com/cloud-manager" in md
        # Duration should span all segments: (42000 - 1000) / 1000 = 41.0
        assert result.get("duration_seconds") == 41.0
        # kind from first segment
        assert result.get("kind") == "audioVisual"
        # resolution from first segment
        assert result.get("resolution") == "640x480"
        # Multi-segment: fields should be in per-segment list, not merged at top level
        assert "fields" not in result  # no top-level fields for multi-segment
        segments = result.get("segments")
        assert isinstance(segments, list)
        assert len(segments) == 3
        # Each segment should have its own fields and time range
        seg0 = segments[0]
        assert "fields" in seg0
        assert "Summary" in seg0["fields"]
        assert seg0.get("start_time_s") == 1.0
        assert seg0.get("end_time_s") == 14.0
        seg2 = segments[2]
        assert "fields" in seg2
        assert "Summary" in seg2["fields"]
        assert seg2.get("start_time_s") == 36.0
        assert seg2.get("end_time_s") == 42.0

    def test_image_fixture_loads(self, image_analysis_result: AnalysisResult) -> None:
        provider = _make_provider()
        result = provider._extract_sections(image_analysis_result)
        assert "markdown" in result

    def test_invoice_fixture_loads(self, invoice_analysis_result: AnalysisResult) -> None:
        provider = _make_provider()
        result = provider._extract_sections(invoice_analysis_result)
        assert "markdown" in result
        assert "fields" in result
        fields = result["fields"]
        assert isinstance(fields, dict)
        assert "VendorName" in fields
        # Single-segment: should NOT have segments key
        assert "segments" not in result


class TestFormatResult:
    def test_format_includes_markdown_and_fields(self) -> None:
        result: dict[str, object] = {
            "markdown": "# Hello World",
            "fields": {"Name": {"type": "string", "value": "Test", "confidence": 0.9}},
        }
        formatted = format_result("test.pdf", result)

        assert 'Document analysis of "test.pdf"' in formatted
        assert "# Hello World" in formatted
        assert "Extracted Fields" in formatted
        assert '"Name"' in formatted

    def test_format_markdown_only(self) -> None:
        result: dict[str, object] = {"markdown": "# Just Text"}
        formatted = format_result("doc.pdf", result)

        assert "# Just Text" in formatted
        assert "Extracted Fields" not in formatted

    def test_format_multi_segment_video(self) -> None:
        """Multi-segment results should format each segment with its own content + fields."""
        result: dict[str, object] = {
            "kind": "audioVisual",
            "duration_seconds": 41.0,
            "resolution": "640x480",
            "markdown": "scene1\n\n---\n\nscene2",  # concatenated for file_search
            "segments": [
                {
                    "start_time_s": 1.0,
                    "end_time_s": 14.0,
                    "markdown": "Welcome to the Contoso demo.",
                    "fields": {
                        "Summary": {"type": "string", "value": "Product intro"},
                        "Speakers": {
                            "type": "object",
                            "value": {"count": 1, "names": ["Host"]},
                        },
                    },
                },
                {
                    "start_time_s": 15.0,
                    "end_time_s": 31.0,
                    "markdown": "Here we show real-time monitoring.",
                    "fields": {
                        "Summary": {"type": "string", "value": "Feature walkthrough"},
                        "Speakers": {
                            "type": "object",
                            "value": {"count": 2, "names": ["Host", "Engineer"]},
                        },
                    },
                },
            ],
        }
        formatted = format_result("demo.mp4", result)

        expected = (
            'Video analysis of "demo.mp4":\n'
            "Duration: 0:41 | Resolution: 640x480\n"
            "\n### Segment 1 (0:01 - 0:14)\n"
            "\n```markdown\nWelcome to the Contoso demo.\n```\n"
            "\n**Fields:**\n```json\n"
            "{\n"
            '  "Summary": {\n'
            '    "type": "string",\n'
            '    "value": "Product intro"\n'
            "  },\n"
            '  "Speakers": {\n'
            '    "type": "object",\n'
            '    "value": {\n'
            '      "count": 1,\n'
            '      "names": [\n'
            '        "Host"\n'
            "      ]\n"
            "    }\n"
            "  }\n"
            "}\n```\n"
            "\n### Segment 2 (0:15 - 0:31)\n"
            "\n```markdown\nHere we show real-time monitoring.\n```\n"
            "\n**Fields:**\n```json\n"
            "{\n"
            '  "Summary": {\n'
            '    "type": "string",\n'
            '    "value": "Feature walkthrough"\n'
            "  },\n"
            '  "Speakers": {\n'
            '    "type": "object",\n'
            '    "value": {\n'
            '      "count": 2,\n'
            '      "names": [\n'
            '        "Host",\n'
            '        "Engineer"\n'
            "      ]\n"
            "    }\n"
            "  }\n"
            "}\n```"
        )
        assert formatted == expected

        # Verify ordering: segment 1 markdown+fields appear before segment 2
        seg1_pos = formatted.index("Segment 1")
        seg2_pos = formatted.index("Segment 2")
        contoso_pos = formatted.index("Welcome to the Contoso demo.")
        monitoring_pos = formatted.index("Here we show real-time monitoring.")
        intro_pos = formatted.index("Product intro")
        walkthrough_pos = formatted.index("Feature walkthrough")
        host_only_pos = formatted.index('"count": 1')
        host_engineer_pos = formatted.index('"count": 2')
        assert (
            seg1_pos
            < contoso_pos
            < intro_pos
            < host_only_pos
            < seg2_pos
            < monitoring_pos
            < walkthrough_pos
            < host_engineer_pos
        )

    def test_format_single_segment_no_segments_key(self) -> None:
        """Single-segment results should NOT have segments key — flat format."""
        result: dict[str, object] = {
            "kind": "document",
            "markdown": "# Invoice content",
            "fields": {
                "VendorName": {"type": "string", "value": "Contoso", "confidence": 0.95},
                "ShippingAddress": {
                    "type": "object",
                    "value": {"street": "123 Main St", "city": "Redmond", "state": "WA"},
                    "confidence": 0.88,
                },
            },
        }
        formatted = format_result("invoice.pdf", result)

        expected = (
            'Document analysis of "invoice.pdf":\n'
            "\n## Content\n\n"
            "```markdown\n# Invoice content\n```\n"
            "\n## Extracted Fields\n\n"
            "```json\n"
            "{\n"
            '  "VendorName": {\n'
            '    "type": "string",\n'
            '    "value": "Contoso",\n'
            '    "confidence": 0.95\n'
            "  },\n"
            '  "ShippingAddress": {\n'
            '    "type": "object",\n'
            '    "value": {\n'
            '      "street": "123 Main St",\n'
            '      "city": "Redmond",\n'
            '      "state": "WA"\n'
            "    },\n"
            '    "confidence": 0.88\n'
            "  }\n"
            "}\n"
            "```"
        )
        assert formatted == expected

        # Verify ordering: header → markdown content → fields
        header_pos = formatted.index('Document analysis of "invoice.pdf"')
        content_header_pos = formatted.index("## Content")
        markdown_pos = formatted.index("# Invoice content")
        fields_header_pos = formatted.index("## Extracted Fields")
        vendor_pos = formatted.index("Contoso")
        address_pos = formatted.index("ShippingAddress")
        street_pos = formatted.index("123 Main St")
        assert (
            header_pos < content_header_pos < markdown_pos < fields_header_pos < vendor_pos < address_pos < street_pos
        )


class TestSupportedMediaTypes:
    def test_pdf_supported(self) -> None:
        assert "application/pdf" in SUPPORTED_MEDIA_TYPES

    def test_audio_supported(self) -> None:
        assert "audio/mp3" in SUPPORTED_MEDIA_TYPES
        assert "audio/wav" in SUPPORTED_MEDIA_TYPES

    def test_video_supported(self) -> None:
        assert "video/mp4" in SUPPORTED_MEDIA_TYPES

    def test_zip_not_supported(self) -> None:
        assert "application/zip" not in SUPPORTED_MEDIA_TYPES


class TestAnalyzerAutoDetection:
    """Verify _resolve_analyzer_id auto-selects the right analyzer by media type."""

    def test_explicit_analyzer_always_wins(self) -> None:
        provider = _make_provider(analyzer_id="prebuilt-invoice")
        assert provider._resolve_analyzer_id("audio/mp3") == "prebuilt-invoice"
        assert provider._resolve_analyzer_id("video/mp4") == "prebuilt-invoice"
        assert provider._resolve_analyzer_id("application/pdf") == "prebuilt-invoice"

    def test_auto_detect_pdf(self) -> None:
        provider = _make_provider()  # analyzer_id=None
        assert provider._resolve_analyzer_id("application/pdf") == "prebuilt-documentSearch"

    def test_auto_detect_image(self) -> None:
        provider = _make_provider()
        assert provider._resolve_analyzer_id("image/jpeg") == "prebuilt-documentSearch"
        assert provider._resolve_analyzer_id("image/png") == "prebuilt-documentSearch"

    def test_auto_detect_audio(self) -> None:
        provider = _make_provider()
        assert provider._resolve_analyzer_id("audio/mp3") == "prebuilt-audioSearch"
        assert provider._resolve_analyzer_id("audio/wav") == "prebuilt-audioSearch"
        assert provider._resolve_analyzer_id("audio/mpeg") == "prebuilt-audioSearch"

    def test_auto_detect_video(self) -> None:
        provider = _make_provider()
        assert provider._resolve_analyzer_id("video/mp4") == "prebuilt-videoSearch"
        assert provider._resolve_analyzer_id("video/webm") == "prebuilt-videoSearch"

    def test_auto_detect_unknown_falls_back_to_document(self) -> None:
        provider = _make_provider()
        assert provider._resolve_analyzer_id("application/octet-stream") == "prebuilt-documentSearch"


class TestFileSearchIntegration:
    _FILE_SEARCH_TOOL = {"type": "file_search", "vector_store_ids": ["vs_test123"]}

    def _make_mock_backend(self) -> AsyncMock:
        """Create a mock FileSearchBackend."""
        backend = AsyncMock()
        backend.upload_file = AsyncMock(return_value="file_test456")
        backend.delete_file = AsyncMock()
        return backend

    def _make_file_search_config(self, backend: AsyncMock | None = None) -> Any:
        from agent_framework_azure_contentunderstanding import FileSearchConfig

        return FileSearchConfig(
            backend=backend or self._make_mock_backend(),
            vector_store_id="vs_test123",
            file_search_tool=self._FILE_SEARCH_TOOL,
        )

    async def test_file_search_uploads_to_vector_store(
        self,
        mock_cu_client: AsyncMock,
        pdf_analysis_result: AnalysisResult,
    ) -> None:
        mock_backend = self._make_mock_backend()
        config = self._make_file_search_config(mock_backend)
        mock_cu_client.begin_analyze_binary = AsyncMock(
            return_value=_make_mock_poller(pdf_analysis_result),
        )
        provider = _make_provider(
            mock_client=mock_cu_client,
            file_search=config,
        )

        msg = Message(
            role="user",
            contents=[
                Content.from_text("Analyze this"),
                _make_content_from_data(_SAMPLE_PDF_BYTES, "application/pdf", "doc.pdf"),
            ],
        )
        context = _make_context([msg])
        state: dict[str, Any] = {}
        session = AgentSession()

        await provider.before_run(
            agent=_make_mock_agent(),
            session=session,
            context=context,
            state=state,
        )

        # File should be uploaded via backend
        mock_backend.upload_file.assert_called_once()
        call_args = mock_backend.upload_file.call_args
        assert call_args[0][0] == "vs_test123"  # vector_store_id
        assert call_args[0][1] == "doc.pdf.md"  # filename
        # file_search tool should be registered on context
        assert self._FILE_SEARCH_TOOL in context.tools

    async def test_file_search_no_content_injection(
        self,
        mock_cu_client: AsyncMock,
        pdf_analysis_result: AnalysisResult,
    ) -> None:
        """When file_search is enabled, full content should NOT be injected into context."""
        mock_cu_client.begin_analyze_binary = AsyncMock(
            return_value=_make_mock_poller(pdf_analysis_result),
        )
        provider = _make_provider(
            mock_client=mock_cu_client,
            file_search=self._make_file_search_config(),
        )

        msg = Message(
            role="user",
            contents=[
                Content.from_text("Analyze this"),
                _make_content_from_data(_SAMPLE_PDF_BYTES, "application/pdf", "doc.pdf"),
            ],
        )
        context = _make_context([msg])
        state: dict[str, Any] = {}
        session = AgentSession()

        await provider.before_run(
            agent=_make_mock_agent(),
            session=session,
            context=context,
            state=state,
        )

        # Context messages should NOT contain full document content
        # (file_search handles retrieval instead)
        for msgs in context.context_messages.values():
            for m in msgs:
                assert "Document Content" not in m.text

    async def test_cleanup_deletes_uploaded_files(
        self,
        mock_cu_client: AsyncMock,
        pdf_analysis_result: AnalysisResult,
    ) -> None:
        mock_backend = self._make_mock_backend()
        config = self._make_file_search_config(mock_backend)
        mock_cu_client.begin_analyze_binary = AsyncMock(
            return_value=_make_mock_poller(pdf_analysis_result),
        )
        provider = _make_provider(
            mock_client=mock_cu_client,
            file_search=config,
        )

        msg = Message(
            role="user",
            contents=[
                Content.from_text("Analyze this"),
                _make_content_from_data(_SAMPLE_PDF_BYTES, "application/pdf", "doc.pdf"),
            ],
        )
        context = _make_context([msg])
        state: dict[str, Any] = {}
        session = AgentSession()

        await provider.before_run(
            agent=_make_mock_agent(),
            session=session,
            context=context,
            state=state,
        )

        # Close should clean up uploaded files (not the vector store itself)
        await provider.close()
        mock_backend.delete_file.assert_called_once_with("file_test456")

    async def test_no_file_search_injects_content(
        self,
        mock_cu_client: AsyncMock,
        pdf_analysis_result: AnalysisResult,
    ) -> None:
        """Without file_search, full content should be injected (default behavior)."""
        mock_cu_client.begin_analyze_binary = AsyncMock(
            return_value=_make_mock_poller(pdf_analysis_result),
        )
        provider = _make_provider(mock_client=mock_cu_client)

        msg = Message(
            role="user",
            contents=[
                Content.from_text("Analyze this"),
                _make_content_from_data(_SAMPLE_PDF_BYTES, "application/pdf", "doc.pdf"),
            ],
        )
        context = _make_context([msg])
        state: dict[str, Any] = {}
        session = AgentSession()

        await provider.before_run(
            agent=_make_mock_agent(),
            session=session,
            context=context,
            state=state,
        )

        # Without file_search, content SHOULD be injected
        found_content = False
        for msgs in context.context_messages.values():
            for m in msgs:
                if "Document Content" in m.text or "Contoso" in m.text:
                    found_content = True
        assert found_content

    async def test_file_search_multiple_files(
        self,
        mock_cu_client: AsyncMock,
        pdf_analysis_result: AnalysisResult,
        audio_analysis_result: AnalysisResult,
    ) -> None:
        """Multiple files should each be uploaded to the vector store."""
        mock_backend = self._make_mock_backend()
        # Return different file IDs for each upload
        mock_backend.upload_file = AsyncMock(side_effect=["file_001", "file_002"])
        config = self._make_file_search_config(mock_backend)
        mock_cu_client.begin_analyze_binary = AsyncMock(
            side_effect=[
                _make_mock_poller(pdf_analysis_result),
                _make_mock_poller(audio_analysis_result),
            ],
        )
        provider = _make_provider(
            mock_client=mock_cu_client,
            file_search=config,
        )

        msg = Message(
            role="user",
            contents=[
                Content.from_text("Compare these"),
                _make_content_from_data(_SAMPLE_PDF_BYTES, "application/pdf", "doc.pdf"),
                _make_content_from_data(b"\x00audio-fake", "audio/mp3", "call.mp3"),
            ],
        )
        context = _make_context([msg])
        state: dict[str, Any] = {}
        session = AgentSession()

        await provider.before_run(agent=_make_mock_agent(), session=session, context=context, state=state)

        # Two files uploaded via backend
        assert mock_backend.upload_file.call_count == 2

    async def test_file_search_skips_empty_markdown(
        self,
        mock_cu_client: AsyncMock,
    ) -> None:
        """Upload should be skipped when CU returns no markdown content."""
        mock_backend = self._make_mock_backend()
        config = self._make_file_search_config(mock_backend)

        # Create a result with empty markdown
        empty_result = AnalysisResult({"contents": [{"markdown": "", "fields": {}}]})
        mock_cu_client.begin_analyze_binary = AsyncMock(
            return_value=_make_mock_poller(empty_result),
        )
        provider = _make_provider(
            mock_client=mock_cu_client,
            file_search=config,
        )

        msg = Message(
            role="user",
            contents=[
                Content.from_text("Analyze this"),
                _make_content_from_data(_SAMPLE_PDF_BYTES, "application/pdf", "empty.pdf"),
            ],
        )
        context = _make_context([msg])
        state: dict[str, Any] = {}
        session = AgentSession()

        await provider.before_run(agent=_make_mock_agent(), session=session, context=context, state=state)

        # No file should be uploaded (empty markdown)
        mock_backend.upload_file.assert_not_called()

    async def test_pending_resolution_uploads_to_vector_store(
        self,
        mock_cu_client: AsyncMock,
        pdf_analysis_result: AnalysisResult,
    ) -> None:
        """When a background task completes in file_search mode, content should be
        uploaded to the vector store — NOT injected into context messages."""
        mock_backend = self._make_mock_backend()
        config = self._make_file_search_config(mock_backend)
        provider = _make_provider(
            mock_client=mock_cu_client,
            file_search=config,
        )

        # Simulate a completed background analysis via continuation token
        mock_poller = _make_mock_poller(pdf_analysis_result)
        mock_poller.done = MagicMock(return_value=True)
        mock_cu_client.begin_analyze = AsyncMock(return_value=mock_poller)

        state: dict[str, Any] = {
            "_pending_tokens": {
                "report.pdf": {"continuation_token": "tok_fs", "analyzer_id": "prebuilt-documentSearch"}
            },
            "documents": {
                "report.pdf": {
                    "status": DocumentStatus.ANALYZING,
                    "filename": "report.pdf",
                    "media_type": "application/pdf",
                    "analyzer_id": "prebuilt-documentSearch",
                    "analyzed_at": None,
                    "analysis_duration_s": None,
                    "upload_duration_s": None,
                    "result": None,
                    "error": None,
                },
            },
        }

        msg = Message(role="user", contents=[Content.from_text("Is the report ready?")])
        context = _make_context([msg])
        session = AgentSession()

        await provider.before_run(agent=_make_mock_agent(), session=session, context=context, state=state)

        # Document should be ready
        assert state["documents"]["report.pdf"]["status"] == DocumentStatus.READY

        # Content should NOT be injected into context messages
        for msgs in context.context_messages.values():
            for m in msgs:
                assert "Document Content" not in m.text

        # Should be uploaded to vector store via backend
        mock_backend.upload_file.assert_called_once()

        # Context messages should mention file_search, not "provided above"
        all_msg_text = " ".join(m.text for msgs in context.context_messages.values() for m in msgs)
        assert "file_search" in all_msg_text or any("file_search" in instr for instr in context.instructions)
        assert "provided above" not in all_msg_text


class TestCloseCancel:
    async def test_close_cleans_up(self) -> None:
        """close() should close the CU client."""
        provider = _make_provider(mock_client=AsyncMock())

        await provider.close()

        # Client should be closed (no tasks to cancel — tokens are just strings)
        provider._client.close.assert_called_once()


class TestSessionIsolation:
    """Verify that per-session state (pending tasks, uploads) is isolated between sessions."""

    async def test_background_task_isolated_per_session(
        self,
        mock_cu_client: AsyncMock,
        pdf_analysis_result: AnalysisResult,
    ) -> None:
        """A background task from session A must not leak into session B."""
        mock_cu_client.begin_analyze_binary = AsyncMock(return_value=_make_slow_poller(pdf_analysis_result, delay=10.0))
        provider = _make_provider(mock_client=mock_cu_client, max_wait=0.1)

        # Session A: upload a file that times out → defers to background
        msg_a = Message(
            role="user",
            contents=[
                Content.from_text("Analyze this"),
                _make_content_from_data(_SAMPLE_PDF_BYTES, "application/pdf", "report.pdf"),
            ],
        )
        state_a: dict[str, Any] = {}
        context_a = _make_context([msg_a])
        await provider.before_run(agent=_make_mock_agent(), session=AgentSession(), context=context_a, state=state_a)

        # Session A should have a pending token
        assert "report.pdf" in state_a.get("_pending_tokens", {})

        # Session B: separate state, no pending tokens
        state_b: dict[str, Any] = {}
        msg_b = Message(role="user", contents=[Content.from_text("Hello")])
        context_b = _make_context([msg_b])
        await provider.before_run(agent=_make_mock_agent(), session=AgentSession(), context=context_b, state=state_b)

        # Session B must NOT see session A's pending token
        assert "_pending_tokens" not in state_b or "report.pdf" not in state_b.get("_pending_tokens", {})
        # Session B must NOT have session A's documents
        assert "report.pdf" not in state_b.get("documents", {})

    async def test_completed_task_resolves_in_correct_session(
        self,
        mock_cu_client: AsyncMock,
        pdf_analysis_result: AnalysisResult,
    ) -> None:
        """A completed background task should only inject content into its own session."""
        provider = _make_provider(mock_client=mock_cu_client)

        # Simulate completed analysis in session A via continuation token
        mock_poller = _make_mock_poller(pdf_analysis_result)
        mock_poller.done = MagicMock(return_value=True)
        mock_cu_client.begin_analyze = AsyncMock(return_value=mock_poller)

        state_a: dict[str, Any] = {
            "_pending_tokens": {
                "report.pdf": {"continuation_token": "tok_a", "analyzer_id": "prebuilt-documentSearch"}
            },
            "documents": {
                "report.pdf": {
                    "status": DocumentStatus.ANALYZING,
                    "filename": "report.pdf",
                    "media_type": "application/pdf",
                    "analyzer_id": "prebuilt-documentSearch",
                    "analyzed_at": None,
                    "analysis_duration_s": None,
                    "upload_duration_s": None,
                    "result": None,
                    "error": None,
                },
            },
        }
        state_b: dict[str, Any] = {}

        # Run session A — should resolve the task
        context_a = _make_context([Message(role="user", contents=[Content.from_text("Is it ready?")])])
        await provider.before_run(agent=_make_mock_agent(), session=AgentSession(), context=context_a, state=state_a)
        assert state_a["documents"]["report.pdf"]["status"] == DocumentStatus.READY

        # Run session B — must NOT have any documents or resolved content
        context_b = _make_context([Message(role="user", contents=[Content.from_text("Hello")])])
        await provider.before_run(agent=_make_mock_agent(), session=AgentSession(), context=context_b, state=state_b)
        assert "report.pdf" not in state_b.get("documents", {})
        # Session B context should have no document-related messages
        assert not any("report.pdf" in m.text for msgs in context_b.context_messages.values() for m in msgs)


class TestAnalyzerAutoDetectionE2E:
    """End-to-end: verify _analyze_file stores the resolved analyzer in DocumentEntry."""

    async def test_audio_file_uses_audio_analyzer(
        self,
        mock_cu_client: AsyncMock,
        audio_analysis_result: AnalysisResult,
    ) -> None:
        mock_cu_client.begin_analyze_binary = AsyncMock(
            return_value=_make_mock_poller(audio_analysis_result),
        )
        provider = _make_provider(mock_client=mock_cu_client)  # analyzer_id=None

        msg = Message(
            role="user",
            contents=[
                Content.from_text("Transcribe this"),
                _make_content_from_data(b"\x00audio", "audio/mp3", "call.mp3"),
            ],
        )
        context = _make_context([msg])
        state: dict[str, Any] = {}
        session = AgentSession()

        await provider.before_run(agent=_make_mock_agent(), session=session, context=context, state=state)

        assert state["documents"]["call.mp3"]["analyzer_id"] == "prebuilt-audioSearch"
        # CU client should have been called with the audio analyzer
        mock_cu_client.begin_analyze_binary.assert_called_once()
        call_args = mock_cu_client.begin_analyze_binary.call_args
        assert call_args[0][0] == "prebuilt-audioSearch"

    async def test_video_file_uses_video_analyzer(
        self,
        mock_cu_client: AsyncMock,
        video_analysis_result: AnalysisResult,
    ) -> None:
        mock_cu_client.begin_analyze_binary = AsyncMock(
            return_value=_make_mock_poller(video_analysis_result),
        )
        provider = _make_provider(mock_client=mock_cu_client)

        msg = Message(
            role="user",
            contents=[
                Content.from_text("Analyze this video"),
                _make_content_from_data(b"\x00video", "video/mp4", "demo.mp4"),
            ],
        )
        context = _make_context([msg])
        state: dict[str, Any] = {}
        session = AgentSession()

        await provider.before_run(agent=_make_mock_agent(), session=session, context=context, state=state)

        assert state["documents"]["demo.mp4"]["analyzer_id"] == "prebuilt-videoSearch"
        call_args = mock_cu_client.begin_analyze_binary.call_args
        assert call_args[0][0] == "prebuilt-videoSearch"

    async def test_pdf_file_uses_document_analyzer(
        self,
        mock_cu_client: AsyncMock,
        pdf_analysis_result: AnalysisResult,
    ) -> None:
        mock_cu_client.begin_analyze_binary = AsyncMock(
            return_value=_make_mock_poller(pdf_analysis_result),
        )
        provider = _make_provider(mock_client=mock_cu_client)

        msg = Message(
            role="user",
            contents=[
                Content.from_text("Read this"),
                _make_content_from_data(_SAMPLE_PDF_BYTES, "application/pdf", "report.pdf"),
            ],
        )
        context = _make_context([msg])
        state: dict[str, Any] = {}
        session = AgentSession()

        await provider.before_run(agent=_make_mock_agent(), session=session, context=context, state=state)

        assert state["documents"]["report.pdf"]["analyzer_id"] == "prebuilt-documentSearch"
        call_args = mock_cu_client.begin_analyze_binary.call_args
        assert call_args[0][0] == "prebuilt-documentSearch"

    async def test_explicit_override_ignores_media_type(
        self,
        mock_cu_client: AsyncMock,
        audio_analysis_result: AnalysisResult,
    ) -> None:
        """Explicit analyzer_id should override auto-detection even for audio."""
        mock_cu_client.begin_analyze_binary = AsyncMock(
            return_value=_make_mock_poller(audio_analysis_result),
        )
        provider = _make_provider(mock_client=mock_cu_client, analyzer_id="prebuilt-invoice")

        msg = Message(
            role="user",
            contents=[
                Content.from_text("Analyze"),
                _make_content_from_data(b"\x00audio", "audio/mp3", "call.mp3"),
            ],
        )
        context = _make_context([msg])
        state: dict[str, Any] = {}
        session = AgentSession()

        await provider.before_run(agent=_make_mock_agent(), session=session, context=context, state=state)

        assert state["documents"]["call.mp3"]["analyzer_id"] == "prebuilt-invoice"
        call_args = mock_cu_client.begin_analyze_binary.call_args
        assert call_args[0][0] == "prebuilt-invoice"

    async def test_per_file_analyzer_overrides_provider_default(
        self,
        mock_cu_client: AsyncMock,
        pdf_analysis_result: AnalysisResult,
    ) -> None:
        """Per-file analyzer_id in additional_properties overrides provider-level default."""
        mock_cu_client.begin_analyze_binary = AsyncMock(
            return_value=_make_mock_poller(pdf_analysis_result),
        )
        # Provider default is prebuilt-documentSearch
        provider = _make_provider(
            mock_client=mock_cu_client,
            analyzer_id="prebuilt-documentSearch",
        )

        msg = Message(
            role="user",
            contents=[
                Content.from_text("Process this invoice"),
                Content.from_data(
                    _SAMPLE_PDF_BYTES,
                    "application/pdf",
                    # Per-file override to prebuilt-invoice
                    additional_properties={
                        "filename": "invoice.pdf",
                        "analyzer_id": "prebuilt-invoice",
                    },
                ),
            ],
        )
        context = _make_context([msg])
        state: dict[str, Any] = {}
        session = AgentSession()

        await provider.before_run(agent=_make_mock_agent(), session=session, context=context, state=state)

        # Per-file override should win
        assert state["documents"]["invoice.pdf"]["analyzer_id"] == "prebuilt-invoice"
        call_args = mock_cu_client.begin_analyze_binary.call_args
        assert call_args[0][0] == "prebuilt-invoice"


class TestWarningsExtraction:
    """Verify that CU analysis warnings are included in extracted output."""

    def test_warnings_included_when_present(self) -> None:
        """Non-empty warnings list should appear with code/message/target (RAI warnings)."""
        provider = _make_provider()
        fixture = {
            "contents": [
                {
                    "path": "input1",
                    "markdown": "Some content",
                    "kind": "document",
                }
            ],
            "warnings": [
                {
                    "code": "ContentFiltered",
                    "message": "Content was filtered due to Responsible AI policy.",
                    "target": "contents/0/markdown",
                },
                {
                    "code": "ContentFiltered",
                    "message": "Violence content detected and filtered.",
                },
            ],
        }
        result_obj = AnalysisResult(fixture)
        extracted = provider._extract_sections(result_obj)
        assert "warnings" in extracted
        warnings = extracted["warnings"]
        assert isinstance(warnings, list)
        assert len(warnings) == 2
        # First warning has code + message + target
        assert warnings[0]["code"] == "ContentFiltered"
        assert warnings[0]["message"] == "Content was filtered due to Responsible AI policy."
        assert warnings[0]["target"] == "contents/0/markdown"
        # Second warning has code + message but no target
        assert warnings[1]["code"] == "ContentFiltered"
        assert warnings[1]["message"] == "Violence content detected and filtered."
        assert "target" not in warnings[1]

    def test_warnings_omitted_when_empty(self, pdf_analysis_result: AnalysisResult) -> None:
        """Empty/None warnings should not appear in extracted result."""
        provider = _make_provider()
        extracted = provider._extract_sections(pdf_analysis_result)
        assert "warnings" not in extracted


class TestCategoryExtraction:
    """Verify that content-level category is included in extracted output."""

    def test_category_included_single_segment(self) -> None:
        """Category from classifier analyzer should appear in single-segment output."""
        provider = _make_provider()
        fixture = {
            "contents": [
                {
                    "path": "input1",
                    "markdown": "Contract text...",
                    "kind": "document",
                    "category": "Legal Contract",
                }
            ],
        }
        result_obj = AnalysisResult(fixture)
        extracted = provider._extract_sections(result_obj)
        assert extracted.get("category") == "Legal Contract"

    def test_category_in_multi_segment_video(self) -> None:
        """Each segment should carry its own category in multi-segment output."""
        provider = _make_provider()
        fixture = {
            "contents": [
                {
                    "path": "input1",
                    "kind": "audioVisual",
                    "startTimeMs": 0,
                    "endTimeMs": 30000,
                    "markdown": "Opening scene with product showcase.",
                    "category": "ProductDemo",
                    "fields": {
                        "Summary": {
                            "type": "string",
                            "valueString": "Product demo intro",
                        }
                    },
                },
                {
                    "path": "input1",
                    "kind": "audioVisual",
                    "startTimeMs": 30000,
                    "endTimeMs": 60000,
                    "markdown": "Customer testimonial segment.",
                    "category": "Testimonial",
                    "fields": {
                        "Summary": {
                            "type": "string",
                            "valueString": "Customer feedback",
                        }
                    },
                },
            ],
        }
        result_obj = AnalysisResult(fixture)
        extracted = provider._extract_sections(result_obj)

        # Top-level metadata
        assert extracted["kind"] == "audioVisual"
        assert extracted["duration_seconds"] == 60.0

        # Segments should have per-segment category
        segments = extracted["segments"]
        assert isinstance(segments, list)
        assert len(segments) == 2

        # First segment: ProductDemo
        assert segments[0]["category"] == "ProductDemo"
        assert segments[0]["start_time_s"] == 0.0
        assert segments[0]["end_time_s"] == 30.0
        assert segments[0]["markdown"] == "Opening scene with product showcase."
        assert "Summary" in segments[0]["fields"]

        # Second segment: Testimonial
        assert segments[1]["category"] == "Testimonial"
        assert segments[1]["start_time_s"] == 30.0
        assert segments[1]["end_time_s"] == 60.0
        assert segments[1]["markdown"] == "Customer testimonial segment."

        # Top-level concatenated markdown for file_search
        assert "Opening scene" in extracted["markdown"]
        assert "Customer testimonial" in extracted["markdown"]

    def test_category_omitted_when_none(self, pdf_analysis_result: AnalysisResult) -> None:
        """No category should be in output when analyzer doesn't classify."""
        provider = _make_provider()
        extracted = provider._extract_sections(pdf_analysis_result)
        assert "category" not in extracted


class TestContentRangeSupport:
    """Verify that content_range from additional_properties is passed to CU."""

    async def test_content_range_passed_to_begin_analyze(
        self,
        mock_cu_client: AsyncMock,
        pdf_analysis_result: AnalysisResult,
    ) -> None:
        """content_range in additional_properties should be forwarded to AnalysisInput."""
        from azure.ai.contentunderstanding.models import AnalysisInput

        mock_cu_client.begin_analyze = AsyncMock(return_value=_make_mock_poller(pdf_analysis_result))
        provider = _make_provider(mock_client=mock_cu_client)

        msg = Message(
            role="user",
            contents=[
                Content.from_text("Analyze pages 1-3"),
                Content.from_uri(
                    "https://example.com/report.pdf",
                    media_type="application/pdf",
                    additional_properties={"filename": "report.pdf", "content_range": "1-3"},
                ),
            ],
        )
        context = _make_context([msg])
        state: dict[str, Any] = {}
        session = AgentSession()

        await provider.before_run(agent=_make_mock_agent(), session=session, context=context, state=state)

        # Verify begin_analyze was called with AnalysisInput containing content_range
        mock_cu_client.begin_analyze.assert_called_once()
        call_kwargs = mock_cu_client.begin_analyze.call_args
        inputs_arg = call_kwargs.kwargs.get("inputs") or call_kwargs[1].get("inputs")
        assert inputs_arg is not None
        assert len(inputs_arg) == 1
        assert isinstance(inputs_arg[0], AnalysisInput)
        assert inputs_arg[0].content_range == "1-3"
        assert inputs_arg[0].url == "https://example.com/report.pdf"
