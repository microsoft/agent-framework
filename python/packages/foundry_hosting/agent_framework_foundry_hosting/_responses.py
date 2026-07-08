# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import tempfile
import threading
from collections.abc import AsyncIterable, AsyncIterator, Generator, Mapping, Sequence
from contextlib import AbstractAsyncContextManager, AsyncExitStack, suppress
from dataclasses import asdict, dataclass, is_dataclass
from pathlib import Path
from typing import Literal, Protocol, cast

from agent_framework import (
    ChatOptions,
    Content,
    ContextProvider,
    FileCheckpointStorage,
    HistoryProvider,
    Message,
    RawAgent,
    SupportsAgentRun,
    WorkflowAgent,
)
from agent_framework.exceptions import AgentFrameworkException
from azure.ai.agentserver.responses import (
    ResponseContext,
    ResponseEventStream,
    ResponseProviderProtocol,
    ResponsesServerOptions,
)
from azure.ai.agentserver.responses._id_generator import IdGenerator
from azure.ai.agentserver.responses.hosting import ResponsesAgentServerHost
from azure.ai.agentserver.responses.models import (
    ApplyPatchToolCallItemParam,
    ApplyPatchToolCallOutputItemParam,
    ComputerCallOutputItemParam,
    ComputerScreenshotContent,
    CreateResponse,
    FunctionCallOutputItemParam,
    FunctionShellAction,
    FunctionShellCallItemParam,
    FunctionShellCallOutputContent,
    FunctionShellCallOutputExitOutcome,
    FunctionShellCallOutputItemParam,
    Item,
    ItemCodeInterpreterToolCall,
    ItemComputerToolCall,
    ItemCustomToolCall,
    ItemCustomToolCallOutput,
    ItemFileSearchToolCall,
    ItemFunctionToolCall,
    ItemImageGenToolCall,
    ItemLocalShellToolCall,
    ItemLocalShellToolCallOutput,
    ItemMcpApprovalRequest,
    ItemMcpToolCall,
    ItemMessage,
    ItemOutputMessage,
    ItemReasoningItem,
    ItemWebSearchToolCall,
    LocalEnvironmentResource,
    MCPApprovalResponse,
    MessageContent,
    MessageContentInputFileContent,
    MessageContentInputImageContent,
    MessageContentInputTextContent,
    MessageContentOutputTextContent,
    MessageContentReasoningTextContent,
    MessageContentRefusalContent,
    MessageRole,
    OAuthConsentRequestOutputItem,
    OutputItem,
    OutputItemApplyPatchToolCall,
    OutputItemApplyPatchToolCallOutput,
    OutputItemCodeInterpreterToolCall,
    OutputItemComputerToolCall,
    OutputItemComputerToolCallOutputResource,
    OutputItemCustomToolCall,
    OutputItemCustomToolCallOutput,
    OutputItemFileSearchToolCall,
    OutputItemFunctionShellCall,
    OutputItemFunctionShellCallOutput,
    OutputItemFunctionToolCall,
    OutputItemImageGenToolCall,
    OutputItemLocalShellToolCall,
    OutputItemLocalShellToolCallOutput,
    OutputItemMcpApprovalRequest,
    OutputItemMcpApprovalResponseResource,
    OutputItemMcpToolCall,
    OutputItemMessage,
    OutputItemOutputMessage,
    OutputItemReasoningItem,
    OutputItemWebSearchToolCall,
    OutputMessageContent,
    OutputMessageContentOutputTextContent,
    OutputMessageContentRefusalContent,
    ResponseStreamEvent,
    StructuredOutputsOutputItem,
    SummaryTextContent,
    TextContent,
)
from azure.ai.agentserver.responses.streaming._builders import (
    OutputItemFunctionCallBuilder,
    OutputItemMcpCallBuilder,
    OutputItemMessageBuilder,
    OutputItemReasoningItemBuilder,
    ReasoningSummaryPartBuilder,
    TextContentBuilder,
)
from mcp import McpError
from typing_extensions import Any

logger = logging.getLogger(__name__)

_AZURE_RESPONSES_MESSAGE_ROLE_TYPE = f"{MessageRole.__module__}:{MessageRole.__qualname__}"


# region Approval Storage
class ApprovalStorage(Protocol):
    """Storage for saving function approval requests."""

    async def save_approval_request(self, approval_request_id: str, request: Content) -> None:
        """Save a function approval request under the given ID."""
        ...

    async def load_approval_request(self, approval_request_id: str) -> Content:
        """Load a function approval request by its ID."""
        ...


class InMemoryFunctionApprovalStorage:
    """An in-memory storage for function approval requests."""

    def __init__(self) -> None:
        self._store: dict[str, Content] = {}

    async def save_approval_request(self, approval_request_id: str, request: Content) -> None:
        if approval_request_id in self._store:
            raise ValueError(f"Approval request with ID '{approval_request_id}' already exists.")
        self._store[approval_request_id] = request

    async def load_approval_request(self, approval_request_id: str) -> Content:
        if approval_request_id not in self._store:
            raise KeyError(f"Approval request with ID '{approval_request_id}' does not exist.")
        return self._store[approval_request_id]


class FileBasedFunctionApprovalStorage:
    """A simple file-based storage for function approval requests.

    Concurrent writes from multiple threads in the same process are
    serialized by a ``threading.Lock``, and the on-disk JSON file is
    updated atomically (write to a temp file, then ``os.replace``) so a
    crash mid-write cannot leave a partially written file behind.
    """

    def __init__(self, storage_path: str) -> None:
        self._storage_path = storage_path
        self._lock = threading.Lock()

    def _create_storage_file_if_not_exists_sync(self) -> None:
        """Lazy-create the storage file (and its parent directory) if it does not already exist.

        Uses exclusive-create mode (``"x"``) so a concurrent creator cannot
        be truncated by an ``open(..., "w")`` after a stale existence check.
        """
        os.makedirs(os.path.dirname(self._storage_path) or ".", exist_ok=True)
        with suppress(FileExistsError), open(self._storage_path, "x") as f:
            json.dump({}, f)

    def _atomic_write(self, data: dict[str, Any]) -> None:
        """Atomically replace the storage file with the serialized ``data``."""
        directory = os.path.dirname(self._storage_path) or "."
        # Serialize first so any error doesn't leave a partial file behind.
        serialized = json.dumps(data)
        fd, tmp_path = tempfile.mkstemp(prefix=".approvals-", suffix=".tmp", dir=directory)
        try:
            with os.fdopen(fd, "w") as tmp:
                tmp.write(serialized)
            os.replace(tmp_path, self._storage_path)
        except BaseException:
            with suppress(OSError):
                os.unlink(tmp_path)
            raise

    def _save_sync(self, approval_request_id: str, request: Content) -> None:
        with self._lock:
            self._create_storage_file_if_not_exists_sync()
            with open(self._storage_path) as f:
                data = json.load(f)
            if approval_request_id in data:
                raise ValueError(f"Approval request with ID '{approval_request_id}' already exists.")
            data[approval_request_id] = request.to_dict()
            self._atomic_write(data)

    def _load_sync(self, approval_request_id: str) -> Content:
        with self._lock:
            self._create_storage_file_if_not_exists_sync()
            with open(self._storage_path) as f:
                data = json.load(f)
        if approval_request_id not in data:
            raise KeyError(f"Approval request with ID '{approval_request_id}' does not exist.")
        return Content.from_dict(data[approval_request_id])

    async def save_approval_request(self, approval_request_id: str, request: Content) -> None:
        await asyncio.to_thread(self._save_sync, approval_request_id, request)

    async def load_approval_request(self, approval_request_id: str) -> Content:
        return await asyncio.to_thread(self._load_sync, approval_request_id)


