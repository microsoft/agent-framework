# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
import base64
import contextlib
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from agent_framework import Content, Message, SessionContext
from agent_framework._sessions import AgentSession
from azure.ai.contentunderstanding.models import AnalysisResult

from agent_framework_azure_ai_contentunderstanding import (
    AnalysisSection,
    ContentLimits,
    ContentUnderstandingContextProvider,
)
from agent_framework_azure_ai_contentunderstanding._context_provider import SUPPORTED_MEDIA_TYPES

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SAMPLE_PDF_BYTES = b"%PDF-1.4 fake content for testing"


def _make_mock_poller(result: AnalysisResult) -> AsyncMock:
    """Create a mock poller that returns the given result immediately."""
    poller = AsyncMock()
    poller.result = AsyncMock(return_value=result)
    return poller


def _make_slow_poller(result: AnalysisResult, delay: float = 10.0) -> AsyncMock:
    """Create a mock poller that simulates a timeout then eventually returns."""
    poller = AsyncMock()

    async def slow_result() -> AnalysisResult:
        await asyncio.sleep(delay)
        return result

    poller.result = slow_result
    return poller


def _make_failing_poller(error: Exception) -> AsyncMock:
    """Create a mock poller that raises an exception."""
    poller = AsyncMock()
    poller.result = AsyncMock(side_effect=error)
    return poller


def _make_data_uri(data: bytes, media_type: str) -> str:
    encoded = base64.b64encode(data).encode("ascii") if isinstance(data, bytes) else data
    if isinstance(encoded, bytes):
        encoded = encoded.decode("ascii")
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
        assert provider.analyzer_id == "prebuilt-documentSearch"
        assert provider.max_wait == 5.0
        assert provider.output_sections == [AnalysisSection.MARKDOWN, AnalysisSection.FIELDS]
        assert provider.content_limits is not None
        assert provider.source_id == "content_understanding"

    def test_custom_values(self) -> None:
        provider = ContentUnderstandingContextProvider(
            endpoint="https://custom.cognitiveservices.azure.com/",
            credential=AsyncMock(),
            analyzer_id="prebuilt-invoice",
            max_wait=10.0,
            output_sections=[AnalysisSection.MARKDOWN],
            content_limits=ContentLimits(max_pages=50),
            source_id="custom_cu",
        )
        assert provider.analyzer_id == "prebuilt-invoice"
        assert provider.max_wait == 10.0
        assert provider.output_sections == [AnalysisSection.MARKDOWN]
        assert provider.content_limits is not None
        assert provider.content_limits.max_pages == 50
        assert provider.source_id == "custom_cu"

    def test_no_content_limits(self) -> None:
        provider = ContentUnderstandingContextProvider(
            endpoint="https://test.cognitiveservices.azure.com/",
            credential=AsyncMock(),
            content_limits=None,
        )
        assert provider.content_limits is None

    def test_max_wait_none(self) -> None:
        provider = ContentUnderstandingContextProvider(
            endpoint="https://test.cognitiveservices.azure.com/",
            credential=AsyncMock(),
            max_wait=None,
        )
        assert provider.max_wait is None


class TestAsyncContextManager:
    async def test_aenter_returns_self(self) -> None:
        provider = ContentUnderstandingContextProvider(
            endpoint="https://test.cognitiveservices.azure.com/",
            credential=AsyncMock(),
        )
        with patch(
            "agent_framework_azure_ai_contentunderstanding._context_provider.ContentUnderstandingClient",
        ) as mock_cls:
            mock_instance = AsyncMock()
            mock_cls.return_value = mock_instance
            result = await provider.__aenter__()
            assert result is provider
            await provider.__aexit__(None, None, None)
            mock_instance.close.assert_called_once()

    async def test_aexit_closes_client(self) -> None:
        provider = ContentUnderstandingContextProvider(
            endpoint="https://test.cognitiveservices.azure.com/",
            credential=AsyncMock(),
        )
        mock_client = AsyncMock()
        provider._client = mock_client  # type: ignore[assignment]
        await provider.__aexit__(None, None, None)
        mock_client.close.assert_called_once()
        assert provider._client is None


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
        assert state["documents"]["invoice.pdf"]["status"] == "ready"

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
        assert state["documents"]["report.pdf"]["status"] == "ready"

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
        assert state["documents"]["doc1.pdf"]["status"] == "ready"
        assert state["documents"]["chart.png"]["status"] == "ready"


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

        assert state["documents"]["big_doc.pdf"]["status"] == "pending"
        assert "big_doc.pdf" in provider._pending_tasks

        # Instructions should mention analyzing
        assert any("being analyzed" in instr for instr in context.instructions)

        # Clean up the background task
        provider._pending_tasks["big_doc.pdf"].cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await provider._pending_tasks["big_doc.pdf"]


