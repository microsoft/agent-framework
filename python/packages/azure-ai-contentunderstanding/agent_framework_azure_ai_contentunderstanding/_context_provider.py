# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, ClassVar

from agent_framework import BaseContextProvider, Content, FunctionTool, Message, SessionContext
from agent_framework._sessions import AgentSession
from azure.ai.contentunderstanding.aio import ContentUnderstandingClient
from azure.ai.contentunderstanding.models import AnalysisResult
from azure.core.credentials import AzureKeyCredential
from azure.core.credentials_async import AsyncTokenCredential

if TYPE_CHECKING:
    from agent_framework._agents import SupportsAgentRun

from ._models import AnalysisSection, ContentLimits, DocumentEntry

logger = logging.getLogger(__name__)

AzureCredentialTypes = AzureKeyCredential | AsyncTokenCredential

SUPPORTED_MEDIA_TYPES: frozenset[str] = frozenset({
    # Documents
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/tiff",
    "image/bmp",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "text/html",
    "text/plain",
    "text/markdown",
    # Audio
    "audio/wav",
    "audio/mp3",
    "audio/mpeg",
    "audio/m4a",
    "audio/flac",
    "audio/ogg",
    # Video
    "video/mp4",
    "video/quicktime",
    "video/x-msvideo",
    "video/webm",
})


