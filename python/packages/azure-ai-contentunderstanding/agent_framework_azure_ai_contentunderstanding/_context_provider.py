# Copyright (c) Microsoft. All rights reserved.

"""Azure Content Understanding context provider using BaseContextProvider.

This module provides ``ContentUnderstandingContextProvider``, built on the
:class:`BaseContextProvider` hooks pattern.  It automatically detects file
attachments, analyzes them via the Azure Content Understanding API, and
injects structured results into the LLM context.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import mimetypes
import sys
import time
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, ClassVar, TypedDict, cast

import filetype
from agent_framework import (
    AGENT_FRAMEWORK_USER_AGENT,
    BaseContextProvider,
    Content,
    FunctionTool,
    Message,
    SessionContext,
)
from agent_framework._sessions import AgentSession
from agent_framework._settings import load_settings
from azure.ai.contentunderstanding.aio import ContentUnderstandingClient
from azure.ai.contentunderstanding.models import AnalysisResult
from azure.core.credentials import AzureKeyCredential
from azure.core.credentials_async import AsyncTokenCredential

if sys.version_info >= (3, 11):
    from typing import Self  # pragma: no cover
else:
    from typing_extensions import Self  # pragma: no cover

if TYPE_CHECKING:
    from agent_framework._agents import SupportsAgentRun

from ._models import AnalysisSection, DocumentEntry, DocumentStatus, FileSearchConfig

logger = logging.getLogger("agent_framework.azure_ai_contentunderstanding")

AzureCredentialTypes = AzureKeyCredential | AsyncTokenCredential

# MIME types used to match against Content.media_type for routing files to CU analysis.
# Only files whose media_type is set by the client and matches this set will be processed;
# files without a media_type are ignored.
#
# Supported input file types:
# https://learn.microsoft.com/azure/ai-services/content-understanding/service-limits#input-file-limits
SUPPORTED_MEDIA_TYPES: frozenset[str] = frozenset({
    # Documents and images
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/tiff",
    "image/bmp",
    "image/heif",
    "image/heic",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    # Text
    "text/plain",
    "text/html",
    "text/markdown",
    "text/rtf",
    "text/xml",
    "application/xml",
    "message/rfc822",
    "application/vnd.ms-outlook",
    # Audio
    "audio/wav",
    "audio/mpeg",
    "audio/mp3",
    "audio/mp4",
    "audio/m4a",
    "audio/flac",
    "audio/ogg",
    "audio/opus",
    "audio/webm",
    "audio/x-ms-wma",
    "audio/aac",
    "audio/amr",
    "audio/3gpp",
    # Video
    "video/mp4",
    "video/quicktime",
    "video/x-msvideo",
    "video/webm",
    "video/x-flv",
    "video/x-ms-wmv",
    "video/x-ms-asf",
    "video/x-matroska",
})

# Mapping from filetype's MIME output to our canonical SUPPORTED_MEDIA_TYPES values.
# filetype uses some x-prefixed variants that differ from our set.
_MIME_ALIASES: dict[str, str] = {
    "audio/x-wav": "audio/wav",
    "audio/x-flac": "audio/flac",
    "audio/mp4": "audio/m4a",
    "video/x-m4v": "video/mp4",
    "video/x-matroska": "video/webm",
}

# Mapping from media type prefix to the appropriate prebuilt CU analyzer.
# Used when analyzer_id is None (auto-detect mode).
_MEDIA_TYPE_ANALYZER_MAP: dict[str, str] = {
    "audio/": "prebuilt-audioSearch",
    "video/": "prebuilt-videoSearch",
}
_DEFAULT_ANALYZER: str = "prebuilt-documentSearch"


class ContentUnderstandingSettings(TypedDict, total=False):
    """Settings for ContentUnderstandingContextProvider with auto-loading from environment.

    Settings are resolved in this order: explicit keyword arguments, values from an
    explicitly provided .env file, then environment variables with the prefix
    ``AZURE_CONTENTUNDERSTANDING_``.

    Keys:
        endpoint: Azure AI Foundry endpoint URL.
            Can be set via environment variable ``AZURE_CONTENTUNDERSTANDING_ENDPOINT``.
    """

    endpoint: str | None


class ContentUnderstandingContextProvider(BaseContextProvider):
    """Context provider that analyzes file attachments using Azure Content Understanding.

    Automatically detects supported file attachments in the agent's input,
    analyzes them via CU, and injects the structured results (markdown, fields)
    into the LLM context. Supports multiple documents per session with background
    processing for long-running analyses. Optionally integrates with a vector
    store backend for ``file_search``-based RAG retrieval on LLM clients that
    support it.

    Args:
        endpoint: Azure AI Foundry endpoint URL
            (e.g., ``"https://<your-foundry-resource>.services.ai.azure.com/"``).
            Can also be set via environment variable
            ``AZURE_CONTENTUNDERSTANDING_ENDPOINT``.
        credential: An ``AzureKeyCredential`` for API key auth or an
            ``AsyncTokenCredential`` (e.g., ``DefaultAzureCredential``) for
            Microsoft Entra ID auth.
        analyzer_id: A prebuilt or custom CU analyzer ID. When ``None``
            (default), a prebuilt analyzer is chosen automatically based on
            the file's media type: ``prebuilt-documentSearch`` for documents
            and images, ``prebuilt-audioSearch`` for audio, and
            ``prebuilt-videoSearch`` for video.
            Analyzer reference: https://learn.microsoft.com/azure/ai-services/content-understanding/concepts/analyzer-reference
            Prebuilt analyzers: https://learn.microsoft.com/azure/ai-services/content-understanding/concepts/prebuilt-analyzers
        max_wait: Max seconds to wait for analysis before deferring to background.
            ``None`` waits until complete.
        output_sections: Which CU output sections to pass to LLM.
            Defaults to ``[AnalysisSection.MARKDOWN, AnalysisSection.FIELDS]``.
        file_search: Optional configuration for uploading CU-extracted markdown to
            a vector store for token-efficient RAG retrieval. When provided, full
            content injection is replaced by ``file_search`` tool registration.
            The ``FileSearchConfig`` abstraction is backend-agnostic — use
            ``FileSearchConfig.from_openai()`` or ``FileSearchConfig.from_foundry()``
            for supported providers, or supply a custom ``FileSearchBackend``
            implementation for other vector store services.
        source_id: Unique identifier for this provider instance, used for message
            attribution and tool registration. Defaults to ``"azure_ai_contentunderstanding"``.
        env_file_path: Path to a ``.env`` file for loading settings.
        env_file_encoding: Encoding of the ``.env`` file.

    Per-file ``additional_properties`` on ``Content`` objects:
        The provider reads the following keys from
        ``Content.additional_properties`` (passed via ``Content.from_data()``
        or ``Content.from_uri()``):

        ``filename`` (str):
            The document key used for tracking, status, and LLM references.
            Without a filename, a UUID-based key is generated.
            Must be unique within a session — uploading a file with a
            duplicate filename will be rejected and the file will not be
            analyzed.

        ``analyzer_id`` (str):
            Per-file analyzer override. Takes priority over the provider-level
            ``analyzer_id``. Useful for mixing analyzers in the same turn
            (e.g., ``prebuilt-invoice`` for invoices alongside
            ``prebuilt-documentSearch`` for general documents).

        Example::

            Content.from_data(
                pdf_bytes, "application/pdf",
                additional_properties={
                    "filename": "invoice.pdf",
                    "analyzer_id": "prebuilt-invoice",
                },
            )
    """

    DEFAULT_SOURCE_ID: ClassVar[str] = "azure_ai_contentunderstanding"
    DEFAULT_MAX_WAIT_SECONDS: ClassVar[float] = 5.0

    def __init__(
        self,
        endpoint: str | None = None,
        credential: AzureCredentialTypes | None = None,
        *,
        analyzer_id: str | None = None,
        max_wait: float | None = DEFAULT_MAX_WAIT_SECONDS,
        output_sections: list[AnalysisSection] | None = None,
        file_search: FileSearchConfig | None = None,
        source_id: str = DEFAULT_SOURCE_ID,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
    ) -> None:
        super().__init__(source_id)

        # Load settings — explicit args take priority over env vars.
        # Env vars use the prefix AZURE_CONTENTUNDERSTANDING_ (e.g.,
        # AZURE_CONTENTUNDERSTANDING_ENDPOINT).
        settings = load_settings(
            ContentUnderstandingSettings,
            env_prefix="AZURE_CONTENTUNDERSTANDING_",
            required_fields=["endpoint"],
            endpoint=endpoint,
            env_file_path=env_file_path,
            env_file_encoding=env_file_encoding,
        )

        resolved_endpoint: str = settings["endpoint"]  # type: ignore[assignment]  # validated by load_settings

        if credential is None:
            raise ValueError(
                "Azure credential is required. Provide a 'credential' parameter "
                "(e.g., AzureKeyCredential or AzureCliCredential)."
            )

        self._endpoint = resolved_endpoint
        self._credential = credential
        self.analyzer_id = analyzer_id
        self.max_wait = max_wait
        self.output_sections = output_sections or [AnalysisSection.MARKDOWN, AnalysisSection.FIELDS]
        self.file_search = file_search
        self._client = ContentUnderstandingClient(
            self._endpoint, self._credential, user_agent=AGENT_FRAMEWORK_USER_AGENT
        )
        # Background CU analysis tasks keyed by doc_key, resolved on next before_run()
        self._pending_tasks: dict[str, asyncio.Task[AnalysisResult]] = {}
        # Documents completed in background that still need vector store upload
        self._pending_uploads: list[tuple[str, DocumentEntry]] = []
        # Uploaded file IDs for file_search mode, tracked for cleanup on close().
        # Works with any FileSearchBackend (OpenAI, Foundry, or custom).
        self._uploaded_file_ids: list[str] = []

    async def __aenter__(self) -> Self:
        """Async context manager entry."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        """Async context manager exit — cleanup clients."""
        await self.close()

    async def close(self) -> None:
        """Close the underlying CU client and cancel pending tasks."""
        for task in self._pending_tasks.values():
            if not task.done():
                task.cancel()
        self._pending_tasks.clear()
        # Clean up uploaded files; the vector store itself is caller-managed.
        if self.file_search and self._uploaded_file_ids:
            await self._cleanup_uploaded_files()
        await self._client.close()

    async def before_run(
        self,
        *,
        agent: SupportsAgentRun,
        session: AgentSession,
        context: SessionContext,
        state: dict[str, Any],
    ) -> None:
        """Analyze file attachments and inject results into the LLM context.

        This method is called automatically by the framework before each LLM invocation.
        """
        documents: dict[str, DocumentEntry] = state.setdefault("documents", {})

        # 1. Resolve pending background tasks
        self._resolve_pending_tasks(documents, context)

        # 1b. Upload any documents that completed in the background (file_search mode)
        if self._pending_uploads:
            for upload_key, upload_entry in self._pending_uploads:
                await self._upload_to_vector_store(upload_key, upload_entry)
            self._pending_uploads.clear()

        # 2. Detect CU-supported file attachments, strip them from input, and return for analysis
        new_files = self._detect_and_strip_files(context)

        # 3. Analyze new files using CU (track elapsed time for combined timeout)
        file_start_times: dict[str, float] = {}
        for doc_key, content_item, binary_data in new_files:
            # Reject duplicate filenames — re-analyzing would orphan vector store entries
            if doc_key in documents:
                logger.warning("Duplicate document key '%s' — skipping (already exists in session).", doc_key)
                context.extend_instructions(
                    self.source_id,
                    f"IMPORTANT: The user tried to upload '{doc_key}', but a file with that name "
                    "was already uploaded earlier in this session. The new upload was REJECTED — "
                    "it was NOT analyzed. Tell the user explicitly that a file with the same name "
                    "already exists and they need to rename the file before uploading again.",
                )
                continue
            file_start_times[doc_key] = time.monotonic()
            doc_entry = await self._analyze_file(doc_key, content_item, binary_data, context)
            if doc_entry:
                documents[doc_key] = doc_entry

        # 4. Inject content for ready documents and register tools
        if documents:
            self._register_tools(documents, context)

        # 5. On upload turns, inject content for all ready docs from this turn
        for doc_key, _, _ in new_files:
            entry = documents.get(doc_key)
            if entry and entry["status"] == DocumentStatus.READY and entry["result"]:
                # Upload to vector store if file_search is configured
                if self.file_search:
                    # Combined timeout: subtract CU analysis time from max_wait
                    remaining: float | None = None
                    if self.max_wait is not None:
                        elapsed = time.monotonic() - file_start_times.get(doc_key, time.monotonic())
                        remaining = max(0.0, self.max_wait - elapsed)
                    uploaded = await self._upload_to_vector_store(doc_key, entry, timeout=remaining)
                    if uploaded:
                        context.extend_instructions(
                            self.source_id,
                            f"The user just uploaded '{entry['filename']}'. It has been analyzed "
                            "using Azure Content Understanding and indexed in a vector store. "
                            f"When using file_search, include '{entry['filename']}' in your query "
                            "to retrieve content from this specific document.",
                        )
                    elif entry.get("error"):
                        # Upload failed (not timeout — actual error)
                        context.extend_instructions(
                            self.source_id,
                            f"Document '{entry['filename']}' was analyzed but failed to upload "
                            "to the vector store. The document content is not available for search.",
                        )
                    else:
                        # Upload deferred to background (timeout)
                        context.extend_instructions(
                            self.source_id,
                            f"Document '{entry['filename']}' has been analyzed and is being indexed. "
                            "Ask about it again in a moment.",
                        )
                else:
                    # Without file_search, inject full content into context
                    context.extend_messages(
                        self,
                        [
                            Message(role="user", text=self._format_result(entry["filename"], entry["result"])),
                        ],
                    )
                    context.extend_instructions(
                        self.source_id,
                        f"The user just uploaded '{entry['filename']}'. It has been analyzed "
                        "using Azure Content Understanding. "
                        "The document content (markdown) and extracted fields (JSON) are provided above. "
                        "If the user's question is ambiguous, prioritize this most recently uploaded document. "
                        "Use specific field values and cite page numbers when answering.",
                    )

        # 6. Register file_search tool (for LLM clients that support it)
        if self.file_search:
            context.extend_tools(
                self.source_id,
                [self.file_search.file_search_tool],
            )
            context.extend_instructions(
                self.source_id,
                "Tool usage guidelines:\n"
                "- Use file_search ONLY when answering questions about document content.\n"
                "- Use list_documents() for status queries (e.g. 'list docs', 'what's uploaded?').\n"
                "- Do NOT call file_search for status queries — it wastes tokens.",
            )

    # ------------------------------------------------------------------
    # File Detection
    # ------------------------------------------------------------------

    def _detect_and_strip_files(
        self,
        context: SessionContext,
    ) -> list[tuple[str, Content, bytes | None]]:
        """Scan input messages for supported file content and prepare for CU analysis.

        Scans for type ``data`` or ``uri`` content supported by Azure Content
        Understanding, strips them from messages to prevent raw binary being sent
        to the LLM, and returns metadata for CU analysis.

        Detected files are tracked via ``doc_key`` (derived from filename, URL,
        or UUID) and their analysis status is managed in session state.

        When the upstream MIME type is unreliable (``application/octet-stream``
        or missing), binary content sniffing via ``filetype`` is used to
        determine the real media type, with ``mimetypes.guess_type`` as a
        filename-based fallback.

        Returns:
            List of (doc_key, content_item, binary_data) tuples for files to analyze.
        """
        results: list[tuple[str, Content, bytes | None]] = []
        strip_ids: set[int] = set()

        for msg in context.input_messages:
            for c in msg.contents:
                if c.type not in ("data", "uri"):
                    continue

                media_type = c.media_type
                # Fast path: already a known supported type
                if media_type and media_type in SUPPORTED_MEDIA_TYPES:
                    binary_data = self._extract_binary(c)
                    results.append((self._derive_doc_key(c), c, binary_data))
                    strip_ids.add(id(c))
                    continue

                # Slow path: unreliable MIME — sniff binary content
                if (not media_type) or (media_type == "application/octet-stream"):
                    binary_data = self._extract_binary(c)
                    resolved = self._sniff_media_type(binary_data, c)
                    if resolved and (resolved in SUPPORTED_MEDIA_TYPES):
                        c.media_type = resolved
                        results.append((self._derive_doc_key(c), c, binary_data))
                        strip_ids.add(id(c))

            # Strip detected files from input so raw binary isn't sent to LLM
            msg.contents = [c for c in msg.contents if id(c) not in strip_ids]

        return results

    @staticmethod
    def _sniff_media_type(binary_data: bytes | None, content: Content) -> str | None:
        """Sniff the actual MIME type from binary data, with filename fallback.

        Uses ``filetype`` (magic-bytes) first, then ``mimetypes.guess_type``
        on the filename. Normalizes filetype's variant MIME values (e.g.
        ``audio/x-wav`` → ``audio/wav``) via ``_MIME_ALIASES``.
        """
        # 1. Binary sniffing via filetype (needs only first 261 bytes)
        if binary_data:
            kind = filetype.guess(binary_data[:262])  # type: ignore[reportUnknownMemberType]
            if kind:
                mime: str = kind.mime  # type: ignore[reportUnknownMemberType]
                return _MIME_ALIASES.get(mime, mime)

        # 2. Filename extension fallback — try additional_properties first,
        # then extract basename from external URL path
        filename: str | None = None
        if content.additional_properties:
            filename = content.additional_properties.get("filename")
        if not filename and content.uri and not content.uri.startswith("data:"):
            # Extract basename from URL path (e.g. "https://example.com/report.pdf?v=1" → "report.pdf")
            filename = content.uri.split("?")[0].split("#")[0].rsplit("/", 1)[-1]
        if filename:
            guessed, _ = mimetypes.guess_type(filename)  # uses file extension to guess MIME type
            if guessed:
                return _MIME_ALIASES.get(guessed, guessed)

        return None

    @staticmethod
    def _is_supported_content(content: Content) -> bool:
        """Check if a content item is a supported file type for CU analysis."""
        if content.type not in ("data", "uri"):
            return False
        media_type = content.media_type
        if not media_type:
            return False
        return media_type in SUPPORTED_MEDIA_TYPES

    @staticmethod
    def _derive_doc_key(content: Content) -> str:
        """Derive a unique document key from content metadata.

        The key is used to track documents in session state. Duplicate keys
        within a session are rejected (not re-analyzed) to prevent orphaned
        vector store entries.

        Priority: filename > URL basename > content hash.
        """
        # 1. Filename from additional_properties
        if content.additional_properties:
            filename = content.additional_properties.get("filename")
            if filename and isinstance(filename, str):
                return str(filename)

        # 2. URL path basename for external URIs (e.g. "https://example.com/report.pdf" → "report.pdf")
        if content.type == "uri" and content.uri and not content.uri.startswith("data:"):
            path = content.uri.split("?")[0].split("#")[0]  # strip query params and fragments
            # rstrip("/") handles trailing slashes (e.g. ".../files/" → ".../files")
            # rsplit("/", 1)[-1] splits from the right once to get the last path segment
            basename = path.rstrip("/").rsplit("/", 1)[-1]
            if basename:
                return basename

        # 3. Fallback: generate a unique ID for anonymous uploads (no filename, no URL)
        return f"doc_{uuid.uuid4().hex[:8]}"

    @staticmethod
    def _extract_binary(content: Content) -> bytes | None:
        """Extract binary data from a data URI content item.

        Only handles ``data:`` URIs (base64-encoded). Returns ``None`` for
        external URLs — those are passed directly to CU via ``begin_analyze``.
        """
        if content.uri and content.uri.startswith("data:"):
            try:
                _, data_part = content.uri.split(",", 1)
                return base64.b64decode(data_part)
            except Exception:
                logger.warning("Failed to decode base64 data URI")
                return None
        return None

    # ------------------------------------------------------------------
    # Analyzer Resolution
    # ------------------------------------------------------------------

    def _resolve_analyzer_id(self, media_type: str) -> str:
        """Return the analyzer ID to use for the given media type.

        When ``self.analyzer_id`` is set, it is always returned (explicit
        override).  Otherwise the media type prefix is matched against the
        known mapping, falling back to ``prebuilt-documentSearch``.
        """
        if self.analyzer_id is not None:
            return self.analyzer_id
        for prefix, analyzer in _MEDIA_TYPE_ANALYZER_MAP.items():
            if media_type.startswith(prefix):
                return analyzer
        return _DEFAULT_ANALYZER

    # ------------------------------------------------------------------
    # Analysis
    # ------------------------------------------------------------------

    async def _analyze_file(
        self,
        doc_key: str,
        content: Content,
        binary_data: bytes | None,
        context: SessionContext,
    ) -> DocumentEntry | None:
        """Analyze a single file via CU with timeout handling.

        The analyzer is resolved in priority order:
        1. Per-file override via ``content.additional_properties["analyzer_id"]``
        2. Provider-level default via ``self.analyzer_id``
        3. Auto-detect by media type (document/audio/video)

        Returns:
            A ``DocumentEntry`` (ready, analyzing, or failed), or ``None`` if
            file data could not be extracted.
        """
        media_type = content.media_type or "application/octet-stream"
        filename = doc_key

        # Per-file analyzer override from additional_properties
        per_file_analyzer = (
            content.additional_properties.get("analyzer_id")
            if content.additional_properties
            else None
        )
        resolved_analyzer = per_file_analyzer or self._resolve_analyzer_id(media_type)
        t0 = time.monotonic()

        try:
            # Start CU analysis
            if content.type == "uri" and content.uri and not content.uri.startswith("data:"):
                poller = await self._client.begin_analyze(
                    resolved_analyzer,
                    body={"inputs": [{"url": content.uri}]},
                )
            elif binary_data:
                poller = await self._client.begin_analyze_binary(
                    resolved_analyzer,
                    binary_input=binary_data,
                    content_type=media_type,
                )
            else:
                context.extend_instructions(
                    self.source_id,
                    f"Could not extract file data from '{filename}'.",
                )
                return None

            # Wait with timeout; defer to background polling on timeout.
            try:
                result = await asyncio.wait_for(poller.result(), timeout=self.max_wait)
            except asyncio.TimeoutError:
                task = asyncio.create_task(self._background_poll(poller))
                self._pending_tasks[doc_key] = task
                context.extend_instructions(
                    self.source_id,
                    f"Document '{filename}' is being analyzed. Ask about it again in a moment.",
                )
                return DocumentEntry(
                    status=DocumentStatus.ANALYZING,
                    filename=filename,
                    media_type=media_type,
                    analyzer_id=resolved_analyzer,
                    analyzed_at=None,
                    analysis_duration_s=None,
                    upload_duration_s=None,
                    result=None,
                    error=None,
                )

            # Analysis completed within timeout
            analysis_duration = round(time.monotonic() - t0, 2)
            extracted = self._extract_sections(result)
            logger.info("Analyzed '%s' with analyzer '%s' in %.1fs.", filename, resolved_analyzer, analysis_duration)
            return DocumentEntry(
                status=DocumentStatus.READY,
                filename=filename,
                media_type=media_type,
                analyzer_id=resolved_analyzer,
                analyzed_at=datetime.now(tz=timezone.utc).isoformat(),
                analysis_duration_s=analysis_duration,
                upload_duration_s=None,
                result=extracted,
                error=None,
            )

        except asyncio.TimeoutError:
            raise
        except Exception as e:
            logger.warning("CU analysis error for '%s': %s", filename, e)
            context.extend_instructions(
                self.source_id,
                f"Could not analyze '{filename}': {e}",
            )
            return DocumentEntry(
                status=DocumentStatus.FAILED,
                filename=filename,
                media_type=media_type,
                analyzer_id=resolved_analyzer,
                analyzed_at=datetime.now(tz=timezone.utc).isoformat(),
                analysis_duration_s=round(time.monotonic() - t0, 2),
                upload_duration_s=None,
                result=None,
                error=str(e),
            )

    async def _background_poll(self, poller: Any) -> AnalysisResult:
        """Poll a CU operation in the background until completion."""
        return await poller.result()  # type: ignore[no-any-return]

    # ------------------------------------------------------------------
    # Pending Task Resolution
    # ------------------------------------------------------------------

    def _resolve_pending_tasks(
        self,
        documents: dict[str, DocumentEntry],
        context: SessionContext,
    ) -> None:
        """Check for completed background CU analysis tasks and update document state.

        When a file's CU analysis exceeds ``max_wait``, it is deferred to a background
        ``asyncio.Task``. This method checks all pending tasks on the next ``before_run()``
        call: completed tasks have their results extracted and status set to ``READY``;
        failed tasks are marked ``FAILED`` with an error message.

        In file_search mode, completed documents are queued in ``_pending_uploads``
        for vector store upload (handled in step 1b of ``before_run``).
        """
        completed_keys: list[str] = []

        for doc_key, task in self._pending_tasks.items():
            if not task.done():
                continue

            completed_keys.append(doc_key)
            entry = documents.get(doc_key)
            if not entry:
                continue

            try:
                result = task.result()
                extracted = self._extract_sections(result)
                entry["status"] = DocumentStatus.READY
                entry["analyzed_at"] = datetime.now(tz=timezone.utc).isoformat()
                entry["result"] = extracted
                entry["error"] = None
                # analysis_duration_s stays None for background tasks (indeterminate)
                logger.info("Background analysis of '%s' completed.", entry["filename"])

                # Inject newly ready content
                if self.file_search:
                    # Upload to vector store — do NOT inject markdown into messages
                    # (this is a sync context; schedule the upload as a task)
                    self._pending_uploads.append((doc_key, entry))
                else:
                    context.extend_messages(
                        self,
                        [
                            Message(role="user", text=self._format_result(entry["filename"], extracted)),
                        ],
                    )
                context.extend_instructions(
                    self.source_id,
                    f"Document '{entry['filename']}' analysis is now complete."
                    + (
                        " Use file_search to retrieve relevant sections."
                        if self.file_search
                        else " The content is provided above."
                    ),
                )

            except Exception as e:
                logger.warning("Background analysis of '%s' failed: %s", entry.get("filename", doc_key), e)
                entry["status"] = DocumentStatus.FAILED
                entry["analyzed_at"] = datetime.now(tz=timezone.utc).isoformat()
                entry["error"] = str(e)
                context.extend_instructions(
                    self.source_id,
                    f"Document '{entry['filename']}' analysis failed: {e}",
                )

        for key in completed_keys:
            del self._pending_tasks[key]

    # ------------------------------------------------------------------
    # Output Extraction & Formatting
    # ------------------------------------------------------------------

    def _extract_sections(self, result: AnalysisResult) -> dict[str, object]:
        """Extract configured sections from a CU analysis result.

        For single-segment results (documents, images, short audio), returns a flat
        dict with ``markdown`` and ``fields`` at the top level.

        For multi-segment results (e.g. video split into scenes), fields are kept
        with their respective segments in a ``segments`` list so the LLM can see
        which fields belong to which part of the content:
        - ``segments``: list of per-segment dicts with ``markdown``, ``fields``,
          ``start_time_s``, and ``end_time_s``
        - ``markdown``: still concatenated at top level for file_search uploads
        - ``duration_seconds``: computed from the global time span
        - ``kind`` / ``resolution``: taken from the first segment
        """
        extracted: dict[str, object] = {}
        contents = result.contents
        if not contents:
            return extracted

        # --- Media metadata (from first segment) ---
        first = contents[0]
        kind = getattr(first, "kind", None)
        if kind:
            extracted["kind"] = kind
        width = getattr(first, "width", None)
        height = getattr(first, "height", None)
        if width and height:
            extracted["resolution"] = f"{width}x{height}"

        # Compute total duration from the global time span of all segments.
        global_start: int | None = None
        global_end: int | None = None
        for content in contents:
            s = getattr(content, "start_time_ms", None) or getattr(content, "startTimeMs", None)
            e = getattr(content, "end_time_ms", None) or getattr(content, "endTimeMs", None)
            if s is not None:
                global_start = s if global_start is None else min(global_start, s)
            if e is not None:
                global_end = e if global_end is None else max(global_end, e)
        if global_start is not None and global_end is not None:
            extracted["duration_seconds"] = round((global_end - global_start) / 1000, 1)

        is_multi_segment = len(contents) > 1

        # --- Single-segment: flat output (documents, images, short audio) ---
        if not is_multi_segment:
            if AnalysisSection.MARKDOWN in self.output_sections and contents[0].markdown:
                extracted["markdown"] = contents[0].markdown
            if AnalysisSection.FIELDS in self.output_sections and contents[0].fields:
                fields: dict[str, object] = {}
                for name, field in contents[0].fields.items():
                    value = self._extract_field_value(field)
                    confidence = getattr(field, "confidence", None)
                    field_type = getattr(field, "type", None)
                    fields[name] = {"type": field_type, "value": value, "confidence": confidence}
                if fields:
                    extracted["fields"] = fields
            return extracted

        # --- Multi-segment: per-segment output (video scenes, long audio) ---
        # Each segment keeps its own markdown + fields together so the LLM can
        # see which fields (e.g. Summary) belong to which part of the content.
        segments_out: list[dict[str, object]] = []
        md_parts: list[str] = []  # also collect for top-level concatenated markdown

        for content in contents:
            seg: dict[str, object] = {}

            # Time range for this segment
            s = getattr(content, "start_time_ms", None) or getattr(content, "startTimeMs", None)
            e = getattr(content, "end_time_ms", None) or getattr(content, "endTimeMs", None)
            if s is not None:
                seg["start_time_s"] = round(s / 1000, 1)
            if e is not None:
                seg["end_time_s"] = round(e / 1000, 1)

            # Per-segment markdown
            if AnalysisSection.MARKDOWN in self.output_sections and content.markdown:
                seg["markdown"] = content.markdown
                md_parts.append(content.markdown)

            # Per-segment fields
            if AnalysisSection.FIELDS in self.output_sections and content.fields:
                seg_fields: dict[str, object] = {}
                for name, field in content.fields.items():
                    value = self._extract_field_value(field)
                    confidence = getattr(field, "confidence", None)
                    field_type = getattr(field, "type", None)
                    seg_fields[name] = {"type": field_type, "value": value, "confidence": confidence}
                if seg_fields:
                    seg["fields"] = seg_fields

            segments_out.append(seg)

        extracted["segments"] = segments_out

        # Top-level concatenated markdown (used by file_search for vector store upload)
        if md_parts:
            extracted["markdown"] = "\n\n---\n\n".join(md_parts)

        return extracted

    @staticmethod
    def _extract_field_value(field: Any) -> object:
        """Extract the value from a CU field, trying multiple attribute names."""
        for attr in ("value_string", "value_number", "value_date", "value"):
            value = getattr(field, attr, None)
            if value is not None:
                return value
        return None

    @staticmethod
    def _format_result(filename: str, result: dict[str, object]) -> str:
        """Format extracted CU result for LLM consumption.

        For multi-segment results (video/audio with ``segments``), each segment's
        markdown and fields are grouped together so the LLM can see which fields
        belong to which part of the content.
        """
        kind = result.get("kind")
        is_video = kind == "audioVisual"
        is_audio = kind == "audio"

        # Header — media-aware label
        if is_video:
            label = "Video analysis"
        elif is_audio:
            label = "Audio analysis"
        else:
            label = "Document analysis"
        parts: list[str] = [f'{label} of "{filename}":']

        # Media metadata line (duration, resolution)
        meta_items: list[str] = []
        duration = result.get("duration_seconds")
        if duration is not None:
            mins, secs = divmod(int(duration), 60)  # type: ignore[call-overload]
            meta_items.append(f"Duration: {mins}:{secs:02d}")
        resolution = result.get("resolution")
        if resolution:
            meta_items.append(f"Resolution: {resolution}")
        if meta_items:
            parts.append(" | ".join(meta_items))

        # --- Multi-segment: format each segment with its own content + fields ---
        raw_segments = result.get("segments")
        segments: list[dict[str, object]] = (
            cast(list[dict[str, object]], raw_segments) if isinstance(raw_segments, list) else []
        )
        if segments:
            for i, seg in enumerate(segments):
                # Segment header with time range
                start = seg.get("start_time_s")
                end = seg.get("end_time_s")
                if start is not None and end is not None:
                    s_min, s_sec = divmod(int(start), 60)  # type: ignore[call-overload]
                    e_min, e_sec = divmod(int(end), 60)  # type: ignore[call-overload]
                    parts.append(f"\n### Segment {i + 1} ({s_min}:{s_sec:02d} - {e_min}:{e_sec:02d})")
                else:
                    parts.append(f"\n### Segment {i + 1}")

                # Segment markdown
                seg_md = seg.get("markdown")
                if seg_md:
                    parts.append(f"\n```markdown\n{seg_md}\n```")

                # Segment fields
                seg_fields = seg.get("fields")
                if isinstance(seg_fields, dict) and seg_fields:
                    fields_json = json.dumps(seg_fields, indent=2, default=str)
                    parts.append(f"\n**Fields:**\n```json\n{fields_json}\n```")

            return "\n".join(parts)

        # --- Single-segment: flat format ---
        fields_raw = result.get("fields")
        fields: dict[str, object] = cast(dict[str, object], fields_raw) if isinstance(fields_raw, dict) else {}

        # For audio: promote Summary field as prose before markdown
        if is_audio and fields:
            summary_field = fields.get("Summary")
            if isinstance(summary_field, dict):
                sf = cast(dict[str, object], summary_field)
                if sf.get("value"):
                    parts.append(f"\n## Summary\n\n{sf['value']}")

        # Markdown content
        markdown = result.get("markdown")
        if markdown:
            parts.append(f"\n## Content\n\n```markdown\n{markdown}\n```")

        # Fields section
        if fields:
            remaining = dict(fields)
            if is_audio:
                remaining = {k: v for k, v in remaining.items() if k != "Summary"}
            if remaining:
                fields_json = json.dumps(remaining, indent=2, default=str)
                parts.append(f"\n## Extracted Fields\n\n```json\n{fields_json}\n```")

        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Tool Registration
    # ------------------------------------------------------------------

    def _register_tools(
        self,
        documents: dict[str, DocumentEntry],
        context: SessionContext,
    ) -> None:
        """Register document tools on the context.

        Only ``list_documents`` is registered — the full document content is
        already injected into conversation history on the upload turn, so a
        separate retrieval tool is not needed.
        """
        context.extend_tools(
            self.source_id,
            [self._make_list_documents_tool(documents)],
        )

    @staticmethod
    def _make_list_documents_tool(documents: dict[str, DocumentEntry]) -> FunctionTool:
        """Create a tool that lists all tracked documents with their status."""
        docs_ref = documents

        def list_documents() -> str:
            """List all documents that have been uploaded and their analysis status."""
            entries: list[dict[str, object]] = []
            for name, entry in docs_ref.items():
                entries.append({
                    "name": name,
                    "status": entry["status"],
                    "media_type": entry["media_type"],
                    "analyzed_at": entry["analyzed_at"],
                    "analysis_duration_s": entry["analysis_duration_s"],
                    "upload_duration_s": entry["upload_duration_s"],
                })
            return json.dumps(entries, indent=2, default=str)

        return FunctionTool(
            name="list_documents",
            description=(
                "List all documents that have been uploaded in this session "
                "with their analysis status (analyzing, uploading, ready, or failed)."
            ),
            func=list_documents,
        )

    # ------------------------------------------------------------------
    # file_search Vector Store Integration
    # ------------------------------------------------------------------

    async def _upload_to_vector_store(
        self, doc_key: str, entry: DocumentEntry, *, timeout: float | None = None
    ) -> bool:
        """Upload CU-extracted markdown to the caller's vector store.

        Delegates to the configured ``FileSearchBackend`` (OpenAI, Foundry,
        or a custom implementation). The upload includes file upload **and**
        vector store indexing (embedding + ingestion) — ``create_and_poll``
        waits for the index to be fully ready before returning.

        Args:
            doc_key: Document identifier.
            entry: The document entry with extracted results.
            timeout: Max seconds to wait for upload + indexing. ``None`` waits
                indefinitely. On timeout the upload is deferred to the
                ``_pending_uploads`` queue for the next ``before_run()`` call.

        Returns:
            True if the upload succeeded, False otherwise.
        """
        if not self.file_search:
            return False

        result = entry.get("result")
        if not result:
            return False

        # Upload the full formatted content (markdown + fields + segments),
        # not just raw markdown — consistent with what non-file_search mode injects.
        formatted = self._format_result(entry["filename"], result)
        if not formatted:
            return False

        entry["status"] = DocumentStatus.UPLOADING
        t0 = time.monotonic()

        try:
            upload_coro = self.file_search.backend.upload_file(
                self.file_search.vector_store_id, f"{doc_key}.md", formatted.encode("utf-8")
            )
            file_id = await asyncio.wait_for(upload_coro, timeout=timeout)
            upload_duration = round(time.monotonic() - t0, 2)
            self._uploaded_file_ids.append(file_id)
            entry["status"] = DocumentStatus.READY
            entry["upload_duration_s"] = upload_duration
            logger.info("Uploaded '%s' to vector store in %.1fs (%s bytes).", doc_key, upload_duration, len(formatted))
            return True

        except asyncio.TimeoutError:
            logger.info("Vector store upload for '%s' timed out; deferring to background.", doc_key)
            entry["status"] = DocumentStatus.UPLOADING
            self._pending_uploads.append((doc_key, entry))
            return False

        except Exception as e:
            logger.warning("Failed to upload '%s' to vector store: %s", doc_key, e)
            entry["status"] = DocumentStatus.FAILED
            entry["upload_duration_s"] = round(time.monotonic() - t0, 2)
            entry["error"] = f"Vector store upload failed: {e}"
            return False

    async def _cleanup_uploaded_files(self) -> None:
        """Delete files uploaded by this provider via the configured backend.

        The vector store itself is caller-managed and is not deleted here.
        """
        if not self.file_search:
            return

        backend = self.file_search.backend

        try:
            for file_id in self._uploaded_file_ids:
                await backend.delete_file(file_id)
            self._uploaded_file_ids.clear()

        except Exception as e:
            logger.warning("Failed to clean up uploaded files: %s", e)
