# Copyright (c) Microsoft. All rights reserved.

"""Azure Content Understanding context provider using ContextProvider.

This module provides ``ContentUnderstandingContextProvider``, built on the
:class:`ContextProvider` hooks pattern.  It automatically detects file
attachments, analyzes them via the Azure Content Understanding API, and
injects structured results into the LLM context.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, ClassVar, TypedDict

from agent_framework import (
    AGENT_FRAMEWORK_USER_AGENT,
    Content,
    ContextProvider,
    FunctionTool,
    Message,
    SessionContext,
)
from agent_framework._sessions import AgentSession
from agent_framework._settings import load_settings
from azure.ai.contentunderstanding.aio import ContentUnderstandingClient
from azure.ai.contentunderstanding.models import AnalysisInput, AnalysisResult
from azure.core.credentials import AzureKeyCredential
from azure.core.credentials_async import AsyncTokenCredential

if TYPE_CHECKING:
    from agent_framework._agents import SupportsAgentRun

from ._detection import (
    detect_and_strip_files,
)
from ._extraction import extract_sections, format_result
from ._models import AnalysisSection, DocumentEntry, DocumentStatus, FileSearchConfig

if sys.version_info >= (3, 11):
    from typing import Self  # pragma: no cover
else:
    from typing_extensions import Self  # pragma: no cover

logger = logging.getLogger("agent_framework.azure_contentunderstanding")

AzureCredentialTypes = AzureKeyCredential | AsyncTokenCredential

# Mapping from media type prefix to the appropriate prebuilt CU analyzer.
# Used when analyzer_id is None (auto-detect mode).
MEDIA_TYPE_ANALYZER_MAP: dict[str, str] = {
    "audio/": "prebuilt-audioSearch",
    "video/": "prebuilt-videoSearch",
}
DEFAULT_ANALYZER: str = "prebuilt-documentSearch"


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


class ContentUnderstandingContextProvider(ContextProvider):
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
            Defaults to ``["markdown", "fields"]``.
        file_search: Optional configuration for uploading CU-extracted markdown to
            a vector store for token-efficient RAG retrieval. When provided, full
            content injection is replaced by ``file_search`` tool registration.
            The ``FileSearchConfig`` abstraction is backend-agnostic — use
            ``FileSearchConfig.from_openai()`` or ``FileSearchConfig.from_foundry()``
            for supported providers, or supply a custom ``FileSearchBackend``
            implementation for other vector store services.
        source_id: Unique identifier for this provider instance, used for message
            attribution and tool registration. Defaults to ``"azure_contentunderstanding"``.
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

        ``content_range`` (str):
            Subset of the input to analyze. For documents, use 1-based page
            numbers (e.g., ``"1-3"`` for pages 1-3, ``"1,3,5-"`` for pages
            1, 3, and 5 onward). For audio/video, use milliseconds
            (e.g., ``"0-60000"`` for the first 60 seconds).

        Example::

            Content.from_data(
                pdf_bytes,
                "application/pdf",
                additional_properties={
                    "filename": "invoice.pdf",
                    "analyzer_id": "prebuilt-invoice",
                    "content_range": "1-3",
                },
            )
    """

    DEFAULT_SOURCE_ID: ClassVar[str] = "azure_contentunderstanding"
    DEFAULT_MAX_WAIT_SECONDS: ClassVar[float] = 5.0

    def __init__(
        self,
        *,
        endpoint: str | None = None,
        credential: AzureCredentialTypes | None = None,
        client: ContentUnderstandingClient | None = None,
        analyzer_id: str | None = None,
        max_wait: float | None = DEFAULT_MAX_WAIT_SECONDS,
        output_sections: list[AnalysisSection] | None = None,
        file_search: FileSearchConfig | None = None,
        source_id: str = DEFAULT_SOURCE_ID,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
    ) -> None:
        super().__init__(source_id)

        if client is not None:
            # Use the pre-built client directly — endpoint/credential are ignored.
            self._client = client
            self._owns_client = False
            self._endpoint = ""
            self._credential = None
        else:
            # Build a new client from endpoint + credential.
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
                    "Azure credential is required. Provide a 'credential' keyword argument "
                    "(e.g., AzureKeyCredential or AzureCliCredential), or pass a pre-built "
                    "'client' (ContentUnderstandingClient) instead."
                )

            self._endpoint = resolved_endpoint
            self._credential = credential
            self._client = ContentUnderstandingClient(
                self._endpoint, self._credential, user_agent=AGENT_FRAMEWORK_USER_AGENT
            )
            self._owns_client = True
        self.analyzer_id = analyzer_id
        self.max_wait = max_wait
        self.output_sections: list[AnalysisSection] = output_sections or ["markdown", "fields"]
        self.file_search = file_search
        # Global list of uploaded file IDs — used only by close() for
        # best-effort cleanup.  The authoritative per-session copy lives in
        # state["_uploaded_file_ids"] (populated in before_run).  This global
        # list may contain entries from multiple sessions; that is intentional
        # for cleanup.
        self._all_uploaded_file_ids: list[str] = []

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
        """Close the underlying CU client and clean up resources.

        Uses global tracking lists for best-effort cleanup across all
        sessions that used this provider instance.
        """
        # Clean up uploaded files; the vector store itself is caller-managed.
        if self.file_search and self._all_uploaded_file_ids:
            await self._cleanup_uploaded_files()
        # Only close the client if we created it internally.
        # When a pre-built client was passed in, the caller owns its lifecycle.
        if self._owns_client:
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

        # Per-session mutable state — isolated per session to prevent cross-session leakage.
        # _pending_tokens stores serializable continuation tokens (not asyncio.Task objects)
        # so that state can be persisted to disk/storage by the framework.
        # Structure: {doc_key: {"continuation_token": <opaque Azure SDK string>,
        #                       "analyzer_id": <CU analyzer used for this file>}}
        pending_tokens: dict[str, dict[str, str]] = state.setdefault("_pending_tokens", {})
        pending_uploads: list[tuple[str, DocumentEntry]] = state.setdefault("_pending_uploads", [])

        # 1. Resolve pending background analyses via continuation tokens
        await self._resolve_pending_tokens(pending_tokens, pending_uploads, documents, context)

        # 1b. Upload any documents that completed in the background (file_search mode)
        if pending_uploads:
            # Use a bounded timeout so before_run() stays responsive and does not block
            # indefinitely on slow vector store indexing.
            upload_timeout = getattr(self, "max_wait", None)
            remaining_uploads: list[tuple[str, DocumentEntry]] = []
            for upload_key, upload_entry in pending_uploads:
                try:
                    if upload_timeout is not None:
                        await asyncio.wait_for(
                            self._upload_to_vector_store(upload_key, upload_entry, state=state),
                            timeout=upload_timeout,
                        )
                    else:
                        await self._upload_to_vector_store(upload_key, upload_entry, state=state)
                except asyncio.TimeoutError:
                    # Leave timed-out uploads pending so they can be retried on a later turn.
                    logger.warning(
                        "Timed out while uploading document '%s' to vector store; will retry later.",
                        upload_key,
                    )
                    remaining_uploads.append((upload_key, upload_entry))
                except Exception:
                    # Log unexpected failures and drop the upload entry; this matches prior
                    # behavior where all pending uploads were cleared regardless of outcome.
                    logger.exception(
                        "Error while uploading document '%s' to vector store; dropping from pending list.",
                        upload_key,
                    )
                    context.extend_messages(
                        self.source_id,
                        [
                            Message(
                                role="user",
                                contents=[
                                    (
                                        f"Document '{upload_key}' was analyzed but failed to upload "
                                        "to the vector store. The document content is not available for search."
                                    )
                                ],
                            )
                        ],
                    )
            state["_pending_uploads"] = remaining_uploads
            pending_uploads = remaining_uploads

        # 2. Detect CU-supported file attachments, strip them from input, and return for analysis
        new_files = detect_and_strip_files(context)

        # 3. Analyze new files using CU (track elapsed time for combined timeout)
        file_start_times: dict[str, float] = {}
        accepted_keys: set[str] = set()  # doc_keys successfully accepted for analysis this turn
        for doc_key, content_item, binary_data in new_files:
            # Reject duplicate filenames — re-analyzing would orphan vector store entries
            if doc_key in documents:
                logger.warning("Duplicate document key '%s' — skipping (already exists in session).", doc_key)
                context.extend_messages(
                    self.source_id,
                    [
                        Message(
                            role="user",
                            contents=[
                                (
                                    f"The user tried to upload '{doc_key}', but a file with that name "
                                    "was already uploaded earlier in this session. The new upload was rejected "
                                    "and was not analyzed. Tell the user that a file with the same name "
                                    "already exists and they need to rename the file before uploading again."
                                )
                            ],
                        )
                    ],
                )
                continue
            file_start_times[doc_key] = time.monotonic()
            doc_entry = await self._analyze_file(doc_key, content_item, binary_data, context, pending_tokens)
            if doc_entry:
                documents[doc_key] = doc_entry
                accepted_keys.add(doc_key)

        # 4. Inject content for ready documents and register tools
        if documents:
            self._register_tools(documents, context)

        # 5. On upload turns, inject content for docs accepted this turn
        for doc_key in accepted_keys:
            entry = documents.get(doc_key)
            if entry and entry["status"] == DocumentStatus.READY and entry["result"]:
                # Upload to vector store if file_search is configured
                if self.file_search:
                    # Combined timeout: subtract CU analysis time from max_wait
                    remaining: float | None = None
                    if self.max_wait is not None:
                        elapsed = time.monotonic() - file_start_times.get(doc_key, time.monotonic())
                        remaining = max(0.0, self.max_wait - elapsed)
                    uploaded = await self._upload_to_vector_store(doc_key, entry, timeout=remaining, state=state)
                    if uploaded:
                        context.extend_messages(
                            self.source_id,
                            [
                                Message(
                                    role="user",
                                    contents=[
                                        (
                                            f"The user just uploaded '{entry['filename']}'. It has been analyzed "
                                            "using Azure Content Understanding and indexed in a vector store. "
                                            f"When using file_search, include '{entry['filename']}' in your query "
                                            "to retrieve content from this specific document."
                                        )
                                    ],
                                )
                            ],
                        )
                    elif entry.get("error"):
                        # Upload failed (not timeout — actual error)
                        context.extend_messages(
                            self.source_id,
                            [
                                Message(
                                    role="user",
                                    contents=[
                                        (
                                            f"Document '{entry['filename']}' was analyzed but failed to upload "
                                            "to the vector store. The document content is not available for search."
                                        )
                                    ],
                                )
                            ],
                        )
                    else:
                        # Upload deferred to background (timeout)
                        context.extend_messages(
                            self.source_id,
                            [
                                Message(
                                    role="user",
                                    contents=[
                                        (
                                            f"Document '{entry['filename']}' has been analyzed and is being indexed. "
                                            "Ask about it again in a moment."
                                        )
                                    ],
                                )
                            ],
                        )
                else:
                    # Without file_search, inject full content into context
                    context.extend_messages(
                        self,
                        [
                            Message(role="user", contents=[format_result(entry["filename"], entry["result"])]),
                        ],
                    )
                    context.extend_messages(
                        self.source_id,
                        [
                            Message(
                                role="user",
                                contents=[
                                    (
                                        f"The user just uploaded '{entry['filename']}'."
                                        " It has been analyzed using Azure Content Understanding."
                                        " The document content (markdown) and extracted fields"
                                        " (JSON) are provided above."
                                        " If the user's question is ambiguous,"
                                        " prioritize this most recently uploaded document."
                                        " Use specific field values and cite page numbers"
                                        " when answering."
                                    )
                                ],
                            )
                        ],
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
        for prefix, analyzer in MEDIA_TYPE_ANALYZER_MAP.items():
            if media_type.startswith(prefix):
                return analyzer
        return DEFAULT_ANALYZER

    # ------------------------------------------------------------------
    # Analysis
    # ------------------------------------------------------------------

    async def _analyze_file(
        self,
        doc_key: str,
        content: Content,
        binary_data: bytes | None,
        context: SessionContext,
        pending_tokens: dict[str, dict[str, str]] | None = None,
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
        props = content.additional_properties or {}
        per_file_analyzer = props.get("analyzer_id")
        content_range = props.get("content_range")
        resolved_analyzer = per_file_analyzer or self._resolve_analyzer_id(media_type)
        t0 = time.monotonic()

        try:
            # Start CU analysis
            if content.type == "uri" and content.uri and not content.uri.startswith("data:"):
                poller = await self._client.begin_analyze(
                    resolved_analyzer,
                    inputs=[AnalysisInput(url=content.uri, content_range=content_range)],
                )
            elif binary_data:
                poller = await self._client.begin_analyze_binary(
                    resolved_analyzer,
                    binary_input=binary_data,
                    content_type=media_type,
                )
            else:
                context.extend_messages(
                    self.source_id,
                    [Message(role="user", contents=[f"Could not extract file data from '{filename}'."])],
                )
                return None

            # Wait with timeout; defer to background polling on timeout.
            try:
                result = await asyncio.wait_for(poller.result(), timeout=self.max_wait)
            except asyncio.TimeoutError:
                # Save continuation token for resuming on next before_run().
                # Continuation tokens are serializable strings, so state can
                # be persisted to disk/storage without issues.
                token = poller.continuation_token()
                logger.info("Analysis of '%s' timed out; deferring to background via continuation token.", filename)
                if pending_tokens is not None:
                    pending_tokens[doc_key] = {
                        "continuation_token": token,
                        "analyzer_id": resolved_analyzer,
                    }
                context.extend_messages(
                    self.source_id,
                    [
                        Message(
                            role="user",
                            contents=[f"Document '{filename}' is being analyzed. Ask about it again in a moment."],
                        )
                    ],
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
            context.extend_messages(
                self.source_id,
                [Message(role="user", contents=[f"Could not analyze '{filename}': {e}"])],
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

    # ------------------------------------------------------------------
    # Pending Token Resolution
    # ------------------------------------------------------------------

    async def _resolve_pending_tokens(
        self,
        pending_tokens: dict[str, dict[str, str]],
        pending_uploads: list[tuple[str, DocumentEntry]],
        documents: dict[str, DocumentEntry],
        context: SessionContext,
    ) -> None:
        """Resume pending CU analyses using serializable continuation tokens.

        When a file's CU analysis exceeds ``max_wait``, a continuation token
        (an opaque string from the Azure SDK) is saved in ``state`` instead of
        an ``asyncio.Task``.  This keeps state fully serializable — it can be
        persisted to disk/storage by the framework.

        On the next ``before_run()`` call, this method resumes each pending
        operation by passing the token back to ``begin_analyze()``.  If the
        server-side operation has completed, the result is available
        immediately; otherwise the token is kept for the next turn.
        """
        if not pending_tokens:
            return
        logger.info("Resolving %d pending analysis token(s).", len(pending_tokens))
        completed_keys: list[str] = []

        for doc_key, token_info in pending_tokens.items():
            entry = documents.get(doc_key)
            if not entry:
                completed_keys.append(doc_key)
                continue

            try:
                poller = await self._client.begin_analyze(  # type: ignore[call-overload, reportUnknownVariableType]
                    token_info["analyzer_id"],
                    continuation_token=token_info["continuation_token"],  # pyright: ignore[reportCallIssue]
                )
                # Use wait_for to avoid blocking before_run indefinitely.
                # poller.done() always returns False for resumed pollers (stale
                # cached status), so we call poller.result() which polls the server.
                #
                # Timeout: at least 10s regardless of max_wait.  The upload-turn
                # max_wait can be very short (e.g. 5s) for responsiveness, but
                # on resolution turns the resumed poller needs a network round-trip
                # to fetch the result.  If the analysis is still running after 10s,
                # the token is kept and retried on the next turn.
                MIN_RESOLUTION_TIMEOUT = 10.0
                resolution_timeout = max(self.max_wait or MIN_RESOLUTION_TIMEOUT, MIN_RESOLUTION_TIMEOUT)
                try:
                    result: AnalysisResult = await asyncio.wait_for(
                        poller.result(),  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
                        timeout=resolution_timeout,
                    )  # pyright: ignore[reportUnknownVariableType]
                except asyncio.TimeoutError:
                    # Still running — update token and keep for next turn
                    new_token: str = poller.continuation_token()  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
                    token_info["continuation_token"] = new_token
                    logger.info("Analysis for '%s' still running; keeping token for next turn.", doc_key)
                    continue

                completed_keys.append(doc_key)
                extracted = self._extract_sections(result)  # pyright: ignore[reportUnknownArgumentType]
                entry["status"] = DocumentStatus.READY
                entry["analyzed_at"] = datetime.now(tz=timezone.utc).isoformat()
                entry["result"] = extracted
                entry["error"] = None
                logger.info("Background analysis of '%s' completed.", entry["filename"])

                # Inject newly ready content
                if self.file_search:
                    pending_uploads.append((doc_key, entry))
                else:
                    context.extend_messages(
                        self,
                        [
                            Message(role="user", contents=[format_result(entry["filename"], extracted)]),
                        ],
                    )
                context.extend_messages(
                    self.source_id,
                    [
                        Message(
                            role="user",
                            contents=[
                                f"Document '{entry['filename']}' analysis is now complete."
                                + (
                                    " The document is being indexed in the vector store and will become"
                                    " searchable via file_search shortly."
                                    if self.file_search
                                    else " The content is provided above."
                                )
                            ],
                        )
                    ],
                )

            except Exception as e:
                completed_keys.append(doc_key)
                logger.warning("Background analysis of '%s' failed: %s", entry.get("filename", doc_key), e)
                entry["status"] = DocumentStatus.FAILED
                entry["analyzed_at"] = datetime.now(tz=timezone.utc).isoformat()
                entry["error"] = str(e)
                context.extend_messages(
                    self.source_id,
                    [Message(role="user", contents=[f"Document '{entry['filename']}' analysis failed: {e}"])],
                )

        for key in completed_keys:
            del pending_tokens[key]

    # ------------------------------------------------------------------
    # Output Extraction & Formatting (delegates to _extraction module)
    # ------------------------------------------------------------------

    def _extract_sections(self, result: AnalysisResult) -> dict[str, object]:
        return extract_sections(result, self.output_sections)

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
        self,
        doc_key: str,
        entry: DocumentEntry,
        *,
        timeout: float | None = None,
        state: dict[str, Any] | None = None,
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
                per-session ``_pending_uploads`` queue for the next
                ``before_run()`` call.
            state: Per-session state dict for tracking uploaded file IDs and
                pending uploads.

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
        formatted = format_result(entry["filename"], result)
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
            # Track in per-session state and global list (for close() cleanup)
            if state is not None:
                state.setdefault("_uploaded_file_ids", []).append(file_id)
            self._all_uploaded_file_ids.append(file_id)
            entry["status"] = DocumentStatus.READY
            entry["upload_duration_s"] = upload_duration
            logger.info("Uploaded '%s' to vector store in %.1fs (%s bytes).", doc_key, upload_duration, len(formatted))
            return True

        except asyncio.TimeoutError:
            logger.info("Vector store upload for '%s' timed out; deferring to background.", doc_key)
            entry["status"] = DocumentStatus.UPLOADING
            if state is not None:
                state.setdefault("_pending_uploads", []).append((doc_key, entry))
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
            for file_id in self._all_uploaded_file_ids:
                await backend.delete_file(file_id)
            self._all_uploaded_file_ids.clear()

        except Exception as e:
            logger.warning("Failed to clean up uploaded files: %s", e)