class ContentUnderstandingContextProvider(BaseContextProvider):
    """Context provider that analyzes file attachments using Azure Content Understanding.

    Automatically detects supported file attachments in the agent's input,
    analyzes them via CU, and injects the structured results (markdown, fields)
    into the LLM context. Supports multiple documents per session with background
    processing for long-running analyses.

    Args:
        endpoint: Azure Content Understanding endpoint URL.
        credential: Azure credential for authentication.
        analyzer_id: CU analyzer to use.
        max_wait: Max seconds to wait for analysis before deferring to background.
            ``None`` waits until complete.
        output_sections: Which CU output sections to pass to LLM.
        content_limits: File size/page/duration limits. ``None`` disables limits.
        source_id: Unique identifier for message attribution.
    """

    DEFAULT_SOURCE_ID: ClassVar[str] = "content_understanding"
    DEFAULT_MAX_WAIT: ClassVar[float] = 5.0
    DEFAULT_CONTENT_LIMITS: ClassVar[ContentLimits] = ContentLimits()

    def __init__(
        self,
        endpoint: str,
        credential: AzureCredentialTypes,
        *,
        analyzer_id: str = "prebuilt-documentSearch",
        max_wait: float | None = DEFAULT_MAX_WAIT,
        output_sections: list[AnalysisSection] | None = None,
        content_limits: ContentLimits | None = DEFAULT_CONTENT_LIMITS,
        source_id: str = DEFAULT_SOURCE_ID,
    ) -> None:
        super().__init__(source_id)
        self._endpoint = endpoint
        self._credential = credential
        self.analyzer_id = analyzer_id
        self.max_wait = max_wait
        self.output_sections = output_sections or [AnalysisSection.MARKDOWN, AnalysisSection.FIELDS]
        self.content_limits = content_limits
        self._client: ContentUnderstandingClient | None = None
        self._pending_tasks: dict[str, asyncio.Task[AnalysisResult]] = {}

    async def __aenter__(self) -> ContentUnderstandingContextProvider:
        self._client = ContentUnderstandingClient(self._endpoint, self._credential)
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()

    async def close(self) -> None:
        """Close the underlying CU client and cancel pending tasks."""
        for task in self._pending_tasks.values():
            if not task.done():
                task.cancel()
        self._pending_tasks.clear()
        if self._client:
            await self._client.close()
            self._client = None

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
                context.extend_messages(
                    self,
                    [
                        Message(role="user", text=self._format_result(entry["filename"], entry["result"])),
                    ],
                )
                context.extend_instructions(
                    self.source_id,
                    "A document has been analyzed using Azure Content Understanding. "
                    "The document content (markdown) and extracted fields (JSON) are provided above. "
                    "Use specific field values and cite page numbers when answering.",
                )

    # ------------------------------------------------------------------
    # File Detection
    # ------------------------------------------------------------------

    def _detect_and_strip_files(
        self,
        context: SessionContext,
    ) -> list[tuple[str, Content, bytes | None]]:
        """Detect supported files in input, strip them, and return metadata.

        Returns:
            List of (doc_key, content_item, binary_data) tuples.
        """
        results: list[tuple[str, Content, bytes | None]] = []

        for msg in context.input_messages:
            supported: list[Content] = []
            for c in msg.contents:
                if self._is_supported_content(c):
                    supported.append(c)

            for c in supported:
                doc_key = self._derive_doc_key(c)
                binary_data = self._extract_binary(c)
                results.append((doc_key, c, binary_data))

            # Strip supported files from input so raw binary isn't sent to LLM
            msg.contents = [c for c in msg.contents if not self._is_supported_content(c)]

        return results

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
    # Content Limit Checks
    # ------------------------------------------------------------------

    def _check_content_limits(self, content: Content, binary_data: bytes | None) -> str | None:
        """Check file against content limits. Returns error message or None."""
        if not self.content_limits:
            return None

        # File size check
        if binary_data:
            size_mb = len(binary_data) / (1024 * 1024)
            if size_mb > self.content_limits.max_file_size_mb:
                return f"File exceeds size limit: {size_mb:.1f} MB (max {self.content_limits.max_file_size_mb} MB)"

        return None

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
        if not self._client:
            msg = "ContentUnderstandingContextProvider not initialized. Use 'async with' or call __aenter__."
            raise RuntimeError(msg)

        media_type = content.media_type or "application/octet-stream"
        filename = doc_key

        # Check content limits
        limit_error = self._check_content_limits(content, binary_data)
        if limit_error:
            documents[doc_key] = DocumentEntry(
                status="failed",
                filename=filename,
                media_type=media_type,
                analyzer_id=self.analyzer_id,
                analyzed_at=datetime.now(tz=timezone.utc).isoformat(),
                result=None,
                error=limit_error,
            )
            context.extend_instructions(
                self.source_id,
                f"File '{filename}' was rejected: {limit_error}",
            )
            return

        try:
            # Start CU analysis
            if content.type == "uri" and content.uri and not content.uri.startswith("data:"):
                poller = await self._client.begin_analyze(
                    self.analyzer_id,
                    body={"inputs": [{"url": content.uri}]},
                )
            elif binary_data:
                poller = await self._client.begin_analyze_binary(
                    self.analyzer_id,
                    binary_input=binary_data,
                    content_type=media_type,
                )
            else:
                context.extend_instructions(
                    self.source_id,
                    f"Could not extract file data from '{filename}'.",
                )
                return

            # Wait with timeout
            if self.max_wait is not None:
                try:
                    result = await asyncio.wait_for(poller.result(), timeout=self.max_wait)
                except asyncio.TimeoutError:
                    # Defer to background
                    task = asyncio.create_task(self._background_poll(poller))
                    self._pending_tasks[doc_key] = task
                    documents[doc_key] = DocumentEntry(
                        status="pending",
                        filename=filename,
                        media_type=media_type,
                        analyzer_id=self.analyzer_id,
                        analyzed_at=None,
                        result=None,
                        error=None,
                    )
                    context.extend_instructions(
                        self.source_id,
                        f"Document '{filename}' is being analyzed. Ask about it again in a moment.",
                    )
                    return
            else:
                result = await poller.result()

            # Store successful result
            extracted = self._extract_sections(result)
            documents[doc_key] = DocumentEntry(
                status="ready",
                filename=filename,
                media_type=media_type,
                analyzer_id=self.analyzer_id,
                analyzed_at=datetime.now(tz=timezone.utc).isoformat(),
                result=extracted,
                error=None,
            )
            logger.info("Analyzed '%s' successfully.", filename)

        except asyncio.TimeoutError:
            raise
        except Exception as e:
            logger.warning("CU analysis error for '%s': %s", filename, e)
            documents[doc_key] = DocumentEntry(
                status="failed",
                filename=filename,
                media_type=media_type,
                analyzer_id=self.analyzer_id,
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
                context.extend_messages(
                    self,
                    [
                        Message(role="user", text=self._format_result(entry["filename"], extracted)),
                    ],
                )
                context.extend_instructions(
                    self.source_id,
                    f"Document '{entry['filename']}' analysis is now complete. The content is provided above.",
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
        """Extract configured sections from a CU analysis result."""
        extracted: dict[str, object] = {}
        contents = result.contents
        if not contents:
            return extracted

        content = contents[0]

        if AnalysisSection.MARKDOWN in self.output_sections and content.markdown:
            extracted["markdown"] = content.markdown

        if AnalysisSection.FIELDS in self.output_sections and content.fields:
            fields: dict[str, dict[str, object]] = {}
            for name, field in content.fields.items():
                value: object = None
                for attr in ("value_string", "value_number", "value_date", "value"):
                    value = getattr(field, attr, None)
                    if value is not None:
                        break
                confidence = getattr(field, "confidence", None)
                field_type = getattr(field, "type", None)
                fields[name] = {"type": field_type, "value": value, "confidence": confidence}
            extracted["fields"] = fields

        return extracted

    @staticmethod
    def _format_result(filename: str, result: dict[str, object]) -> str:
        """Format extracted CU result for LLM consumption."""
        parts: list[str] = [f'Document analysis of "{filename}":']

        markdown = result.get("markdown")
        if markdown:
            parts.append(f"\n## Document Content\n\n```markdown\n{markdown}\n```")

        fields = result.get("fields")
        if fields:
            fields_json = json.dumps(fields, indent=2, default=str)
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