def _validate_path_segment(segment: str, *, kind: Literal["context id", "user id"]) -> None:
    """Validate that ``segment`` is a single safe path component (CWE-22).

    ``segment`` originates from caller-controlled fields (such as
    ``previous_response_id``), server-generated fields (``conversation_id`` /
    ``response_id``), or the platform-injected per-user partition key
    (``x-agent-user-id``). In every case it must be treated as an untrusted
    single path segment: path separators, drive letters, parent references and
    similar would otherwise let the resulting directory escape the configured
    storage root.

    We deliberately do not URL-decode the value here: the hosting layer never
    decodes these ids before joining them, so forms such as ``%2e%2e`` are
    accepted as literal directory names. Do NOT add decoding here without
    re-validating after the decode -- decode-then-join is exactly the pattern
    that reintroduces traversal. We also do not attempt to "sanitize" by
    stripping characters because that can introduce collisions between distinct
    ids.
    """
    if not isinstance(segment, str) or not segment:
        raise RuntimeError(f"Invalid {kind}: must be a non-empty string.")
    # Reject any value that is not a single safe path component. This covers
    # POSIX/Windows separators, NUL bytes, drive letters, and all-dot segments
    # (``.``, ``..``, ``...``, ...).
    if (
        "/" in segment
        or "\\" in segment
        or "\x00" in segment
        # All-dot segments (``.``, ``..``, ``...``, ...) reduce to "" after stripping dots.
        or segment.strip(".") == ""
        or os.path.isabs(segment)
        or os.path.splitdrive(segment)[0]
    ):
        raise RuntimeError(f"Invalid {kind}: {segment!r}")


def _checkpoint_storage_for_context(root: str, context_id: str, *, user_id: str | None = None) -> FileCheckpointStorage:
    """Build a ``FileCheckpointStorage`` for ``context_id`` rooted under ``root``.

    When the platform supplies a per-user partition key (``user_id``, from the
    ``x-agent-user-id`` header on container protocol v2), the per-conversation
    checkpoint directory is nested under it: ``<root>/<user_id>/<context_id>``.
    This isolates each tenant's workflow state so one user can never restore or
    observe another user's checkpoint, even with a guessed or forged
    ``context_id``. An absent (``None``) or empty ``user_id`` -- local
    development or protocol v1 -- falls back to the unscoped
    ``<root>/<context_id>`` layout.

    Both ``context_id`` and ``user_id`` are validated as single safe path
    segments, and each resolved directory is verified to stay under its parent
    before any directory is created on disk (CWE-22).
    """
    _validate_path_segment(context_id, kind="context id")

    base_path = Path(root).resolve()
    if user_id:
        _validate_path_segment(user_id, kind="user id")
        user_path = (base_path / user_id).resolve()
        if not user_path.is_relative_to(base_path):
            raise RuntimeError(f"Invalid user id: {user_id!r}")
        base_path = user_path

    storage_path = (base_path / context_id).resolve()
    if not storage_path.is_relative_to(base_path):
        raise RuntimeError(f"Invalid context id: {context_id!r}")
    return FileCheckpointStorage(
        storage_path,
        # Keep this provider-specific allowlist narrow. Hosted workflow
        # checkpoints can persist Azure's role enum inside Message objects.
        allowed_checkpoint_types=[_AZURE_RESPONSES_MESSAGE_ROLE_TYPE],
    )


def _approval_storage_path_for_user(base_path: str, user_id: str) -> str:
    """Return the per-user approval storage file path under the base directory.

    Inserts the validated ``user_id`` as a directory segment between the base
    directory and the file name (``<dir>/<user_id>/<file>``), mirroring the
    per-user checkpoint partitioning so one tenant can never read another
    tenant's saved approval requests. The user id is validated as a single safe
    path segment and the resulting directory is verified to stay under the base
    directory before use (CWE-22).
    """
    _validate_path_segment(user_id, kind="user id")
    directory, filename = os.path.split(base_path)
    base_dir = Path(directory or ".").resolve()
    user_dir = (base_dir / user_id).resolve()
    if not user_dir.is_relative_to(base_dir):
        raise RuntimeError(f"Invalid user id: {user_id!r}")
    return str(user_dir / filename)


# endregion Approval Storage

# Foundry Toolbox Auth integration
# Consent-URL error code returned by the Foundry MCP gateway when calling `/list`
CONSENT_ERROR_CODE = -32006


@dataclass
class ConsentError:
    name: str
    consent_url: str


def consent_url_from_error(exc: BaseException) -> list[ConsentError] | None:
    """Return the consent URLs when ``exc`` wraps Foundry MCP gateway consent errors.

    Args:
        exc: The exception to inspect.

    Returns:
        The consent URL(s) extracted from the error, or ``None`` if no consent error was found.
    """
    inner_exception = next((arg for arg in exc.args if isinstance(arg, McpError)), None)
    if inner_exception is not None and inner_exception.error.code == CONSENT_ERROR_CODE:
        # Parse the error message
        # The error message is structured with the following format:
        # "tools/list failed for 1 tool source(s), succeeded for 0 tool source(s) {"errors":[{"name": ..."
        # where the second part is a JSON string that can be deserialized into an object with the following shape:
        # ruff: disable[ERA001]
        # {
        #   "errors" : [
        #       {
        #           "name": "Name of the MCP tool that requires consent",
        #           "type" : "mcp",
        #           "error": {
        #               "code": "CONSENT_REQUIRED",
        #               "message": consent_url,
        #           }
        #       }
        #   ]
        # }
        # ruff: enable[ERA001]
        try:
            consent_errors: list[ConsentError] = []
            error_message_start = inner_exception.error.message.find("{")
            if error_message_start == -1:
                logger.warning("Consent error message does not contain JSON: %s", inner_exception.error.message)
                return None
            consent_details_json = inner_exception.error.message[error_message_start:]
            consent_details = json.loads(consent_details_json)
            if "errors" not in consent_details or not isinstance(consent_details["errors"], list):
                logger.warning("Consent error message JSON does not contain 'errors' list: %s", consent_details_json)
                return None
            for error in consent_details["errors"]:
                if (
                    isinstance(error, dict)
                    and error.get("type") == "mcp"  # type: ignore
                    and "error" in error
                    and isinstance(error["error"], dict)
                    and error["error"].get("code") == "CONSENT_REQUIRED"  # type: ignore
                    and "message" in error["error"]
                ):
                    consent_url = error["error"]["message"]  # type: ignore
                    if isinstance(consent_url, str):
                        consent_errors.append(ConsentError(name=error.get("name", "Unknown"), consent_url=consent_url))  # type: ignore
                    else:
                        logger.warning("Consent URL in error message is not a valid URL: %s", consent_url)  # type: ignore
            if consent_errors:
                return consent_errors
        except json.JSONDecodeError:
            logger.warning("Failed to parse consent details JSON: %s", inner_exception.error.message)
    return None


# endregion Foundry Toolbox Auth integration


