# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import mimetypes
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, ClassVar, cast

import filetype
from agent_framework import BaseContextProvider, Content, FunctionTool, Message, SessionContext
from agent_framework._sessions import AgentSession
from azure.ai.contentunderstanding.aio import ContentUnderstandingClient
from azure.ai.contentunderstanding.models import AnalysisResult
from azure.core.credentials import AzureKeyCredential
from azure.core.credentials_async import AsyncTokenCredential

if TYPE_CHECKING:
    from agent_framework._agents import SupportsAgentRun

from ._models import AnalysisSection, DocumentEntry, FileSearchConfig

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


class ContentUnderstandingContextProvider(BaseContextProvider):
    """Context provider that analyzes file attachments using Azure Content Understanding.

    Automatically detects supported file attachments in the agent's input,
    analyzes them via CU, and injects the structured results (markdown, fields)
    into the LLM context. Supports multiple documents per session with background
    processing for long-running analyses.

    Args:
        endpoint: Azure AI Foundry endpoint URL
            (e.g., ``"https://<your-foundry-resource>.services.ai.azure.com/"``).
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
            an OpenAI vector store for token-efficient RAG retrieval. When provided,
            full content injection is replaced by ``file_search`` tool registration.
        source_id: Unique identifier for message attribution.
    """

    DEFAULT_SOURCE_ID: ClassVar[str] = "content_understanding"
    DEFAULT_MAX_WAIT_SECONDS: ClassVar[float] = 5.0

    def __init__(
        self,
        endpoint: str,
        credential: AzureCredentialTypes,
        *,
        analyzer_id: str | None = None,
        max_wait: float | None = DEFAULT_MAX_WAIT_SECONDS,
        output_sections: list[AnalysisSection] | None = None,
        file_search: FileSearchConfig | None = None,
        source_id: str = DEFAULT_SOURCE_ID,
    ) -> None:
        super().__init__(source_id)
        self._endpoint = endpoint
        self._credential = credential
        self.analyzer_id = analyzer_id
        self.max_wait = max_wait
        self.output_sections = output_sections or [AnalysisSection.MARKDOWN, AnalysisSection.FIELDS]
        self.file_search = file_search
        self._client = ContentUnderstandingClient(self._endpoint, self._credential)
        # Background CU analysis tasks keyed by doc_key, resolved on next before_run()
        self._pending_tasks: dict[str, asyncio.Task[AnalysisResult]] = {}
        # Documents completed in background that still need vector store upload
        self._pending_uploads: list[tuple[str, DocumentEntry]] = []
        # OpenAI vector store ID for file_search mode (user-provided or auto-created)
        self._vector_store_id: str | None = None
        # Whether the provider created the vector store (True) or the user provided it (False).
        # Only auto-created stores are deleted on close().
        self._owns_vector_store: bool = False
        # Uploaded OpenAI file IDs, tracked for cleanup
        self._uploaded_file_ids: list[str] = []

    async def __aenter__(self) -> ContentUnderstandingContextProvider:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()

    async def close(self) -> None:
        """Close the underlying CU client and cancel pending tasks."""
        for task in self._pending_tasks.values():
            if not task.done():
                task.cancel()
        self._pending_tasks.clear()
        # Clean up vector store resources
        if self.file_search and (self._vector_store_id or self._uploaded_file_ids):
            await self._cleanup_vector_store()
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

        # 2. Detect and strip supported file attachments from input
        new_files = self._detect_and_strip_files(context)

        # 3. Analyze new files
        for doc_key, content_item, binary_data in new_files:
            await self._analyze_file(doc_key, content_item, binary_data, documents, context)

        # 4. Inject content for ready documents and register tools
        if documents:
            self._register_tools(documents, context)

        # 5. On upload turns, inject content for all ready docs from this turn
        for doc_key, _, _ in new_files:
            entry = documents.get(doc_key)
            if entry and entry["status"] == "ready" and entry["result"]:
                # Upload to vector store if file_search is configured
                if self.file_search:
                    await self._upload_to_vector_store(doc_key, entry)
                else:
                    # Without file_search, inject full content into context
                    context.extend_messages(
                        self,
                        [
                            Message(role="user", text=self._format_result(entry["filename"], entry["result"])),
                        ],
                    )
                if self.file_search:
                    context.extend_instructions(
                        self.source_id,
                        "A document has been analyzed using Azure Content Understanding "
                        "and indexed in a vector store. Use file_search to retrieve relevant sections.",
                    )
                else:
                    context.extend_instructions(
                        self.source_id,
                        "A document has been analyzed using Azure Content Understanding. "
                        "The document content (markdown) and extracted fields (JSON) are provided above. "
                        "Use specific field values and cite page numbers when answering.",
                    )

        # 6. Register file_search tool if vector store exists
        if self.file_search and self._vector_store_id:
            context.extend_tools(
                self.source_id,
                [self.file_search.backend.make_tool([self._vector_store_id])],
            )

    # ------------------------------------------------------------------
    # File Detection
    # ------------------------------------------------------------------

    def _detect_and_strip_files(
        self,
        context: SessionContext,
    ) -> list[tuple[str, Content, bytes | None]]:
        """Detect supported files in input, strip them, and return metadata.

        When the upstream MIME type is unreliable (``application/octet-stream``
        or missing), binary content sniffing via ``filetype`` is used to
        determine the real media type, with ``mimetypes.guess_type`` as a
        filename-based fallback.

        Returns:
            List of (doc_key, content_item, binary_data) tuples.
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
                if not media_type or media_type == "application/octet-stream":
                    binary_data = self._extract_binary(c)
                    resolved = self._sniff_media_type(binary_data, c)
                    if resolved and resolved in SUPPORTED_MEDIA_TYPES:
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

        # 2. Filename extension fallback
        filename: str | None = None
        if content.additional_properties:
            filename = content.additional_properties.get("filename")
        if not filename and content.uri and not content.uri.startswith("data:"):
            filename = content.uri.split("?")[0].split("#")[0].rsplit("/", 1)[-1]
        if filename:
            guessed, _ = mimetypes.guess_type(filename)
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
        """Derive a document key from content metadata.

        Priority: filename > URL basename > content hash.
        """
        # 1. Filename from additional_properties
        if content.additional_properties:
            filename = content.additional_properties.get("filename")
            if filename and isinstance(filename, str):
                return str(filename)

        # 2. URL path basename for external URIs
        if content.type == "uri" and content.uri and not content.uri.startswith("data:"):
            path = content.uri.split("?")[0].split("#")[0]
            basename = path.rstrip("/").rsplit("/", 1)[-1]
            if basename:
                return basename

        # 3. Content hash for anonymous binary uploads
        if content.uri and content.uri.startswith("data:"):
            _, data_part = content.uri.split(",", 1)
            raw = base64.b64decode(data_part)
            return f"doc_{hashlib.sha256(raw).hexdigest()[:8]}"

        return f"doc_{id(content)}"

    @staticmethod
    def _extract_binary(content: Content) -> bytes | None:
        """Extract binary data from a content item."""
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
        documents: dict[str, DocumentEntry],
        context: SessionContext,
    ) -> None:
        """Analyze a single file via CU with timeout handling."""
        media_type = content.media_type or "application/octet-stream"
        filename = doc_key
        resolved_analyzer = self._resolve_analyzer_id(media_type)

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
                return

            # Wait with timeout; defer to background polling on timeout.
            try:
                result = await asyncio.wait_for(poller.result(), timeout=self.max_wait)
            except asyncio.TimeoutError:
                task = asyncio.create_task(self._background_poll(poller))
                self._pending_tasks[doc_key] = task
                documents[doc_key] = DocumentEntry(
                    status="pending",
                    filename=filename,
                    media_type=media_type,
                    analyzer_id=resolved_analyzer,
                    analyzed_at=None,
                    result=None,
                    error=None,
                )
                context.extend_instructions(
                    self.source_id,
                    f"Document '{filename}' is being analyzed. Ask about it again in a moment.",
                )
                return

            # Store successful result
            extracted = self._extract_sections(result)
            documents[doc_key] = DocumentEntry(
                status="ready",
                filename=filename,
                media_type=media_type,
                analyzer_id=resolved_analyzer,
                analyzed_at=datetime.now(tz=timezone.utc).isoformat(),
                result=extracted,
                error=None,
            )
            logger.info("Analyzed '%s' with analyzer '%s' successfully.", filename, resolved_analyzer)

        except asyncio.TimeoutError:
            raise
        except Exception as e:
            logger.warning("CU analysis error for '%s': %s", filename, e)
            documents[doc_key] = DocumentEntry(
                status="failed",
                filename=filename,
                media_type=media_type,
                analyzer_id=resolved_analyzer,
                analyzed_at=datetime.now(tz=timezone.utc).isoformat(),
                result=None,
                error=str(e),
            )
            context.extend_instructions(
                self.source_id,
                f"Could not analyze '{filename}': {e}",
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
        """Check for completed background tasks and update document state."""
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
                entry["status"] = "ready"
                entry["analyzed_at"] = datetime.now(tz=timezone.utc).isoformat()
                entry["result"] = extracted
                entry["error"] = None
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
                entry["status"] = "failed"
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

        For multi-segment results (e.g. video split into scenes), this method
        iterates **all** ``contents`` entries and merges them:
        - ``duration_seconds``: computed from the global min(startTimeMs) to max(endTimeMs)
        - ``markdown``: concatenated across segments with separator
        - ``fields``: merged; when the same field name appears in multiple segments,
          values are collected into a per-segment list
        - ``kind`` / ``resolution``: taken from the first segment
        """
        extracted: dict[str, object] = {}
        contents = result.contents
        if not contents:
            return extracted

        # --- Media metadata (merged across all segments) ---
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

        # --- Markdown (concatenated) ---
        if AnalysisSection.MARKDOWN in self.output_sections:
            md_parts: list[str] = []
            for content in contents:
                if content.markdown:
                    md_parts.append(content.markdown)
            if md_parts:
                extracted["markdown"] = "\n\n---\n\n".join(md_parts)

        # --- Fields (merged across segments) ---
        if AnalysisSection.FIELDS in self.output_sections:
            merged_fields: dict[str, list[dict[str, object]]] = {}
            for seg_idx, content in enumerate(contents):
                if not content.fields:
                    continue
                for name, field in content.fields.items():
                    value: object = None
                    for attr in ("value_string", "value_number", "value_date", "value"):
                        value = getattr(field, attr, None)
                        if value is not None:
                            break
                    confidence = getattr(field, "confidence", None)
                    field_type = getattr(field, "type", None)
                    entry = {"type": field_type, "value": value, "confidence": confidence}
                    if len(contents) > 1:
                        entry["segment"] = seg_idx
                    merged_fields.setdefault(name, []).append(entry)

            # Flatten single-occurrence fields for backward compat
            fields: dict[str, dict[str, object] | list[dict[str, object]]] = {}
            for name, entries in merged_fields.items():
                fields[name] = entries[0] if len(entries) == 1 else entries
            if fields:
                extracted["fields"] = fields

        return extracted

    @staticmethod
    def _format_result(filename: str, result: dict[str, object]) -> str:
        """Format extracted CU result for LLM consumption."""
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

        # For audio: promote Summary field as prose before markdown
        fields_raw = result.get("fields")
        fields: dict[str, object] = (
            cast(dict[str, object], fields_raw) if isinstance(fields_raw, dict) else {}
        )
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
            # For audio, Summary was already shown as prose above
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
        """Register list_documents and get_analyzed_document tools."""
        context.extend_tools(
            self.source_id,
            [
                self._make_list_documents_tool(documents),
                self._make_get_document_tool(documents),
            ],
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
                })
            return json.dumps(entries, indent=2, default=str)

        return FunctionTool(
            name="list_documents",
            description=(
                "List all documents that have been uploaded in this session "
                "with their analysis status (pending, ready, or failed)."
            ),
            func=list_documents,
        )

    def _make_get_document_tool(self, documents: dict[str, DocumentEntry]) -> FunctionTool:
        """Create a tool that retrieves cached analysis for a specific document."""
        docs_ref = documents
        format_fn = self._format_result

        def get_analyzed_document(document_name: str, section: str = "all") -> str:
            """Retrieve the analyzed content of a previously uploaded document.

            Args:
                document_name: The name of the document to retrieve.
                section: Which section to retrieve: "markdown", "fields", or "all".
            """
            entry = docs_ref.get(document_name)
            if not entry:
                return (
                    f"No document found with name '{document_name}'. Use list_documents() to see available documents."
                )
            if entry["status"] == "pending":
                return f"Document '{document_name}' is still being analyzed. Please try again in a moment."
            if entry["status"] == "failed":
                return f"Document '{document_name}' analysis failed: {entry.get('error', 'unknown error')}"
            if not entry["result"]:
                return f"No analysis result available for '{document_name}'."

            result = entry["result"]
            if section == "markdown":
                md = result.get("markdown", "")
                return str(md) if md else f"No markdown content available for '{document_name}'."
            if section == "fields":
                fields = result.get("fields")
                if fields:
                    return json.dumps(fields, indent=2, default=str)
                return f"No extracted fields available for '{document_name}'."

            return format_fn(entry["filename"], result)

        return FunctionTool(
            name="get_analyzed_document",
            description="Retrieve the analyzed content of a previously uploaded document by name. "
            "Use 'section' parameter to get 'markdown', 'fields', or 'all' (default).",
            func=get_analyzed_document,
        )

    # ------------------------------------------------------------------
    # file_search Vector Store Integration
    # ------------------------------------------------------------------

    async def _upload_to_vector_store(self, doc_key: str, entry: DocumentEntry) -> None:
        """Upload CU-extracted markdown to a vector store for RAG retrieval."""
        if not self.file_search:
            return

        result = entry.get("result")
        if not result:
            return

        markdown = result.get("markdown")
        if not markdown or not isinstance(markdown, str):
            return

        backend = self.file_search.backend

        try:
            # Resolve vector store on first upload: use user-provided ID or auto-create.
            if not self._vector_store_id:
                if self.file_search.vector_store_id:
                    # User-provided vector store — don't delete on close
                    self._vector_store_id = self.file_search.vector_store_id
                    self._owns_vector_store = False
                    logger.info("Using user-provided vector store (%s).", self._vector_store_id)
                else:
                    # Auto-create an ephemeral vector store.
                    self._vector_store_id = await backend.create_vector_store()
                    self._owns_vector_store = True
                    logger.info("Created vector store (%s).", self._vector_store_id)

            # Upload markdown as a .md file
            file_id = await backend.upload_file(
                self._vector_store_id, f"{doc_key}.md", markdown.encode("utf-8")
            )
            self._uploaded_file_ids.append(file_id)
            logger.info("Uploaded '%s' to vector store (%s bytes).", doc_key, len(markdown))

        except Exception as e:
            logger.warning("Failed to upload '%s' to vector store: %s", doc_key, e)

    async def _cleanup_vector_store(self) -> None:
        """Clean up vector store resources.

        Only deletes the vector store itself if it was auto-created by the provider
        (``_owns_vector_store is True``). Uploaded files are always deleted regardless
        of ownership, since the provider created them.
        """
        if not self.file_search:
            return

        backend = self.file_search.backend

        try:
            # Only delete the vector store if we created it
            if self._vector_store_id and self._owns_vector_store:
                await backend.delete_vector_store(self._vector_store_id)
                logger.info("Deleted vector store %s.", self._vector_store_id)
            self._vector_store_id = None
            self._owns_vector_store = False

            for file_id in self._uploaded_file_ids:
                await backend.delete_file(file_id)
            self._uploaded_file_ids.clear()

        except Exception as e:
            logger.warning("Failed to clean up vector store resources: %s", e)