class TestBeforeRunPendingResolution:
    async def test_pending_completes_on_next_turn(
        self,
        mock_cu_client: AsyncMock,
        pdf_analysis_result: AnalysisResult,
    ) -> None:
        provider = _make_provider(mock_client=mock_cu_client)

        # Simulate a completed background task
        async def return_result() -> AnalysisResult:
            return pdf_analysis_result

        task: asyncio.Task[AnalysisResult] = asyncio.ensure_future(return_result())
        await asyncio.sleep(0.01)  # Let task complete
        provider._pending_tasks["report.pdf"] = task

        state: dict[str, Any] = {
            "documents": {
                "report.pdf": {
                    "status": "pending",
                    "filename": "report.pdf",
                    "media_type": "application/pdf",
                    "analyzer_id": "prebuilt-documentSearch",
                    "analyzed_at": None,
                    "result": None,
                    "error": None,
                },
            },
        }

        msg = Message(role="user", contents=[Content.from_text("Is the report ready?")])
        context = _make_context([msg])
        session = AgentSession()

        await provider.before_run(agent=_make_mock_agent(), session=session, context=context, state=state)

        assert state["documents"]["report.pdf"]["status"] == "ready"
        assert state["documents"]["report.pdf"]["result"] is not None
        assert "report.pdf" not in provider._pending_tasks


class TestBeforeRunPendingFailure:
    async def test_pending_task_failure_updates_state(
        self,
        mock_cu_client: AsyncMock,
    ) -> None:
        provider = _make_provider(mock_client=mock_cu_client)

        async def failing_task() -> AnalysisResult:
            raise RuntimeError("CU service unavailable")

        task: asyncio.Task[AnalysisResult] = asyncio.ensure_future(failing_task())
        await asyncio.sleep(0.01)  # Let task fail
        provider._pending_tasks["bad_doc.pdf"] = task

        state: dict[str, Any] = {
            "documents": {
                "bad_doc.pdf": {
                    "status": "pending",
                    "filename": "bad_doc.pdf",
                    "media_type": "application/pdf",
                    "analyzer_id": "prebuilt-documentSearch",
                    "analyzed_at": None,
                    "result": None,
                    "error": None,
                },
            },
        }

        msg = Message(role="user", contents=[Content.from_text("Check status")])
        context = _make_context([msg])
        session = AgentSession()

        await provider.before_run(agent=_make_mock_agent(), session=session, context=context, state=state)

        assert state["documents"]["bad_doc.pdf"]["status"] == "failed"
        assert "CU service unavailable" in (state["documents"]["bad_doc.pdf"]["error"] or "")


class TestDocumentKeyDerivation:
    def test_filename_from_additional_properties(self) -> None:
        content = _make_content_from_data(_SAMPLE_PDF_BYTES, "application/pdf", "my_report.pdf")
        key = ContentUnderstandingContextProvider._derive_doc_key(content)
        assert key == "my_report.pdf"

    def test_url_basename(self) -> None:
        content = Content.from_uri("https://example.com/docs/annual_report.pdf", media_type="application/pdf")
        key = ContentUnderstandingContextProvider._derive_doc_key(content)
        assert key == "annual_report.pdf"

    def test_content_hash_fallback(self) -> None:
        content = Content.from_data(_SAMPLE_PDF_BYTES, "application/pdf")
        key = ContentUnderstandingContextProvider._derive_doc_key(content)
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
        assert state["documents"]["doc.pdf"]["status"] == "ready"


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
        assert parsed[0]["status"] == "ready"


