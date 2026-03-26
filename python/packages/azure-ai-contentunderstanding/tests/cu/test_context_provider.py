# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
import base64
import contextlib
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from agent_framework import Content, Message, SessionContext
from agent_framework._sessions import AgentSession
from azure.ai.contentunderstanding.models import AnalysisResult

from agent_framework_azure_ai_contentunderstanding import (
    AnalysisSection,
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
        assert provider.analyzer_id is None
        assert provider.max_wait == 5.0
        assert provider.output_sections == [AnalysisSection.MARKDOWN, AnalysisSection.FIELDS]
        assert provider.source_id == "content_understanding"

    def test_custom_values(self) -> None:
        provider = ContentUnderstandingContextProvider(
            endpoint="https://custom.cognitiveservices.azure.com/",
            credential=AsyncMock(),
            analyzer_id="prebuilt-invoice",
            max_wait=10.0,
            output_sections=[AnalysisSection.MARKDOWN],
            source_id="custom_cu",
        )
        assert provider.analyzer_id == "prebuilt-invoice"
        assert provider.max_wait == 10.0
        assert provider.output_sections == [AnalysisSection.MARKDOWN]
        assert provider.source_id == "custom_cu"

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
        result = await provider.__aenter__()
        assert result is provider

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

        assert state["documents"]["error.pdf"]["status"] == "failed"
        assert "Service unavailable" in (state["documents"]["error.pdf"]["error"] or "")

    async def test_client_created_in_init(self) -> None:
        """Client is created eagerly in __init__, not lazily."""
        provider = ContentUnderstandingContextProvider(
            endpoint="https://test.cognitiveservices.azure.com/",
            credential=AsyncMock(),
        )
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
        # All 3 segments should be concatenated
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
        # Fields merged across 3 segments: Summary appears 3 times
        fields = result.get("fields")
        assert isinstance(fields, dict)
        assert "Summary" in fields
        # Multi-segment field should be a list of per-segment entries
        summary = fields["Summary"]
        assert isinstance(summary, list)
        assert len(summary) == 3
        assert summary[0]["segment"] == 0
        assert summary[2]["segment"] == 2

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
    _MOCK_TOOL = {"type": "file_search", "vector_store_ids": ["vs_test123"]}

    def _make_mock_backend(self) -> AsyncMock:
        """Create a mock FileSearchBackend for file upload operations."""
        backend = AsyncMock()
        backend.upload_file = AsyncMock(return_value="file_test456")
        backend.delete_file = AsyncMock()
        return backend

    def _make_file_search_config(self, backend: AsyncMock | None = None) -> Any:
        from agent_framework_azure_ai_contentunderstanding import FileSearchConfig

        return FileSearchConfig(
            backend=backend or self._make_mock_backend(),
            vector_store_id="vs_test123",
            file_search_tool=self._MOCK_TOOL,
        )

    async def test_file_search_uploads_to_vector_store(
        self,
        mock_cu_client: AsyncMock,
        pdf_analysis_result: AnalysisResult,
    ) -> None:
        mock_backend = self._make_mock_backend()
        mock_cu_client.begin_analyze_binary = AsyncMock(
            return_value=_make_mock_poller(pdf_analysis_result),
        )
        provider = _make_provider(
            mock_client=mock_cu_client,
            file_search=self._make_file_search_config(mock_backend),
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

        # File should be uploaded
        mock_backend.upload_file.assert_called_once()
        # file_search tool should be registered on context
        file_search_tools = [t for t in context.tools if isinstance(t, dict) and t.get("type") == "file_search"]
        assert len(file_search_tools) == 1
        assert file_search_tools[0]["vector_store_ids"] == ["vs_test123"]

    async def test_file_search_no_content_injection(
        self,
        mock_cu_client: AsyncMock,
        pdf_analysis_result: AnalysisResult,
    ) -> None:
        """When file_search is enabled, full content should NOT be injected into context."""
        mock_backend = self._make_mock_backend()
        mock_cu_client.begin_analyze_binary = AsyncMock(
            return_value=_make_mock_poller(pdf_analysis_result),
        )
        provider = _make_provider(
            mock_client=mock_cu_client,
            file_search=self._make_file_search_config(mock_backend),
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

    async def test_cleanup_deletes_vector_store(
        self,
        mock_cu_client: AsyncMock,
        pdf_analysis_result: AnalysisResult,
    ) -> None:
        mock_backend = self._make_mock_backend()
        mock_cu_client.begin_analyze_binary = AsyncMock(
            return_value=_make_mock_poller(pdf_analysis_result),
        )
        provider = _make_provider(
            mock_client=mock_cu_client,
            file_search=self._make_file_search_config(mock_backend),
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

        # Close should clean up uploaded files (not the vector store)
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
        mock_cu_client.begin_analyze_binary = AsyncMock(
            side_effect=[
                _make_mock_poller(pdf_analysis_result),
                _make_mock_poller(audio_analysis_result),
            ],
        )
        provider = _make_provider(
            mock_client=mock_cu_client,
            file_search=self._make_file_search_config(mock_backend),
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

        # Two files uploaded
        mock_backend.create_vector_store.assert_not_called()
        assert mock_backend.upload_file.call_count == 2

    async def test_file_search_skips_empty_markdown(
        self,
        mock_cu_client: AsyncMock,
    ) -> None:
        """Upload should be skipped when CU returns no markdown content."""
        mock_backend = self._make_mock_backend()

        # Create a result with empty markdown
        empty_result = AnalysisResult({"contents": [{"markdown": "", "fields": {}}]})
        mock_cu_client.begin_analyze_binary = AsyncMock(
            return_value=_make_mock_poller(empty_result),
        )
        provider = _make_provider(
            mock_client=mock_cu_client,
            file_search=self._make_file_search_config(mock_backend),
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
        provider = _make_provider(
            mock_client=mock_cu_client,
            file_search=self._make_file_search_config(mock_backend),
        )

        # Simulate a completed background task
        async def return_result() -> AnalysisResult:
            return pdf_analysis_result

        task: asyncio.Task[AnalysisResult] = asyncio.ensure_future(return_result())
        await asyncio.sleep(0.01)
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

        # Document should be ready
        assert state["documents"]["report.pdf"]["status"] == "ready"

        # Content should NOT be injected into context messages
        for msgs in context.context_messages.values():
            for m in msgs:
                assert "Document Content" not in m.text

        # Should be uploaded to vector store instead
        mock_backend.upload_file.assert_called_once()

        # Instructions should mention file_search, not "provided above"
        assert any("file_search" in instr for instr in context.instructions)
        assert not any("provided above" in instr for instr in context.instructions)


class TestClientCreatedInInit:
    def test_client_is_not_none_after_init(self) -> None:
        """Client is created eagerly in __init__."""
        provider = ContentUnderstandingContextProvider(
            endpoint="https://test.cognitiveservices.azure.com/",
            credential=AsyncMock(),
        )
        assert provider._client is not None


class TestCloseCancel:
    async def test_close_cancels_pending_tasks(self) -> None:
        """close() should cancel any pending background analysis tasks."""
        provider = _make_provider(mock_client=AsyncMock())

        # Simulate a long-running pending task
        async def slow() -> None:
            await asyncio.sleep(100)

        task = asyncio.create_task(slow())
        provider._pending_tasks["big_file.pdf"] = task  # type: ignore[assignment]

        await provider.close()

        # Allow the cancellation to propagate
        with contextlib.suppress(asyncio.CancelledError):
            await task

        assert task.cancelled()
        assert len(provider._pending_tasks) == 0


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