# region ResponsesHostServer
class ResponsesHostServer(ResponsesAgentServerHost):
    """A responses server host for an agent."""

    # TODO(@taochen): Allow a different checkpoint storage that stores checkpoints externally
    CHECKPOINT_STORAGE_PATH = "/.checkpoints"
    FUNCTION_APPROVAL_STORAGE_PATH = "/.function_approvals/approval_requests.json"

    def __init__(
        self,
        agent: SupportsAgentRun,
        *,
        prefix: str = "",
        options: ResponsesServerOptions | None = None,
        store: ResponseProviderProtocol | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize a ResponsesHostServer.

        Args:
            agent: The agent to handle responses for.
            prefix: The URL prefix for the server.
            options: Optional server options.
            store: Optional response store.
            **kwargs: Additional keyword arguments.

        Note:
            1. The agent must not have a history provider with `load_messages=True`,
               because history is managed by the hosting infrastructure.
            2. The agent must not have any context providers that maintain context
               in memory, because the hosting environment may get deactivated between
               requests, and any in-memory context would be lost.
        """
        super().__init__(prefix=prefix, options=options, store=store, **kwargs)

        for provider in getattr(agent, "context_providers", []):
            if isinstance(provider, HistoryProvider) and provider.load_messages:
                raise RuntimeError(
                    "There shouldn't be a history provider with `load_messages=True` already present. "
                    "History is managed by the hosting infrastructure."
                )
            provider = cast(ContextProvider, provider)
            logger.warning(
                "Context provider %s is present. If it maintains context in memory, "
                "the context may be lost between requests. Use with caution.",
                provider.source_id,
            )

        self._is_workflow_agent = False
        self._checkpoint_storage_path = None
        if isinstance(agent, WorkflowAgent):
            if agent.workflow._runner_context.has_checkpointing():  # pyright: ignore[reportPrivateUsage]
                raise RuntimeError(
                    "There should not be a checkpoint storage already present in the workflow agent. "
                    "The hosting infrastructure will manage checkpoints instead."
                )
            self._checkpoint_storage_path = (
                self.CHECKPOINT_STORAGE_PATH
                if self.config.is_hosted
                else os.path.join(os.getcwd(), self.CHECKPOINT_STORAGE_PATH.lstrip("/"))
            )
            self._is_workflow_agent = True

        self._agent = agent
        self._approval_storage = (
            FileBasedFunctionApprovalStorage(self.FUNCTION_APPROVAL_STORAGE_PATH)
            if self.config.is_hosted
            else InMemoryFunctionApprovalStorage()
        )
        # Per-user (multi-tenant) approval stores. Hosted file-based approval
        # storage is partitioned by the platform per-user partition key so one
        # tenant can never read another tenant's saved approval requests.
        # Instances are cached so concurrent requests for the same user share one
        # lock, preserving serialized read-modify-write on the JSON file. Local
        # (in-memory) dev and protocol v1 (no user id) keep the single shared
        # ``self._approval_storage``.
        self._approval_storages_by_user: dict[str, ApprovalStorage] = {}
        # Lazy agent lifecycle: the agent (and any MCP tools it owns) is entered on
        # the first request rather than at server startup, so that authentication
        # failures during MCP connect can be surfaced to the client as an
        # `oauth_consent_request` stream event instead of crashing the server.
        self._agent_stack: AsyncExitStack | None = None
        self._agent_init_lock = asyncio.Lock()
        self.shutdown_handler(self._cleanup_agent)
        self.response_handler(self._handle_response)

    async def _ensure_agent_ready(self) -> None:
        """Lazily enter the agent's async context exactly once.

        On failure the partial exit stack is closed and ``_agent_stack`` is left
        as ``None`` so a subsequent request (e.g. after the user completes OAuth
        consent) can retry the connection.
        """
        if self._agent_stack is not None:
            return
        async with self._agent_init_lock:
            if self._agent_stack is not None:
                return
            stack = AsyncExitStack()
            try:
                if isinstance(self._agent, AbstractAsyncContextManager):
                    await stack.enter_async_context(self._agent)
            except BaseException:
                await stack.aclose()
                raise
            self._agent_stack = stack

    async def _cleanup_agent(self) -> None:
        """Close the agent's async context. Registered as the server shutdown handler."""
        stack = self._agent_stack
        if stack is not None:
            self._agent_stack = None
            await stack.aclose()

    def _approval_storage_for_user(self, user_id: str | None) -> ApprovalStorage:
        """Return the approval storage scoped to ``user_id`` when applicable.

        For hosted multi-tenant deployments the file-based store is partitioned
        by the platform per-user partition key, so one tenant can never read
        another tenant's saved approval requests. Falls back to the single shared
        store for local (in-memory) hosting or when no per-user partition key is
        available (protocol v1 / local development). Instances are cached so
        concurrent requests for the same user share one lock.

        Raises:
            RuntimeError: If ``user_id`` is not a safe single path segment.
        """
        if not self.config.is_hosted or not user_id:
            return self._approval_storage
        storage = self._approval_storages_by_user.get(user_id)
        if storage is None:
            storage = FileBasedFunctionApprovalStorage(
                _approval_storage_path_for_user(self.FUNCTION_APPROVAL_STORAGE_PATH, user_id)
            )
            self._approval_storages_by_user[user_id] = storage
        return storage

    async def _handle_response(
        self,
        request: CreateResponse,
        context: ResponseContext,
        cancellation_signal: asyncio.Event,
    ) -> AsyncIterable[ResponseStreamEvent | dict[str, Any]]:
        """Handle the creation of a response."""
        # Fail fast if the service is on protocol v1.0.0
        if self.config.is_hosted and context.platform_context.call_id is None:
            raise RuntimeError(
                "The hosted environment is running on protocol 1.0.0, but the agent requires protocol 2.0.0. "
                "Please upgrade your agent protocol to 2.0.0 in `agent.manifest.yaml` or `agent.yaml`, or "
                "downgrade the `agent-framework-foundry-hosting` package to `1.0.0a260625` or before to use 1.0.0."
            )

        if self._is_workflow_agent:
            # Workflow agents are handled differently because they require checkpoint restoration
            return self._handle_inner_workflow(request, context)
        return self._handle_inner_agent(request, context)

    async def _handle_inner_agent(
        self,
        request: CreateResponse,
        context: ResponseContext,
    ) -> AsyncIterable[ResponseStreamEvent | dict[str, Any]]:
        """Handle the creation of a response for a regular (non-workflow) agent."""
        response_event_stream = ResponseEventStream(response_id=context.response_id, model=request.model)
        yield response_event_stream.emit_created()
        yield response_event_stream.emit_in_progress()

        # Track the current active output item builder for streaming;
        # lazily created on matching content, closed when a different type arrives.
        tracker: _OutputItemTracker | None = None

        try:
            user_id = context.platform_context.user_id_key
            approval_storage = self._approval_storage_for_user(user_id)
            input_items = await context.get_input_items()
            input_messages = await _items_to_messages(input_items, approval_storage=approval_storage)

            history = await context.get_history()
            run_kwargs: dict[str, Any] = {
                "messages": [
                    *(await _output_items_to_messages(history, approval_storage=approval_storage)),
                    *input_messages,
                ]
            }
            is_streaming_request = request.stream is not None and request.stream is True

            chat_options, are_options_set = _to_chat_options(request)

            if are_options_set and not isinstance(self._agent, RawAgent):
                logger.warning("Agent doesn't support runtime options. They will be ignored.")
            else:
                run_kwargs["options"] = chat_options

            # Lazy-enter the agent (and any MCP tools it owns). The MCP client wraps gateway
            # consent failures (and other connection-time errors) in AgentFrameworkException; if
            # one of those is a consent error we surface the consent link to the client through
            # the already-opened response stream instead of failing the request. Other exception
            # types fall through to the outer handler below and become ``response.failed``.
            try:
                await self._ensure_agent_ready()
            except AgentFrameworkException as ex:
                consent_errors = consent_url_from_error(ex)
                if consent_errors is None:
                    raise
                for consent_error in consent_errors:
                    logger.warning("Consent URL for tool '%s': %s", consent_error.name, consent_error.consent_url)
                    oauth_item = OAuthConsentRequestOutputItem(
                        id=IdGenerator.new_id("oacr"),
                        consent_link=consent_error.consent_url,
                        server_label=consent_error.name,
                    )
                    builder = response_event_stream.add_output_item(oauth_item.id)
                    yield builder.emit_added(oauth_item)
                    yield builder.emit_done(oauth_item)
                yield response_event_stream.emit_completed()
                return

            tracker = _OutputItemTracker(response_event_stream) if is_streaming_request else None

            if not is_streaming_request:
                # Run the agent in non-streaming mode
                response = await self._agent.run(stream=False, **run_kwargs)  # type: ignore[reportUnknownMemberType]

                async for item in _to_outputs_for_messages(
                    response_event_stream,
                    response.messages,
                    approval_storage=approval_storage,
                ):
                    yield item
            else:
                if tracker is None:  # pragma: no cover - defensive, set above
                    raise RuntimeError("Streaming tracker was not initialized.")
                # Run the agent in streaming mode
                async for update in self._agent.run(stream=True, **run_kwargs):  # type: ignore[reportUnknownMemberType]
                    for content in update.contents:
                        for event in tracker.handle(content):
                            yield event
                        if tracker.needs_async:
                            async for item in _to_outputs(
                                response_event_stream,
                                content,
                                approval_storage=approval_storage,
                            ):
                                yield item
                            tracker.needs_async = False

                # Close any remaining active builder
                for event in tracker.close():
                    yield event
            yield response_event_stream.emit_completed()
        except Exception as ex:
            logger.exception("Failed to produce response for agent")
            for event in self._emit_failure(response_event_stream, tracker, ex):
                yield event

    async def _handle_inner_workflow(
        self,
        request: CreateResponse,
        context: ResponseContext,
    ) -> AsyncIterable[ResponseStreamEvent | dict[str, Any]]:
        """Handle the creation of a response for a workflow agent."""
        response_event_stream = ResponseEventStream(response_id=context.response_id, model=request.model)
        yield response_event_stream.emit_created()
        yield response_event_stream.emit_in_progress()

        # Track the current active output item builder for streaming;
        # lazily created on matching content, closed when a different type arrives.
        tracker: _OutputItemTracker | None = None

        try:
            user_id = context.platform_context.user_id_key
            approval_storage = self._approval_storage_for_user(user_id)
            input_items = await context.get_input_items()
            input_messages = await _items_to_messages(input_items, approval_storage=approval_storage)
            is_streaming_request = request.stream is not None and request.stream is True

            _, are_options_set = _to_chat_options(request)
            if are_options_set:
                logger.warning("Workflow agent doesn't support runtime options. They will be ignored.")

            if request.previous_response_id is not None and context.conversation_id is not None:
                raise RuntimeError("Previous response ID cannot be used in conjunction with conversation ID.")
            context_id = request.previous_response_id or context.conversation_id

            # The following should never happen due to the checks above.
            # This is for type safety and defensive programming.
            if self._checkpoint_storage_path is None:
                raise RuntimeError("Checkpoint storage path is not configured for workflow agent.")
            if not isinstance(self._agent, WorkflowAgent):
                raise RuntimeError("Agent is not a workflow agent.")

            # Workflow agents are not async context managers in any built-in path,
            # but call _ensure_agent_ready for symmetry with the regular path so
            # any future async resources owned by the workflow are entered here.
            await self._ensure_agent_ready()

            # Per-user checkpoint isolation for multi-tenant hosting (container
            # protocol v2): the per-user partition key computed above
            # (``x-agent-user-id``) scopes every checkpoint directory for this turn,
            # so one tenant can never restore or observe another tenant's workflow
            # state -- even with a guessed or forged context id. The key is stable
            # per user across turns, so multi-turn continuity is preserved. Absent
            # (``None``)/empty in local development or protocol v1, where the
            # unscoped single-tenant layout is used.

            # Determine the latest checkpoint (if any) so we can resume the
            # workflow's prior state for this turn. The directory is keyed by
            # the inbound context id (conversation_id when set, otherwise
            # previous_response_id). Multi-turn declarative workflows need the
            # workflow's internal state (e.g. Conversation.messages,
            # intermediate Local.* variables) to survive across user turns;
            # the only place that state lives is the workflow checkpoint, so
            # on every turn we restore the latest checkpoint and feed the new
            # input back into the start executor as a continuation rather than
            # a fresh run.
            latest_checkpoint_id: str | None = None
            restore_storage: FileCheckpointStorage | None = None
            if context_id is not None:
                restore_storage = _checkpoint_storage_for_context(
                    self._checkpoint_storage_path, context_id, user_id=user_id
                )
                latest_checkpoint = await restore_storage.get_latest(workflow_name=self._agent.workflow.name)
                if latest_checkpoint is not None:
                    latest_checkpoint_id = latest_checkpoint.checkpoint_id

            # Storage that will receive checkpoints written during this turn.
            # When the caller chains with previous_response_id, the next turn
            # will reference the current response_id as its previous_response_id,
            # so new checkpoints must land under the current response_id (or the
            # conversation_id when set). When conversation_id is set, this
            # matches restore_storage; when only previous_response_id was
            # supplied, restore_storage points at the *prior* response's
            # directory and write_storage points at the *current* response's.
            write_context_id = context.conversation_id or context.response_id
            write_storage = _checkpoint_storage_for_context(
                self._checkpoint_storage_path, write_context_id, user_id=user_id
            )

            # Multi-turn pattern: when we have a prior checkpoint, restore it
            # first (drive the workflow back to idle with prior state intact),
            # then make a separate call that delivers the new user input. This
            # depends on Workflow.run preserving shared state across calls. The
            # restore-only call may yield events from any pending in-flight
            # work in the checkpoint; we consume those internally here so they
            # don't surface to the response stream as duplicates.
            #
            # If the restored checkpoint had pending request_info events, the
            # restore-only call replays them through
            # ``WorkflowAgent._convert_workflow_event_to_agent_response_updates``
            # and populates ``self._agent.pending_requests``. That is the correct
            # state: those requests are genuinely outstanding, and the next
            # ``run(input_messages, ...)`` call may contain ``function_call_output``
            # items (carried as FunctionResult/FunctionApprovalResponse content)
            # that fulfill them via :meth:`WorkflowAgent._process_pending_requests`.
            if latest_checkpoint_id is not None:
                if is_streaming_request:
                    async for _ in self._agent.run(
                        stream=True,
                        checkpoint_id=latest_checkpoint_id,
                        checkpoint_storage=restore_storage,
                    ):
                        pass
                else:
                    await self._agent.run(
                        stream=False,
                        checkpoint_id=latest_checkpoint_id,
                        checkpoint_storage=restore_storage,
                    )

            if not is_streaming_request:
                # Run the agent in non-streaming mode with the new user input.
                response = await self._agent.run(
                    input_messages,
                    stream=False,
                    checkpoint_storage=write_storage,
                )

                async for item in _to_outputs_for_messages(
                    response_event_stream,
                    response.messages,
                    approval_storage=approval_storage,
                ):
                    yield item

                await self._delete_not_latest_checkpoints(write_storage, self._agent.workflow.name)
                yield response_event_stream.emit_completed()
                return

            tracker = _OutputItemTracker(response_event_stream)

            # Run the workflow agent in streaming mode with the new user input.
            async for update in self._agent.run(
                input_messages,
                stream=True,
                checkpoint_storage=write_storage,
            ):
                for content in update.contents:
                    for event in tracker.handle(content):
                        yield event
                    if tracker.needs_async:
                        async for item in _to_outputs(
                            response_event_stream, content, approval_storage=approval_storage
                        ):
                            yield item
                        tracker.needs_async = False

            # Close any remaining active builder
            for event in tracker.close():
                yield event

            await self._delete_not_latest_checkpoints(write_storage, self._agent.workflow.name)
            yield response_event_stream.emit_completed()
        except Exception as ex:
            logger.exception("Failed to produce response for workflow agent")
            for event in self._emit_failure(response_event_stream, tracker, ex):
                yield event

    @staticmethod
    async def _delete_not_latest_checkpoints(checkpoint_storage: FileCheckpointStorage, workflow_name: str) -> None:
        """Delete all checkpoints except the latest one.

        We only need the last checkpoint for each invocation.
        """
        latest_checkpoint = await checkpoint_storage.get_latest(workflow_name=workflow_name)
        if latest_checkpoint is not None:
            all_checkpoints = await checkpoint_storage.list_checkpoints(workflow_name=workflow_name)
            for checkpoint in all_checkpoints:
                if checkpoint.checkpoint_id != latest_checkpoint.checkpoint_id:
                    await checkpoint_storage.delete(checkpoint.checkpoint_id)

    @staticmethod
    def _emit_failure(
        response_event_stream: ResponseEventStream,
        tracker: _OutputItemTracker | None,
        ex: BaseException,
    ) -> Generator[ResponseStreamEvent]:
        """Yield a terminal ``response.failed`` event for ``ex``.

        Drains any in-progress streaming output item first so the resulting
        SSE stream stays well-formed, then emits ``response.failed`` carrying
        the exception's message (falling back to the exception type name when
        ``str(ex)`` is empty). Any error raised while draining the tracker is
        logged and otherwise ignored so that the original failure is always
        what the client sees.
        """
        if tracker is not None:
            try:
                yield from tracker.close()
            except Exception:
                logger.exception("Error while closing streaming tracker after failure")
        message = str(ex) or type(ex).__name__
        yield response_event_stream.emit_failed(message=message)


# endregion ResponsesHostServer

# region Active Builder State


class _OutputItemTracker:
    """Tracks the current active output item builder during streaming.

    Handles lazy creation, delta emission, and closing of streaming builders
    for text messages, reasoning, function calls, and MCP calls.
    """

    _DELTA_TYPES = frozenset({"text", "text_reasoning", "function_call", "mcp_server_tool_call"})

    def __init__(self, stream: ResponseEventStream) -> None:
        self._stream = stream
        self._active_type: str | None = None
        self._active_id: str | None = None
        # Accumulated delta text for the current active builder
        self._accumulated: list[str] = []
        # Builder state — only one is active at a time
        self._message_item: OutputItemMessageBuilder | None = None
        self._text_content: TextContentBuilder | None = None
        self._reasoning_item: OutputItemReasoningItemBuilder | None = None
        self._summary_part: ReasoningSummaryPartBuilder | None = None
        self._fc_builder: OutputItemFunctionCallBuilder | None = None
        self._mcp_builder: OutputItemMcpCallBuilder | None = None
        self.needs_async = False

    def handle(self, content: Content) -> Generator[ResponseStreamEvent]:
        """Process a content item, yielding sync events.

        Sets ``needs_async = True`` if the caller must also drain an
        async ``_to_outputs`` call for this content.
        """
        if content.type == "text" and content.text is not None:
            if self._active_type != "text":
                yield from self._close()
                yield from self._open_message()
            self._accumulated.append(content.text)
            if self._text_content is not None:
                yield self._text_content.emit_delta(content.text)

        elif content.type == "text_reasoning" and content.text is not None:
            if self._active_type != "text_reasoning":
                yield from self._close()
                yield from self._open_reasoning()
            self._accumulated.append(content.text)
            if self._summary_part is not None:
                yield self._summary_part.emit_text_delta(content.text)

        elif content.type == "function_call" and content.call_id is not None:
            if self._active_type != "function_call" or self._active_id != content.call_id:
                yield from self._close()
                yield from self._open_function_call(content)
            args_str = _arguments_to_str(content.arguments)
            self._accumulated.append(args_str)
            if self._fc_builder is not None:
                yield self._fc_builder.emit_arguments_delta(args_str)

        elif content.type == "mcp_server_tool_call" and content.tool_name:
            key = content.call_id or f"{content.server_name or 'default'}::{content.tool_name}"
            if self._active_type != "mcp_server_tool_call" or self._active_id != key:
                yield from self._close()
                yield from self._open_mcp_call(content)
            args_str = _arguments_to_str(content.arguments)
            self._accumulated.append(args_str)
            if self._mcp_builder is not None:
                yield self._mcp_builder.emit_arguments_delta(args_str)

        elif (
            content.type == "mcp_server_tool_result"
            and self._active_type == "mcp_server_tool_call"
            and self._mcp_builder is not None
            and content.call_id is not None
            and content.call_id == self._mcp_builder.item_id
        ):
            accumulated = "".join(self._accumulated)
            yield self._mcp_builder.emit_arguments_done(accumulated)
            yield self._mcp_builder.emit_completed()
            yield self._mcp_builder.emit_done(output=_stringify_mcp_output(content.output))
            self._mcp_builder = None
            self._active_type = None
            self._active_id = None
            self._accumulated.clear()
            self.needs_async = False
            return

        else:
            yield from self._close()
            self.needs_async = True

    def close(self) -> Generator[ResponseStreamEvent]:
        """Close any remaining active builder."""
        yield from self._close()

    # -- Private open/close helpers --

    def _open_message(self) -> Generator[ResponseStreamEvent]:
        self._message_item = self._stream.add_output_item_message()
        self._text_content = self._message_item.add_text_content()
        self._active_type = "text"
        self._active_id = None
        yield self._message_item.emit_added()
        yield self._text_content.emit_added()

    def _open_reasoning(self) -> Generator[ResponseStreamEvent]:
        self._reasoning_item = self._stream.add_output_item_reasoning_item()
        self._summary_part = self._reasoning_item.add_summary_part()
        self._active_type = "text_reasoning"
        self._active_id = None
        yield self._reasoning_item.emit_added()
        yield self._summary_part.emit_added()

    def _open_function_call(self, content: Content) -> Generator[ResponseStreamEvent]:
        self._fc_builder = self._stream.add_output_item_function_call(
            name=content.name or "",
            call_id=content.call_id or "",
        )
        self._active_type = "function_call"
        self._active_id = content.call_id
        yield self._fc_builder.emit_added()

    def _open_mcp_call(self, content: Content) -> Generator[ResponseStreamEvent]:
        self._mcp_builder = self._stream.add_output_item_mcp_call(
            server_label=content.server_name or "default",
            name=content.tool_name or "",
            item_id=content.call_id,
        )
        self._active_type = "mcp_server_tool_call"
        self._active_id = content.call_id or f"{content.server_name or 'default'}::{content.tool_name}"
        yield self._mcp_builder.emit_added()

    def _close(self) -> Generator[ResponseStreamEvent]:
        accumulated = "".join(self._accumulated)

        if self._active_type == "text" and self._text_content and self._message_item:
            yield self._text_content.emit_text_done(accumulated)
            yield self._text_content.emit_done()
            yield self._message_item.emit_done()
            self._text_content = None
            self._message_item = None

        elif self._active_type == "text_reasoning" and self._summary_part and self._reasoning_item:
            yield self._summary_part.emit_text_done(accumulated)
            yield self._summary_part.emit_done()
            yield self._reasoning_item.emit_done()
            self._summary_part = None
            self._reasoning_item = None

        elif self._active_type == "function_call" and self._fc_builder:
            yield self._fc_builder.emit_arguments_done(accumulated)
            yield self._fc_builder.emit_done()
            self._fc_builder = None

        elif self._active_type == "mcp_server_tool_call" and self._mcp_builder:
            yield self._mcp_builder.emit_arguments_done(accumulated)
            yield self._mcp_builder.emit_completed()
            yield self._mcp_builder.emit_done()
            self._mcp_builder = None

        self._active_type = None
        self._active_id = None
        self._accumulated.clear()


# endregion


# region Option Conversion


def _to_chat_options(request: CreateResponse) -> tuple[ChatOptions, bool]:
    """Converts a CreateResponse request to ChatOptions.

    Args:
        request (CreateResponse): The request to convert.

    Returns:
        ChatOptions: The converted ChatOptions.
        bool: Whether any options were set.

    """
    chat_options = ChatOptions()
    are_options_set = False

    if request.temperature is not None:
        chat_options["temperature"] = request.temperature
        are_options_set = True
    if request.top_p is not None:
        chat_options["top_p"] = request.top_p
        are_options_set = True
    if request.max_output_tokens is not None:
        chat_options["max_tokens"] = request.max_output_tokens
        are_options_set = True
    if request.parallel_tool_calls is not None:
        chat_options["allow_multiple_tool_calls"] = request.parallel_tool_calls
        are_options_set = True

    return chat_options, are_options_set


# endregion


# region Input Message Conversion


async def _items_to_messages(
    input_items: Sequence[Item], *, approval_storage: ApprovalStorage | None = None
) -> list[Message]:
    """Converts a sequence of input items to a list of Messages, one per item.

    Args:
        input_items: The input items to convert.
        approval_storage: An optional ApprovalStorage instance used to look up
            approval requests when converting MCP approval response items.

    Returns:
        A list of Messages, one per supported input item.
    """
    messages: list[Message] = []
    for item in input_items:
        messages.append(await _item_to_message(item, approval_storage=approval_storage))
    return messages


async def _item_to_message(item: Item, *, approval_storage: ApprovalStorage | None = None) -> Message:
    """Converts an Item to a Message.

    Args:
        item: The Item to convert.
        approval_storage: An optional ApprovalStorage instance used to look up
            approval requests when converting MCP approval response items.

    Returns:
        The converted Message.

    Raises:
        ValueError: If the Item type is not supported.
    """
    if item.type == "message":
        msg = cast(ItemMessage, item)
        if isinstance(msg.content, str):
            return Message(role=msg.role, contents=[Content.from_text(msg.content)])
        return Message(role=msg.role, contents=[_convert_message_content(part) for part in msg.content])

    if item.type == "output_message":
        output_msg = cast(ItemOutputMessage, item)
        return Message(
            role=output_msg.role, contents=[_convert_output_message_content(part) for part in output_msg.content]
        )

    if item.type == "function_call":
        fc = cast(ItemFunctionToolCall, item)
        return Message(
            role="assistant",
            contents=[Content.from_function_call(fc.call_id, fc.name, arguments=fc.arguments)],
        )

    if item.type == "function_call_output":
        fco = cast(FunctionCallOutputItemParam, item)
        output = fco.output if isinstance(fco.output, str) else str(fco.output)
        return Message(
            role="tool",
            contents=[Content.from_function_result(fco.call_id, result=output)],
        )

    if item.type == "reasoning":
        reasoning = cast(ItemReasoningItem, item)
        reason_contents: list[Content] = []
        if reasoning.summary:
            for summary in reasoning.summary:
                reason_contents.append(Content.from_text(summary.text))
        return Message(role="assistant", contents=reason_contents)

    if item.type == "mcp_call":
        mcp = cast(ItemMcpToolCall, item)
        contents = [
            Content.from_mcp_server_tool_call(
                mcp.id,
                mcp.name,
                server_name=mcp.server_label,
                arguments=mcp.arguments,
            )
        ]
        if getattr(mcp, "output", None) is not None:
            contents.append(Content.from_mcp_server_tool_result(call_id=mcp.id, output=mcp.output))
        return Message(
            role="assistant",
            contents=contents,
        )

    if item.type == "mcp_approval_request":
        mcp_req = cast(ItemMcpApprovalRequest, item)
        if approval_storage is not None:
            function_approval_request_content = await approval_storage.load_approval_request(mcp_req.id)
        else:
            raise ValueError("ApprovalStorage is required to load approval request.")
        return Message(
            role="assistant",
            contents=[function_approval_request_content],
        )

    if item.type == "mcp_approval_response":
        mcp_resp = cast(MCPApprovalResponse, item)
        if approval_storage is not None:
            function_approval_request_content = await approval_storage.load_approval_request(
                mcp_resp.approval_request_id
            )
        else:
            raise ValueError("ApprovalStorage is required to load approval request.")
        return Message(
            role="user",
            contents=[function_approval_request_content.to_function_approval_response(mcp_resp.approve)],
        )

    if item.type == "code_interpreter_call":
        ci = cast(ItemCodeInterpreterToolCall, item)
        return Message(
            role="assistant",
            contents=[Content.from_code_interpreter_tool_call(call_id=ci.id)],
        )

    if item.type == "image_generation_call":
        ig = cast(ItemImageGenToolCall, item)
        return Message(
            role="assistant",
            contents=[Content.from_image_generation_tool_call(image_id=ig.id)],
        )

    if item.type == "shell_call":
        sc = cast(FunctionShellCallItemParam, item)
        return Message(
            role="assistant",
            contents=[
                Content.from_shell_tool_call(
                    call_id=sc.call_id,
                    commands=sc.action.commands,
                    status=str(sc.status),
                )
            ],
        )

    if item.type == "shell_call_output":
        sco = cast(FunctionShellCallOutputItemParam, item)
        outputs = [
            Content.from_shell_command_output(
                stdout=out.stdout or "",
                stderr=out.stderr or "",
                exit_code=getattr(out.outcome, "exit_code", None) if hasattr(out, "outcome") else None,
            )
            for out in (sco.output or [])
        ]
        return Message(
            role="tool",
            contents=[
                Content.from_shell_tool_result(
                    call_id=sco.call_id,
                    outputs=outputs,
                    max_output_length=sco.max_output_length,
                )
            ],
        )

    if item.type == "local_shell_call":
        lsc = cast(ItemLocalShellToolCall, item)
        commands = lsc.action.command if hasattr(lsc.action, "command") and lsc.action.command else []
        return Message(
            role="assistant",
            contents=[
                Content.from_shell_tool_call(
                    call_id=lsc.call_id,
                    commands=commands,
                    status=str(lsc.status),
                )
            ],
        )

    if item.type == "local_shell_call_output":
        lsco = cast(ItemLocalShellToolCallOutput, item)
        return Message(
            role="tool",
            contents=[
                Content.from_shell_tool_result(
                    call_id=lsco.id,
                    outputs=[Content.from_shell_command_output(stdout=lsco.output)],
                )
            ],
        )

    if item.type == "file_search_call":
        fs = cast(ItemFileSearchToolCall, item)
        return Message(
            role="assistant",
            contents=[
                Content.from_function_call(
                    fs.id,
                    "file_search",
                    arguments=json.dumps({"queries": fs.queries}),
                )
            ],
        )

    if item.type == "web_search_call":
        ws = cast(ItemWebSearchToolCall, item)
        return Message(
            role="assistant",
            contents=[Content.from_function_call(ws.id, "web_search")],
        )

    if item.type == "computer_call":
        cc = cast(ItemComputerToolCall, item)
        return Message(
            role="assistant",
            contents=[
                Content.from_function_call(
                    cc.call_id,
                    "computer_use",
                    arguments=str(cc.action),
                )
            ],
        )

    if item.type == "computer_call_output":
        cco = cast(ComputerCallOutputItemParam, item)
        return Message(
            role="tool",
            contents=[Content.from_function_result(cco.call_id, result=str(cco.output))],
        )

    if item.type == "custom_tool_call":
        ct = cast(ItemCustomToolCall, item)
        return Message(
            role="assistant",
            contents=[Content.from_function_call(ct.call_id, ct.name, arguments=ct.input)],
        )

    if item.type == "custom_tool_call_output":
        cto = cast(ItemCustomToolCallOutput, item)
        output = cto.output if isinstance(cto.output, str) else str(cto.output)
        # Hosted-MCP results land here because the host writes them via
        # `aoutput_item_custom_tool_call_output` (see `_to_outputs` for
        # `mcp_server_tool_result`). The persisted `call_id` keeps its
        # `mcp_*` prefix; on read, route those back to a hosted-MCP result
        # Content so the chat-client serialize layer can coalesce them
        # onto a single `mcp_call` input item with `output` populated.
        # Issue #5546.
        if cto.call_id and cto.call_id.startswith("mcp_"):
            return Message(
                role="tool",
                contents=[Content.from_mcp_server_tool_result(call_id=cto.call_id, output=output)],
            )
        return Message(
            role="tool",
            contents=[Content.from_function_result(cto.call_id, result=output)],
        )

    if item.type == "apply_patch_call":
        ap = cast(ApplyPatchToolCallItemParam, item)
        return Message(
            role="assistant",
            contents=[
                Content.from_function_call(
                    ap.call_id,
                    "apply_patch",
                    arguments=str(ap.operation),
                )
            ],
        )

    if item.type == "apply_patch_call_output":
        apo = cast(ApplyPatchToolCallOutputItemParam, item)
        return Message(
            role="tool",
            contents=[Content.from_function_result(apo.call_id, result=apo.output or "")],
        )

    raise ValueError(f"Unsupported Item type: {item.type}")


async def _output_items_to_messages(
    history: Sequence[OutputItem],
    *,
    approval_storage: ApprovalStorage | None = None,
) -> list[Message]:
    """Converts a sequence of OutputItem objects to a list of Message objects.

    Args:
        history (Sequence[OutputItem]): The sequence of OutputItem objects to convert.
        approval_storage (ApprovalStorage | None, optional): The approval storage to use for
            resolving MCP approval requests. Defaults to None.

    Returns:
        list[Message]: The list of Message objects.
    """
    messages: list[Message] = []
    for item in history:
        messages.append(await _output_item_to_message(item, approval_storage=approval_storage))
    return messages


async def _output_item_to_message(item: OutputItem, *, approval_storage: ApprovalStorage | None = None) -> Message:
    """Converts an OutputItem to a Message.

    Args:
        item (OutputItem): The OutputItem to convert.
        approval_storage (ApprovalStorage | None, optional): The approval storage to use for
            resolving MCP approval requests. Defaults to None.

    Returns:
        Message: The converted Message.

    Raises:
        ValueError: If the OutputItem type is not supported.
    """
    if item.type == "output_message":
        output_msg = cast(OutputItemOutputMessage, item)
        return Message(
            role=output_msg.role, contents=[_convert_output_message_content(part) for part in output_msg.content]
        )

    if item.type == "message":
        msg = cast(OutputItemMessage, item)
        return Message(role=msg.role, contents=[_convert_message_content(part) for part in msg.content])

    if item.type == "function_call":
        fc = cast(OutputItemFunctionToolCall, item)
        return Message(
            role="assistant",
            contents=[Content.from_function_call(fc.call_id, fc.name, arguments=fc.arguments)],
        )

    if item.type == "function_call_output":
        fco = cast(FunctionCallOutputItemParam, item)
        output = fco.output if isinstance(fco.output, str) else str(fco.output)
        return Message(
            role="tool",
            contents=[Content.from_function_result(fco.call_id, result=output)],
        )

    if item.type == "reasoning":
        reasoning = cast(OutputItemReasoningItem, item)
        contents: list[Content] = []
        if reasoning.summary:
            for summary in reasoning.summary:
                contents.append(Content.from_text(summary.text))
        return Message(role="assistant", contents=contents)

    if item.type == "mcp_call":
        mcp = cast(OutputItemMcpToolCall, item)
        contents = [
            Content.from_mcp_server_tool_call(
                mcp.id,
                mcp.name,
                server_name=mcp.server_label,
                arguments=mcp.arguments,
            )
        ]
        if getattr(mcp, "output", None) is not None:
            contents.append(Content.from_mcp_server_tool_result(call_id=mcp.id, output=mcp.output))
        return Message(
            role="assistant",
            contents=contents,
        )

    if item.type == "mcp_approval_request":
        mcp_req = cast(OutputItemMcpApprovalRequest, item)
        if approval_storage is not None:
            function_approval_request_content = await approval_storage.load_approval_request(mcp_req.id)
        else:
            raise ValueError("ApprovalStorage is required to load approval request.")
        return Message(
            role="assistant",
            contents=[function_approval_request_content],
        )

    if item.type == "mcp_approval_response":
        mcp_resp = cast(OutputItemMcpApprovalResponseResource, item)
        if approval_storage is not None:
            function_approval_request_content = await approval_storage.load_approval_request(
                mcp_resp.approval_request_id
            )
        else:
            raise ValueError("ApprovalStorage is required to load approval request.")

        return Message(
            role="user",
            contents=[function_approval_request_content.to_function_approval_response(mcp_resp.approve)],
        )

    if item.type == "code_interpreter_call":
        ci = cast(OutputItemCodeInterpreterToolCall, item)
        return Message(
            role="assistant",
            contents=[Content.from_code_interpreter_tool_call(call_id=ci.id)],
        )

    if item.type == "image_generation_call":
        ig = cast(OutputItemImageGenToolCall, item)
        return Message(
            role="assistant",
            contents=[Content.from_image_generation_tool_call(image_id=ig.id)],
        )

    if item.type == "shell_call":
        sc = cast(OutputItemFunctionShellCall, item)
        return Message(
            role="assistant",
            contents=[
                Content.from_shell_tool_call(
                    call_id=sc.call_id,
                    commands=sc.action.commands,
                    status=str(sc.status),
                )
            ],
        )

    if item.type == "shell_call_output":
        sco = cast(OutputItemFunctionShellCallOutput, item)
        outputs = [
            Content.from_shell_command_output(
                stdout=out.stdout or "",
                stderr=out.stderr or "",
                exit_code=getattr(out.outcome, "exit_code", None) if hasattr(out, "outcome") else None,
            )
            for out in (sco.output or [])
        ]
        return Message(
            role="tool",
            contents=[
                Content.from_shell_tool_result(
                    call_id=sco.call_id,
                    outputs=outputs,
                    max_output_length=sco.max_output_length,
                )
            ],
        )

    if item.type == "local_shell_call":
        lsc = cast(OutputItemLocalShellToolCall, item)
        commands = lsc.action.command if hasattr(lsc.action, "command") and lsc.action.command else []
        return Message(
            role="assistant",
            contents=[
                Content.from_shell_tool_call(
                    call_id=lsc.call_id,
                    commands=commands,
                    status=str(lsc.status),
                )
            ],
        )

    if item.type == "local_shell_call_output":
        lsco = cast(OutputItemLocalShellToolCallOutput, item)
        return Message(
            role="tool",
            contents=[
                Content.from_shell_tool_result(
                    call_id=lsco.id,
                    outputs=[Content.from_shell_command_output(stdout=lsco.output)],
                )
            ],
        )

    if item.type == "file_search_call":
        fs = cast(OutputItemFileSearchToolCall, item)
        return Message(
            role="assistant",
            contents=[
                Content.from_function_call(
                    fs.id,
                    "file_search",
                    arguments=json.dumps({"queries": fs.queries}),
                )
            ],
        )

    if item.type == "web_search_call":
        ws = cast(OutputItemWebSearchToolCall, item)
        return Message(
            role="assistant",
            contents=[Content.from_function_call(ws.id, "web_search")],
        )

    if item.type == "computer_call":
        cc = cast(OutputItemComputerToolCall, item)
        return Message(
            role="assistant",
            contents=[
                Content.from_function_call(
                    cc.call_id,
                    "computer_use",
                    arguments=str(cc.action),
                )
            ],
        )

    if item.type == "computer_call_output":
        cco = cast(OutputItemComputerToolCallOutputResource, item)
        return Message(
            role="tool",
            contents=[Content.from_function_result(cco.call_id, result=str(cco.output))],
        )

    if item.type == "custom_tool_call":
        ct = cast(OutputItemCustomToolCall, item)
        return Message(
            role="assistant",
            contents=[Content.from_function_call(ct.call_id, ct.name, arguments=ct.input)],
        )

    if item.type == "custom_tool_call_output":
        cto = cast(OutputItemCustomToolCallOutput, item)
        output = cto.output if isinstance(cto.output, str) else str(cto.output)
        # Hosted-MCP results land here because the host writes them via
        # `aoutput_item_custom_tool_call_output`. Route `mcp_*` call_ids
        # back to a hosted-MCP result Content so the chat-client serialize
        # layer can coalesce onto the matching `mcp_call` input item.
        # Issue #5546.
        if cto.call_id and cto.call_id.startswith("mcp_"):
            return Message(
                role="tool",
                contents=[Content.from_mcp_server_tool_result(call_id=cto.call_id, output=output)],
            )
        return Message(
            role="tool",
            contents=[Content.from_function_result(cto.call_id, result=output)],
        )

    if item.type == "apply_patch_call":
        ap = cast(OutputItemApplyPatchToolCall, item)
        return Message(
            role="assistant",
            contents=[
                Content.from_function_call(
                    ap.call_id,
                    "apply_patch",
                    arguments=str(ap.operation),
                )
            ],
        )

    if item.type == "apply_patch_call_output":
        apo = cast(OutputItemApplyPatchToolCallOutput, item)
        return Message(
            role="tool",
            contents=[Content.from_function_result(apo.call_id, result=apo.output or "")],
        )

    if item.type == "oauth_consent_request":
        oauth = cast(OAuthConsentRequestOutputItem, item)
        return Message(
            role="assistant",
            contents=[Content.from_oauth_consent_request(oauth.consent_link)],
        )

    if item.type == "structured_outputs":
        so = cast(StructuredOutputsOutputItem, item)
        text = json.dumps(so.output) if not isinstance(so.output, str) else so.output
        return Message(role="assistant", contents=[Content.from_text(text)])

    raise ValueError(f"Unsupported OutputItem type: {item.type}")


def _convert_output_message_content(content: OutputMessageContent) -> Content:
    """Converts an OutputMessageContent to a Content object.

    Args:
        content (OutputMessageContent): The OutputMessageContent to convert.

    Returns:
        Content: The converted Content object.

    Raises:
        ValueError: If the OutputMessageContent type is not supported.
    """
    if content.type == "output_text":
        text_content = cast(OutputMessageContentOutputTextContent, content)
        return Content.from_text(text_content.text)
    if content.type == "refusal":
        refusal_content = cast(OutputMessageContentRefusalContent, content)
        return Content.from_text(refusal_content.refusal)

    raise ValueError(f"Unsupported OutputMessageContent type: {content.type}")


def _convert_file_data(data_uri: str, filename: str | None = None) -> Content:
    """Convert a file_data data URI to a Content object.

    For text/* MIME types, decodes the base64 content and returns it as text.
    For other types, returns a URI-based Content with the filename preserved.
    """
    # Parse data URI: data:<media_type>;base64,<data>
    if data_uri.startswith("data:") and ";base64," in data_uri:
        header, encoded = data_uri.split(";base64,", 1)
        media_type = header[len("data:") :]
        if media_type.startswith("text/"):
            try:
                decoded_text = base64.b64decode(encoded).decode("utf-8")
            except (ValueError, UnicodeDecodeError):
                logger.warning(
                    "Failed to decode text/* file_data as UTF-8, falling through to URI passthrough.",
                    exc_info=True,
                )
            else:
                prefix = f"[File: {filename}]\n" if filename else ""
                return Content.from_text(f"{prefix}{decoded_text}")
    additional_properties = {"filename": filename} if filename else None
    return Content.from_uri(data_uri, additional_properties=additional_properties)


def _convert_message_content(content: MessageContent) -> Content:
    """Converts a MessageContent to a Content object.

    Args:
        content (MessageContent): The MessageContent to convert.

    Returns:
        Content: The converted Content object.

    Raises:
        ValueError: If the MessageContent type is not supported.
    """
    if content.type == "input_text":
        input_text = cast(MessageContentInputTextContent, content)
        return Content.from_text(input_text.text)
    if content.type == "output_text":
        output_text = cast(MessageContentOutputTextContent, content)
        return Content.from_text(output_text.text)
    if content.type == "text":
        text = cast(TextContent, content)
        return Content.from_text(text.text)
    if content.type == "summary_text":
        summary = cast(SummaryTextContent, content)
        return Content.from_text(summary.text)
    if content.type == "refusal":
        refusal = cast(MessageContentRefusalContent, content)
        return Content.from_text(refusal.refusal)
    if content.type == "reasoning_text":
        reasoning = cast(MessageContentReasoningTextContent, content)
        return Content.from_text_reasoning(text=reasoning.text)
    if content.type == "input_image":
        image = cast(MessageContentInputImageContent, content)
        if image.image_url:
            if image.image_url.startswith("data:"):
                return Content.from_uri(image.image_url)
            return Content.from_uri(image.image_url, media_type="image/*")
        if image.file_id:
            return Content.from_hosted_file(image.file_id)
    if content.type == "input_file":
        file = cast(MessageContentInputFileContent, content)
        if file.file_url:
            return Content.from_uri(file.file_url)
        if file.file_id:
            return Content.from_hosted_file(file.file_id, name=file.filename)
        if file.file_data:
            return _convert_file_data(file.file_data, file.filename)
    if content.type == "computer_screenshot":
        screenshot = cast(ComputerScreenshotContent, content)
        return Content.from_uri(screenshot.image_url)

    raise ValueError(f"Unsupported MessageContent type: {content.type}")


# endregion

# region Output Item Conversion


def _argument_json_default(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        return to_dict()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _arguments_to_str(arguments: Any | None) -> str:
    """Convert arguments to a JSON string.

    Args:
        arguments: The arguments to convert, can be a string, JSON-like object, or None.

    Returns:
        The arguments as a JSON string.
    """
    if arguments is None:
        return ""
    if isinstance(arguments, str):
        return arguments
    return json.dumps(arguments, default=_argument_json_default)


async def _to_outputs(
    stream: ResponseEventStream,
    content: Content,
    *,
    approval_storage: ApprovalStorage | None = None,
) -> AsyncIterator[ResponseStreamEvent]:
    """Converts a Content object to an async sequence of ResponseStreamEvent objects.

    Args:
        stream: The ResponseEventStream to use for building events.
        content: The Content to convert.
        approval_storage: An optional ApprovalStorage instance to use for saving and loading function approval requests.

    Yields:
        ResponseStreamEvent: The converted event objects.

    Raises:
        ValueError: If the Content type is not supported.
    """
    if content.type == "text" and content.text is not None:
        async for event in stream.aoutput_item_message(content.text):
            yield event
    elif content.type == "text_reasoning" and content.text is not None:
        async for event in stream.aoutput_item_reasoning_item(content.text):
            yield event
    elif content.type == "function_call":
        async for event in stream.aoutput_item_function_call(
            content.name,  # type: ignore[arg-type]
            content.call_id,  # type: ignore[arg-type]
            _arguments_to_str(content.arguments),
        ):
            yield event
    elif content.type == "function_result":
        async for event in stream.aoutput_item_function_call_output(
            content.call_id,  # type: ignore[arg-type]
            str(content.result or ""),
        ):
            yield event
    elif content.type == "image_generation_tool_result" and content.outputs is not None:
        async for event in stream.aoutput_item_image_gen_call(str(content.outputs)):
            yield event
    elif content.type == "mcp_server_tool_call":
        mcp_call = stream.add_output_item_mcp_call(
            server_label=content.server_name or "default",
            name=content.tool_name or "",
            item_id=content.call_id,
        )
        yield mcp_call.emit_added()
        async for event in mcp_call.aarguments(_arguments_to_str(content.arguments)):
            yield event
        yield mcp_call.emit_completed()
        yield mcp_call.emit_done()
    elif content.type == "mcp_server_tool_result":
        output = (
            content.output
            if isinstance(content.output, str)
            else str(content.output)
            if content.output is not None
            else ""
        )
        async for event in stream.aoutput_item_custom_tool_call_output(content.call_id or "", output):
            yield event
    elif content.type == "shell_tool_call":
        action = FunctionShellAction(commands=content.commands or [], timeout_ms=0, max_output_length=0)
        async for event in stream.aoutput_item_function_shell_call(
            content.call_id or "",
            action,
            LocalEnvironmentResource(),
            status=content.status or "completed",
        ):
            yield event
    elif content.type == "shell_tool_result":
        output_items: list[FunctionShellCallOutputContent] = []
        if content.outputs:
            for out in content.outputs:
                exit_code = getattr(out, "exit_code", None)
                output_items.append(
                    FunctionShellCallOutputContent(
                        stdout=getattr(out, "stdout", "") or "",
                        stderr=getattr(out, "stderr", "") or "",
                        outcome=FunctionShellCallOutputExitOutcome(exit_code=exit_code if exit_code is not None else 0),
                    )
                )
        async for event in stream.aoutput_item_function_shell_call_output(
            content.call_id or "",
            output_items,
            status=content.status or "completed",
            max_output_length=content.max_output_length,
        ):
            yield event
    elif content.type == "function_approval_request":
        function_call: Content = content.function_call  # type: ignore
        server_label = function_call.additional_properties.get("server_label", "agent_framework")
        request_saved = False
        async for event in stream.aoutput_item_mcp_approval_request(
            server_label,
            function_call.name,  # type: ignore
            _arguments_to_str(function_call.arguments),
        ):
            if approval_storage is not None and not request_saved:
                # Extract the approval request ID generated by the infrastructure
                # when the approval request item is added to the stream. Save the
                # approval request to the approval storage so it can be retrieved later
                # for round trips where the original approval request needs to be looked up.
                item = getattr(event, "item", None)
                if item is not None and getattr(item, "id", None) is not None:
                    approval_request_id = cast(str, item.id)
                    await approval_storage.save_approval_request(approval_request_id, content)
                    request_saved = True
            yield event
        if approval_storage is not None and not request_saved:
            logger.warning(
                "Approval request was not saved to approval storage because the approval request ID "
                "could not be extracted from the stream event."
            )
    else:
        # Log a warning for unsupported content types instead of raising an error to avoid breaking the response stream.
        logger.warning(f"Content type '{content.type}' is not supported yet. This is usually safe to ignore.")


def _stringify_mcp_output(output: Any) -> str:
    """Convert hosted MCP output payloads into the string shape expected by mcp_call.output."""
    if output is None:
        return ""
    if isinstance(output, str):
        return output
    if isinstance(output, Mapping):
        text = cast(Any, output).get("text")
        if isinstance(text, str):
            return text
        return json.dumps(output, default=str)
    if isinstance(output, Sequence) and not isinstance(output, (str, bytes, bytearray)):
        parts: list[str] = []
        entries = cast(Sequence[object], output)
        for entry in entries:
            if isinstance(entry, Content) and entry.type == "text":
                parts.append(entry.text or "")
                continue
            parts.append(_stringify_mcp_output(entry))
        return "".join(parts)
    return str(output)


def _emit_completed_mcp_call(
    stream: ResponseEventStream,
    call_content: Content,
    *,
    arguments: str,
    output: str,
) -> Generator[ResponseStreamEvent]:
    """Emit a single completed MCP call item carrying both arguments and output."""
    mcp_call = stream.add_output_item_mcp_call(
        server_label=call_content.server_name or "default",
        name=call_content.tool_name or "",
        item_id=call_content.call_id,
    )
    yield mcp_call.emit_added()
    yield mcp_call.emit_arguments_done(arguments)
    yield mcp_call.emit_completed()
    yield mcp_call.emit_done(output=output)


async def _to_outputs_for_messages(
    stream: ResponseEventStream,
    messages: Sequence[Message],
    *,
    approval_storage: ApprovalStorage | None = None,
) -> AsyncIterator[ResponseStreamEvent]:
    """Convert messages to output events with hosted-MCP call/result coalescing.

    Parse once in message/content order and emit either:
    - a single canonical completed ``mcp_call`` when adjacent hosted MCP
      call/result content are encountered, or
    - standard output items for all other content types.
    """
    pending_mcp_call: Content | None = None

    for message in messages:
        for content in message.contents:
            if pending_mcp_call is not None:
                if content.type == "mcp_server_tool_result" and content.call_id == pending_mcp_call.call_id:
                    for event in _emit_completed_mcp_call(
                        stream,
                        pending_mcp_call,
                        arguments=_arguments_to_str(pending_mcp_call.arguments),
                        output=_stringify_mcp_output(content.output),
                    ):
                        yield event
                    pending_mcp_call = None
                    continue

                async for event in _to_outputs(stream, pending_mcp_call, approval_storage=approval_storage):
                    yield event
                pending_mcp_call = None

            if content.type == "mcp_server_tool_call" and content.call_id:
                pending_mcp_call = content
                continue

            async for event in _to_outputs(stream, content, approval_storage=approval_storage):
                yield event

    if pending_mcp_call is not None:
        async for event in _to_outputs(stream, pending_mcp_call, approval_storage=approval_storage):
            yield event


# endregion