class TestGetDocumentTool:
    async def test_retrieves_cached_content(
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

        # Find the get_analyzed_document tool
        get_tool = None
        for tool in context.tools:
            if getattr(tool, "name", None) == "get_analyzed_document":
                get_tool = tool
                break

        assert get_tool is not None
        result = get_tool.func("test.pdf")  # type: ignore[union-attr]
        assert "Contoso" in result or "Financial" in result

    async def test_not_found(
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

        get_tool = None
        for tool in context.tools:
            if getattr(tool, "name", None) == "get_analyzed_document":
                get_tool = tool
                break

        assert get_tool is not None
        result = get_tool.func("nonexistent.pdf")  # type: ignore[union-attr]
        assert "No document found" in result


class TestOutputFiltering:
    def test_default_markdown_and_fields(self, pdf_analysis_result: AnalysisResult) -> None:
        provider = _make_provider()
        result = provider._extract_sections(pdf_analysis_result)

        assert "markdown" in result
        assert "fields" in result
        assert "Contoso" in str(result["markdown"])

    def test_markdown_only(self, pdf_analysis_result: AnalysisResult) -> None:
        provider = _make_provider(output_sections=[AnalysisSection.MARKDOWN])
        result = provider._extract_sections(pdf_analysis_result)

        assert "markdown" in result
        assert "fields" not in result

    def test_fields_only(self, invoice_analysis_result: AnalysisResult) -> None:
        provider = _make_provider(output_sections=[AnalysisSection.FIELDS])
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


class TestContentLimits:
    async def test_over_limit_file_size(self, mock_cu_client: AsyncMock) -> None:
        # Use a very small limit that the test PDF bytes will exceed
        provider = _make_provider(
            mock_client=mock_cu_client,
            content_limits=ContentLimits(max_file_size_mb=0.00001),  # ~10 bytes = reject everything
        )

        msg = Message(
            role="user",
            contents=[
                Content.from_text("Analyze this"),
                _make_content_from_data(_SAMPLE_PDF_BYTES, "application/pdf", "big.pdf"),
            ],
        )
        context = _make_context([msg])
        state: dict[str, Any] = {}
        session = AgentSession()

        await provider.before_run(agent=_make_mock_agent(), session=session, context=context, state=state)

        assert state["documents"]["big.pdf"]["status"] == "failed"
        assert "exceeds size limit" in (state["documents"]["big.pdf"]["error"] or "")

    async def test_no_limits_allows_any_size(
        self,
        mock_cu_client: AsyncMock,
        pdf_analysis_result: AnalysisResult,
    ) -> None:
        mock_cu_client.begin_analyze_binary = AsyncMock(return_value=_make_mock_poller(pdf_analysis_result))
        provider = _make_provider(mock_client=mock_cu_client, content_limits=None)

        msg = Message(
            role="user",
            contents=[
                Content.from_text("Analyze this"),
                _make_content_from_data(_SAMPLE_PDF_BYTES, "application/pdf", "any_size.pdf"),
            ],
        )
        context = _make_context([msg])
        state: dict[str, Any] = {}
        session = AgentSession()

        await provider.before_run(agent=_make_mock_agent(), session=session, context=context, state=state)

        assert state["documents"]["any_size.pdf"]["status"] == "ready"


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

        assert state["documents"]["error.pdf"]["status"] == "failed"
        assert "Service unavailable" in (state["documents"]["error.pdf"]["error"] or "")

    async def test_not_initialized_raises(self) -> None:
        provider = ContentUnderstandingContextProvider(
            endpoint="https://test.cognitiveservices.azure.com/",
            credential=AsyncMock(),
        )
        # provider._client is None since we never called __aenter__

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

        with pytest.raises(RuntimeError, match="not initialized"):
            await provider.before_run(agent=_make_mock_agent(), session=session, context=context, state=state)


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
        assert "Product Demo" in str(result["markdown"])

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


class TestFormatResult:
    def test_format_includes_markdown_and_fields(self) -> None:
        result: dict[str, object] = {
            "markdown": "# Hello World",
            "fields": {"Name": {"type": "string", "value": "Test", "confidence": 0.9}},
        }
        formatted = ContentUnderstandingContextProvider._format_result("test.pdf", result)

        assert 'Document analysis of "test.pdf"' in formatted
        assert "# Hello World" in formatted
        assert "Extracted Fields" in formatted
        assert '"Name"' in formatted

    def test_format_markdown_only(self) -> None:
        result: dict[str, object] = {"markdown": "# Just Text"}
        formatted = ContentUnderstandingContextProvider._format_result("doc.pdf", result)

        assert "# Just Text" in formatted
        assert "Extracted Fields" not in formatted


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
