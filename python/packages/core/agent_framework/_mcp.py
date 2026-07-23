# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
import base64
import contextlib
import contextvars
import json
import logging
import re
import sys
import warnings
from abc import abstractmethod
from collections.abc import Callable, Collection, Coroutine, Mapping, Sequence
from contextlib import AsyncExitStack, _AsyncGeneratorContextManager  # type: ignore
from dataclasses import dataclass
from datetime import timedelta
from functools import partial
from inspect import isawaitable
from typing import TYPE_CHECKING, Any, Literal, TypeAlias, TypedDict, cast

from opentelemetry import propagate
from opentelemetry import trace as otel_trace

from ._feature_stage import (
    ExperimentalFeature,
    ExperimentalWarning,
    _warn_on_feature_use,  # pyright: ignore[reportPrivateUsage]
    experimental,
)
from ._telemetry import FeatureIndex, mark_feature_used
from ._tools import FunctionTool
from ._types import (
    ChatOptions,
    Content,
    Message,
)
from .exceptions import ToolException, ToolExecutionException
from .observability import (
    OtelAttr,
    create_mcp_client_span,
    set_mcp_span_error,
)

if sys.version_info >= (3, 11):
    from typing import Self  # pragma: no cover
else:
    from typing_extensions import Self  # pragma: no cover

if TYPE_CHECKING:
    from httpx import AsyncClient
    from mcp import types
    from mcp.client.session import ClientSession
    from mcp.shared.context import RequestContext
    from mcp.shared.session import RequestResponder

    from ._clients import SupportsChatGetResponse
    from ._middleware import FunctionInvocationContext


logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    _MCPSamplingContentBlock: TypeAlias = (
        types.TextContent
        | types.ImageContent
        | types.AudioContent
        | types.EmbeddedResource
        | types.ResourceLink
        | types.ToolUseContent
    )
else:
    _MCPSamplingContentBlock = Any


class MCPSpecificApproval(TypedDict, total=False):
    """Represents the specific approval mode for an MCP tool.

    When using this mode, the user must specify which tools always or never require approval.

    Attributes:
        always_require_approval: A sequence of tool names that always require approval.
        never_require_approval: A sequence of tool names that never require approval.
    """

    always_require_approval: Collection[str] | None
    never_require_approval: Collection[str] | None


_MCP_REMOTE_NAME_KEY = "_mcp_remote_name"
_MCP_NORMALIZED_NAME_KEY = "_mcp_normalized_name"
_MCP_PROGRESSIVE_LIST_TOOL_NAME = "list_mcp_tools"
_MCP_PROGRESSIVE_LOAD_TOOL_NAME = "load_tool"
_MCP_PROGRESSIVE_UNLOAD_TOOL_NAME = "unload_tool"
# Reserved key in an ``additional_tool_argument_names`` mapping that applies its
# values to every tool on the server rather than a single named tool.
_MCP_GLOBAL_EXTRA_ARGS_KEY = "*"
_MCP_META_LABEL_PATTERN = r"[A-Za-z](?:[A-Za-z0-9-]*[A-Za-z0-9])?"
_MCP_META_KEY_PATTERN = re.compile(
    rf"^(?:(?:{_MCP_META_LABEL_PATTERN})(?:\.{_MCP_META_LABEL_PATTERN})*/)?"
    r"[A-Za-z0-9](?:[A-Za-z0-9_.-]*[A-Za-z0-9])?$"
)
# Framework kwargs that flow through the function-invocation pipeline (via
# ``FunctionInvocationContext.kwargs``) but must never be forwarded to an MCP
# server: they are internal objects that the MCP SDK cannot serialize. They are
# dropped as a safety net when a tool declares one of them in its schema, unless
# the user explicitly opts the name back in via ``additional_tool_argument_names``
# (explicit extras always win over the denylist).
# - chat_options/tools/tool_choice/session/thread: framework runtime objects.
# - conversation_id: internal tracking ID used by services like Azure AI.
# - options: metadata/store used by AG-UI for Azure AI client requirements.
# - response_format: a Pydantic model class for structured output (not serializable).
# - _meta: reserved key extracted separately as MCP request metadata.
_MCP_FRAMEWORK_DENYLIST: frozenset[str] = frozenset({
    "chat_options",
    "tools",
    "tool_choice",
    "session",
    "thread",
    "conversation_id",
    "options",
    "response_format",
    "_meta",
})
_mcp_call_headers: contextvars.ContextVar[dict[str, str]] = contextvars.ContextVar("_mcp_call_headers")
MCP_DEFAULT_TIMEOUT = 30
MCP_DEFAULT_SSE_READ_TIMEOUT = 60 * 5

# Default safety limits applied to server-initiated MCP sampling requests
# (``sampling/createMessage``). MCP servers are untrusted third parties, so the
# default ``sampling_callback`` denies requests unless an approval callback is
# supplied, and bounds the cost of any approved request.
# - ``_DEFAULT_SAMPLING_MAX_TOKENS`` clamps the server-requested ``maxTokens``.
# - ``_DEFAULT_SAMPLING_MAX_REQUESTS`` caps the number of sampling requests per
#   session connection (the counter resets on reconnect).
_DEFAULT_SAMPLING_MAX_TOKENS = 4096
_DEFAULT_SAMPLING_MAX_REQUESTS = 25

# A user-supplied gate invoked before each server-initiated sampling request is
# forwarded to the chat client. It receives the raw ``CreateMessageRequestParams``
# and returns (or awaits to) a truthy value to approve the request or a falsy
# value to deny it. Both synchronous and asynchronous callables are supported.
SamplingApprovalCallback = Callable[["types.CreateMessageRequestParams"], "bool | Coroutine[Any, Any, bool]"]

# region: Helpers

LOG_LEVEL_MAPPING: dict[str, int] = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "notice": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
    "critical": logging.CRITICAL,
    "alert": logging.CRITICAL,
    "emergency": logging.CRITICAL,
}


def _get_input_model_from_mcp_prompt(prompt: types.Prompt) -> dict[str, Any]:
    """Get the input model from an MCP prompt.

    Returns a JSON schema dictionary for prompt arguments.
    """
    # Check if 'arguments' is missing or empty
    if not prompt.arguments:
        return {"type": "object", "properties": {}}

    # Convert prompt arguments to JSON schema format
    properties: dict[str, Any] = {}
    required: list[str] = []

    for prompt_argument in prompt.arguments:
        # For prompts, all arguments are typically string type unless specified otherwise
        properties[prompt_argument.name] = {
            "type": "string",
            "description": prompt_argument.description if hasattr(prompt_argument, "description") else "",
        }
        if prompt_argument.required:
            required.append(prompt_argument.name)

    schema: dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    return schema


def _normalize_mcp_name(name: str) -> str:
    """Normalize MCP tool/prompt names to allowed identifier pattern (A-Za-z0-9_.-)."""
    return re.sub(r"[^A-Za-z0-9_.-]", "-", name)


def _build_prefixed_mcp_name(
    normalized_name: str,
    tool_name_prefix: str | None,
) -> str:
    """Build the exposed MCP function name from a normalized name and optional prefix."""
    if not tool_name_prefix:
        return normalized_name
    normalized_prefix = _normalize_mcp_name(tool_name_prefix).rstrip("_.-")
    if not normalized_prefix:
        return normalized_name
    trimmed_name = normalized_name.lstrip("_.-")
    return f"{normalized_prefix}_{trimmed_name}" if trimmed_name else normalized_prefix


def _normalize_additional_tool_argument_names(
    additional_tool_argument_names: Sequence[str] | Mapping[str, Sequence[str]] | None,
) -> tuple[set[str], dict[str, set[str]]]:
    """Split user-supplied extra argument names into global and per-tool sets.

    Accepts either a sequence (applied to every tool) or a mapping keyed by remote
    tool name, where the reserved key ``"*"`` is treated as global. Mapping values
    may be a sequence or a single string. Returns a
    ``(global_extras, per_tool_extras)`` tuple.
    """
    if additional_tool_argument_names is None:
        return set(), {}
    if isinstance(additional_tool_argument_names, str):
        return {additional_tool_argument_names}, {}
    if isinstance(additional_tool_argument_names, Mapping):
        global_extras: set[str] = set()
        per_tool_extras: dict[str, set[str]] = {}
        for tool_name, names in additional_tool_argument_names.items():
            # Treat a bare string value as a single name rather than iterating its characters.
            names_set = {names} if isinstance(names, str) else set(names)
            if tool_name == _MCP_GLOBAL_EXTRA_ARGS_KEY:
                global_extras.update(names_set)
            else:
                per_tool_extras[tool_name] = names_set
        return global_extras, per_tool_extras
    return set(additional_tool_argument_names), {}


def _mcp_config_candidate_names(*, local_name: str, normalized_name: str, remote_name: str) -> tuple[str, ...]:
    """Return safe configuration names for MCP allow/approval matching."""
    names = [remote_name]
    if normalized_name == remote_name and local_name != remote_name:
        names.append(local_name)
    return tuple(names)


def _validate_mcp_meta_key(key: str) -> None:
    """Validate an MCP ``_meta`` key against the 2025-06-18 key-name format."""
    if not _MCP_META_KEY_PATTERN.fullmatch(key):
        raise ToolExecutionException(f"Invalid MCP _meta key name: {key!r}.")


def _validate_mcp_meta(raw_meta: object | None) -> dict[str, Any] | None:
    """Validate and copy MCP request metadata."""
    if raw_meta is None:
        return None
    if not isinstance(raw_meta, dict):
        raise ToolExecutionException("MCP tool metadata provided via _meta must be a dict.")

    raw_meta_dict = cast(Mapping[object, Any], raw_meta)
    meta: dict[str, Any] = {}
    for key, value in raw_meta_dict.items():
        if not isinstance(key, str):
            raise ToolExecutionException("MCP tool metadata provided via _meta must use string keys.")
        _validate_mcp_meta_key(key)
        meta[key] = value
    return meta


def _inject_otel_into_mcp_meta(
    meta: dict[str, Any] | None = None,
    *,
    overwrite: bool = False,
) -> dict[str, Any] | None:
    """Inject OpenTelemetry trace context into MCP request _meta via the global propagator(s)."""
    carrier: dict[str, str] = {}
    propagate.inject(carrier)
    if not carrier:
        return meta

    if meta is None:
        meta = {}
    for key, value in carrier.items():
        _validate_mcp_meta_key(key)
        if overwrite or key not in meta:
            meta[key] = value

    return meta


def _url_origin(url: Any) -> tuple[str, str, int | None]:
    port = url.port
    if port is None:
        port = 443 if url.scheme == "https" else 80 if url.scheme == "http" else None
    return (url.scheme, url.host or "", port)


# Internal polling bounds for MCP long-running tasks. Not user-tunable today;
# promote to MCPTaskOptions if a concrete need arises.
_MCP_TASK_MIN_POLL_INTERVAL = timedelta(milliseconds=500)
_MCP_TASK_MAX_POLL_INTERVAL = timedelta(seconds=5)
_MCP_TASK_CANCEL_TIMEOUT = timedelta(seconds=5)
_MCP_TASK_TERMINAL_STATUSES: frozenset[str] = frozenset({"completed", "failed", "cancelled", "input_required"})

# Total send attempts for a Phase 2 request (initial try + one reconnect-and-retry).
# A single transient disconnect should not abort a long-running task; sustained outages
# surface as ``_MCPTaskAbandoned`` after the second failure.
_MCP_RECONNECT_ATTEMPTS = 2


class _MCPTaskAbandoned(ToolExecutionException):
    """Raised when the remote MCP task may still be running and must be cancelled.

    Subclass of ToolExecutionException so callers see a normal tool failure.
    """


class _MCPDeadlineExpired(Exception):
    """Internal marker for ``max_task_wait`` expiry; distinct from inner TimeoutError."""


@experimental(feature_id=ExperimentalFeature.MCP_LONG_RUNNING_TASKS)
@dataclass(frozen=True)
class MCPTaskOptions:
    """Options controlling how MCPTool drives the MCP long-running task lifecycle.

    When an MCP server advertises a tool with ``execution.taskSupport == "required"``,
    the framework transparently drives the SEP-2663 ``tools/call`` → ``tasks/get``
    (polled) → ``tasks/result`` lifecycle so the agent sees a normal tool result.

    Instances are immutable; replace the whole object via
    ``MCPTool.task_options = MCPTaskOptions(...)`` to change behavior.

    Attributes:
        default_ttl: Optional task-record retention time forwarded to the server as
            ``params.task.ttl`` (milliseconds, integer). The server keeps the task
            record around this long after the task reaches a terminal status so the
            client can still call ``tasks/get`` / ``tasks/result``; it does not
            cancel a running task. When ``None``, the server applies its own default.
            Must be positive if set (zero would expire the record before any client
            could read it).
        cancel_remote_task_on_local_cancellation: If True (default), a local
            cancellation of the awaiting coroutine triggers a best-effort
            ``tasks/cancel`` on the server before re-raising ``CancelledError``.
            Only gates ``CancelledError``; abandonment paths (max-wait,
            unrecoverable poll errors, lost connection after task_id is known)
            always cancel regardless of this flag.
        max_task_wait: Optional client-side deadline for the whole post-create
            lifecycle (poll + result fetch). When exceeded, raises
            ``ToolExecutionException`` and fires a best-effort ``tasks/cancel``.
            ``None`` (default) means no client-side bound. Must be positive if set.
    """

    default_ttl: timedelta | None = None
    cancel_remote_task_on_local_cancellation: bool = True
    max_task_wait: timedelta | None = None

    def __post_init__(self) -> None:
        if self.default_ttl is not None and self.default_ttl.total_seconds() <= 0:
            raise ValueError("MCPTaskOptions.default_ttl must be positive.")
        if self.max_task_wait is not None and self.max_task_wait.total_seconds() <= 0:
            raise ValueError("MCPTaskOptions.max_task_wait must be positive.")


def streamable_http_client(*args: Any, **kwargs: Any) -> _AsyncGeneratorContextManager[Any, None]:
    """Lazily import the MCP streamable HTTP transport."""
    try:
        from mcp.client.streamable_http import streamable_http_client as _streamable_http_client
    except ModuleNotFoundError as ex:
        missing_name = ex.name or str(ex)
        if missing_name == "mcp" or missing_name.startswith("mcp.") or "mcp" in missing_name:
            raise ModuleNotFoundError("`MCPStreamableHTTPTool` requires `mcp`. Please install `mcp`.") from ex
        raise ModuleNotFoundError(
            f"`MCPStreamableHTTPTool` requires streamable HTTP transport support. "
            f"The optional dependency `{missing_name}` is not installed. Please update your dependencies."
        ) from ex

    return _streamable_http_client(*args, **kwargs)


def _should_propagate_cancelled_error(ex: BaseException) -> bool:
    """Return True if *ex* is a genuine task-cancellation that should propagate unchanged.

    On Python >= 3.11, ``task.cancelling() > 0`` distinguishes a real caller-driven
    cancellation from a CancelledError raised internally by a library (e.g. via an
    anyio cancel scope).  On older Python versions the API is unavailable, so we
    always return False and let callers wrap the error in ToolException instead.
    """
    if not isinstance(ex, asyncio.CancelledError):
        return False
    if sys.version_info < (3, 11):
        return False
    task = asyncio.current_task()
    return task is not None and task.cancelling() > 0


# region: MCP Plugin


class MCPTool:
    """Main MCP class for connecting to Model Context Protocol servers.

    This is the base class for MCP tool implementations. It handles connection management,
    tool and prompt loading, and communication with MCP servers.

    Note:
        MCPTool cannot be instantiated directly. Use one of the subclasses:
        MCPStdioTool, MCPStreamableHTTPTool, or MCPWebsocketTool.

    Examples:
        See the subclass documentation for usage examples:

        - :class:`MCPStdioTool` for stdio-based MCP servers
        - :class:`MCPStreamableHTTPTool` for HTTP-based MCP servers
        - :class:`MCPWebsocketTool` for WebSocket-based MCP servers
    """

    def __init__(
        self,
        name: str,
        description: str | None = None,
        approval_mode: (Literal["always_require", "never_require"] | MCPSpecificApproval | None) = None,
        allowed_tools: Collection[str] | None = None,
        tool_name_prefix: str | None = None,
        load_tools: bool = True,
        parse_tool_results: Callable[[types.CallToolResult], str | list[Content]] | None = None,
        load_prompts: bool = True,
        parse_prompt_results: Callable[[types.GetPromptResult], str] | None = None,
        session: ClientSession | None = None,
        request_timeout: int | None = None,
        client: SupportsChatGetResponse | None = None,
        sampling_approval_callback: SamplingApprovalCallback | None = None,
        sampling_max_tokens: int | None = _DEFAULT_SAMPLING_MAX_TOKENS,
        sampling_max_requests: int | None = _DEFAULT_SAMPLING_MAX_REQUESTS,
        additional_properties: dict[str, Any] | None = None,
        task_options: MCPTaskOptions | None = None,
        additional_tool_argument_names: Sequence[str] | Mapping[str, Sequence[str]] | None = None,
        use_progressive_disclosure: bool = False,
        always_load: Collection[str] | None = None,
    ) -> None:
        """Initialize the MCP Tool base.

        Note:
            Do not use this method, use one of the subclasses: MCPStreamableHTTPTool, MCPWebsocketTool
            or MCPStdioTool.

        Args:
            name: The name of the MCP tool.
            description: A description of the MCP tool.
            approval_mode: Whether approval is required to run tools.
            allowed_tools: Optional allow-list of MCP tool names to expose as functions.
                ``None`` (the default) exposes every tool advertised by the MCP server.
                A non-empty collection exposes only the raw remote tools whose names appear in it. For
                compatibility, the prefixed local function name is also accepted when the raw remote name already
                matches its normalized form; normalized aliases do not authorize a different raw remote tool.
                An empty collection (``[]``) exposes no tools — if you simply want to
                disable tool execution, prefer ``load_tools=False`` instead. ``[]`` is
                useful as a runtime guard or when you want to load tool metadata for
                inspection without exposing the tools for invocation.
            tool_name_prefix: Optional prefix to prepend to exposed MCP function names.
            load_tools: Whether to load tools from the MCP server.
            parse_tool_results: An optional callable with signature
                ``Callable[[types.CallToolResult], str]`` that overrides the default result
                parsing. When ``None`` (the default), the built-in parser converts MCP types
                directly to a string. If you need per-function result parsing, access the
                ``.functions`` list after connecting and set ``result_parser`` on individual
                ``FunctionTool`` instances.
            load_prompts: Whether to load prompts from the MCP server.
            parse_prompt_results: An optional callable with signature
                ``Callable[[types.GetPromptResult], str]`` that overrides the default prompt
                result parsing. When ``None`` (the default), the built-in parser converts
                MCP prompt results to a string. If you need per-function result parsing,
            access the ``.functions`` list after connecting and set ``result_parser`` on
            individual ``FunctionTool`` instances.
            session: An existing MCP client session to use.
            request_timeout: Timeout in seconds for MCP requests.
            client: A chat client for sampling callbacks.
            sampling_approval_callback: Optional gate invoked before each server-initiated
                ``sampling/createMessage`` request is forwarded to ``client``. It receives the
                raw ``CreateMessageRequestParams`` and may be synchronous or asynchronous;
                returning a truthy value approves the request and a falsy value denies it. When
                ``None`` (the default), every sampling request is **denied** because MCP servers
                are untrusted third parties (confused-deputy risk). To restore the legacy
                auto-approve behavior, pass ``lambda params: True`` as an explicit, conscious
                opt-in.
            sampling_max_tokens: Upper bound applied to the server-requested ``maxTokens`` for an
                approved sampling request. The effective value is ``min(requested, cap)``. Set to
                ``None`` to disable the cap. Defaults to ``_DEFAULT_SAMPLING_MAX_TOKENS``.
            sampling_max_requests: Maximum number of sampling requests allowed per session
                connection; further requests are rejected. The counter resets on reconnect. Set
                to ``None`` to disable the limit. Defaults to ``_DEFAULT_SAMPLING_MAX_REQUESTS``.
            additional_properties: Additional properties for the tool.
            task_options: Options controlling how long-running MCP tasks are driven for
                tools that advertise ``execution.taskSupport == "required"``. When ``None``,
                the defaults from :class:`MCPTaskOptions` are used.
            additional_tool_argument_names: Extra argument names to forward to the MCP server
                in addition to each tool's declared parameters. A ``Sequence[str]`` applies to
                every tool; a ``Mapping[str, Sequence[str]]`` is keyed by remote tool name with
                ``"*"`` as a global key. See the transport subclasses for full details.
            use_progressive_disclosure: When ``True``, expose discovery and loader tools plus
                ``always_load`` tools initially, and let the model load and unload other allowed MCP tools on demand.
            always_load: MCP tool names to keep visible from the start when progressive disclosure
                is enabled. Names use the same safe matching rules as ``allowed_tools``; unmatched
                entries are ignored.
        """
        if use_progressive_disclosure and not load_tools:
            raise ValueError("use_progressive_disclosure=True requires load_tools=True.")
        if use_progressive_disclosure:
            _warn_on_feature_use(
                stage="experimental",
                feature_id=ExperimentalFeature.PROGRESSIVE_TOOLS,
                object_name="MCP progressive disclosure",
                category=ExperimentalWarning,
            )
        self.name = name
        self.description = description or ""
        self.approval_mode = approval_mode
        self.allowed_tools = allowed_tools
        self.tool_name_prefix = _normalize_mcp_name(tool_name_prefix).rstrip("_.-") if tool_name_prefix else None
        self.additional_properties = additional_properties
        self.load_tools_flag = load_tools
        self.parse_tool_results = parse_tool_results
        self.load_prompts_flag = load_prompts
        self.parse_prompt_results = parse_prompt_results
        # Defer constructing the default MCPTaskOptions so the experimental warning
        # only fires when LRO is actually engaged (lazy-resolved by _effective_task_options).
        self._task_options_explicit: MCPTaskOptions | None = task_options
        self._task_options_default: MCPTaskOptions | None = None
        self._exit_stack = AsyncExitStack()
        self._lifecycle_lock = asyncio.Lock()
        self._lifecycle_request_lock = asyncio.Lock()
        self._function_load_lock = asyncio.Lock()
        self._lifecycle_queue: asyncio.Queue[tuple[str, bool, bool, asyncio.Future[None]]] | None = None
        self._lifecycle_owner_task: asyncio.Task[None] | None = None
        self.session = session
        self.request_timeout = request_timeout
        self.client = client
        self.sampling_approval_callback = sampling_approval_callback
        self.sampling_max_tokens = sampling_max_tokens
        self.sampling_max_requests = sampling_max_requests
        self._sampling_request_count = 0
        self._functions: list[FunctionTool] = []
        self.use_progressive_disclosure = use_progressive_disclosure
        self.always_load = always_load
        self._always_load_names = set(always_load or ())
        self._progressive_loader_functions: list[FunctionTool] | None = None
        self._progressive_loaded_tool_names: set[str] = set()
        self._tool_call_meta_by_name: dict[str, dict[str, Any]] = {}
        self._tool_task_support_by_name: dict[str, str] = {}
        self._tool_param_names_by_name: dict[str, set[str]] = {}
        self._global_extra_arg_names, self._tool_extra_arg_names = _normalize_additional_tool_argument_names(
            additional_tool_argument_names
        )
        self.is_connected: bool = False
        self._tools_loaded: bool = False
        self._prompts_loaded: bool = False
        self._server_capabilities: types.ServerCapabilities | None = None
        self._supports_tools: bool = True
        self._supports_prompts: bool = True
        self._supports_logging: bool | None = None
        self._ping_available: bool = True
        self._pending_reload_tasks: set[asyncio.Task[None]] = set()

    def __str__(self) -> str:
        return f"MCPTool(name={self.name}, description={self.description})"

    def _mcp_base_span_attributes(self) -> dict[str, Any]:
        """Return base MCP span attributes shared across all operations.

        Subclasses override to add transport-specific attributes (server address, port, etc.).
        """
        return {}

    def _parse_prompt_result_from_mcp(
        self,
        mcp_type: types.GetPromptResult,
    ) -> str:
        """Parse an MCP GetPromptResult directly into a string representation."""
        from mcp import types

        parts: list[str] = []
        for message in mcp_type.messages:
            content = message.content
            if isinstance(content, types.TextContent):
                parts.append(content.text)
            elif isinstance(content, (types.ImageContent, types.AudioContent)):
                parts.append(
                    json.dumps(
                        {
                            "type": "image" if isinstance(content, types.ImageContent) else "audio",
                            "data": content.data,
                            "mimeType": content.mimeType,
                        },
                        default=str,
                    )
                )
            elif isinstance(content, types.EmbeddedResource):
                match content.resource:
                    case types.TextResourceContents():
                        parts.append(content.resource.text)
                    case types.BlobResourceContents():
                        parts.append(
                            json.dumps(
                                {
                                    "type": "blob",
                                    "data": content.resource.blob,
                                    "mimeType": content.resource.mimeType,
                                },
                                default=str,
                            )
                        )
            else:
                parts.append(str(content))
        if not parts:
            return ""
        if len(parts) == 1:
            return parts[0]
        return json.dumps(parts, default=str)

    def _parse_message_from_mcp(
        self,
        mcp_type: types.PromptMessage | types.SamplingMessage,
    ) -> Message:
        """Parse an MCP container type into an Agent Framework type."""
        return Message(
            role=mcp_type.role,
            contents=self._parse_content_from_mcp(mcp_type.content),
            raw_representation=mcp_type,
        )

    def _parse_tool_result_from_mcp(
        self,
        mcp_type: types.CallToolResult,
    ) -> list[Content]:
        """Parse an MCP CallToolResult into a list of Content items.

        If the server attached a ``_meta`` payload to the tool result (e.g. for
        Information Flow Control labels under the ``ifc`` key), a copy of that
        payload is stamped onto each produced :class:`Content` instance under
        ``additional_properties["_meta"]``.  Downstream layers (such as
        :class:`agent_framework.security.SecureMCPToolProxy`) consume this key
        to derive per-item security labels.
        The sentinel is intentionally generic so any MCP server's ``_meta``
        keys (current or future) can be interpreted by higher-level code.
        """
        from mcp import types

        raw_meta = mcp_type.meta
        meta: dict[str, Any] | None = dict(raw_meta) if isinstance(raw_meta, Mapping) else None
        # Stamp the server ``_meta`` payload directly via additional_properties on
        # each newly constructed Content; empty when the server provided no meta.
        additional_kwargs: dict[str, Any] = {"additional_properties": {"_meta": meta}} if meta else {}

        result: list[Content] = []
        for item in mcp_type.content:
            match item:
                case types.TextContent():
                    result.append(Content.from_text(item.text, **additional_kwargs))
                case types.ImageContent() | types.AudioContent():
                    decoded = base64.b64decode(item.data)
                    result.append(
                        Content.from_data(
                            data=decoded,
                            media_type=item.mimeType,
                            **additional_kwargs,
                        )
                    )
                case types.ResourceLink():
                    result.append(
                        Content.from_uri(
                            uri=str(item.uri),
                            media_type=item.mimeType,
                            **additional_kwargs,
                        )
                    )
                case types.EmbeddedResource():
                    match item.resource:
                        case types.TextResourceContents():
                            result.append(Content.from_text(item.resource.text, **additional_kwargs))
                        case types.BlobResourceContents():
                            blob = item.resource.blob
                            mime = item.resource.mimeType or "application/octet-stream"
                            if not blob.startswith("data:"):
                                blob = f"data:{mime};base64,{blob}"
                            result.append(
                                Content.from_uri(
                                    uri=blob,
                                    media_type=mime,
                                    **additional_kwargs,
                                )
                            )
                case _:
                    result.append(Content.from_text(str(item), **additional_kwargs))

        if mcp_type.structuredContent is not None:
            result.append(Content.from_text(json.dumps(mcp_type.structuredContent, default=str)))

        if not result:
            result.append(Content.from_text("null", **additional_kwargs))
        return result

    def _parse_content_from_mcp(
        self,
        mcp_type: types.ImageContent
        | types.TextContent
        | types.AudioContent
        | types.EmbeddedResource
        | types.ResourceLink
        | types.ToolUseContent
        | types.ToolResultContent
        | Sequence[
            types.ImageContent
            | types.TextContent
            | types.AudioContent
            | types.EmbeddedResource
            | types.ResourceLink
            | types.ToolUseContent
            | types.ToolResultContent
        ],
    ) -> list[Content]:
        """Parse an MCP type into an Agent Framework type."""
        from mcp import types

        mcp_content_types: Sequence[Any] = (
            cast(Sequence[Any], mcp_type) if isinstance(mcp_type, Sequence) else [mcp_type]
        )
        return_types: list[Content] = []
        for mcp_type in mcp_content_types:
            match mcp_type:
                case types.TextContent():
                    return_types.append(Content.from_text(text=mcp_type.text, raw_representation=mcp_type))
                case types.ImageContent() | types.AudioContent():
                    data_bytes = base64.b64decode(mcp_type.data) if isinstance(mcp_type.data, str) else mcp_type.data
                    return_types.append(
                        Content.from_data(
                            data=data_bytes,
                            media_type=mcp_type.mimeType,
                            raw_representation=mcp_type,
                        )
                    )
                case types.ResourceLink():
                    return_types.append(
                        Content.from_uri(
                            uri=str(mcp_type.uri),
                            media_type=mcp_type.mimeType or "application/json",
                            raw_representation=mcp_type,
                        )
                    )
                case types.ToolUseContent():
                    return_types.append(
                        Content.from_function_call(
                            call_id=mcp_type.id,
                            name=mcp_type.name,
                            arguments=mcp_type.input,
                            raw_representation=mcp_type,
                        )
                    )
                case types.ToolResultContent():
                    return_types.append(
                        Content.from_function_result(
                            call_id=mcp_type.toolUseId,
                            result=self._parse_content_from_mcp(mcp_type.content)
                            if mcp_type.content
                            else mcp_type.structuredContent,
                            exception=str(Exception()) if mcp_type.isError else None,
                            raw_representation=mcp_type,
                        )
                    )
                case types.EmbeddedResource():
                    match mcp_type.resource:
                        case types.TextResourceContents():
                            return_types.append(
                                Content.from_text(
                                    text=mcp_type.resource.text,
                                    raw_representation=mcp_type,
                                    additional_properties=(
                                        mcp_type.annotations.model_dump() if mcp_type.annotations else None
                                    ),
                                )
                            )
                        case types.BlobResourceContents():
                            return_types.append(
                                Content.from_uri(
                                    uri=mcp_type.resource.blob,
                                    media_type=mcp_type.resource.mimeType,
                                    raw_representation=mcp_type,
                                    additional_properties=(
                                        mcp_type.annotations.model_dump() if mcp_type.annotations else None
                                    ),
                                )
                            )
                case _:
                    pass
        return return_types

    def _prepare_content_for_mcp(
        self,
        content: Content,
    ) -> _MCPSamplingContentBlock | None:
        """Prepare an Agent Framework content type for MCP."""
        from mcp import types

        if content.type == "text":
            return types.TextContent(type="text", text=content.text)  # type: ignore[attr-defined]
        if content.type == "function_call":
            if not content.call_id or not content.name:
                return None
            return types.ToolUseContent(
                type="tool_use",
                id=content.call_id,
                name=content.name,
                input=content.parse_arguments() or {},
            )
        if content.type == "data":
            if content.media_type and content.media_type.startswith("image/"):
                return types.ImageContent(type="image", data=content.uri, mimeType=content.media_type)  # type: ignore[attr-defined]
            if content.media_type and content.media_type.startswith("audio/"):
                return types.AudioContent(type="audio", data=content.uri, mimeType=content.media_type)  # type: ignore[attr-defined]
            if content.media_type and content.media_type.startswith("application/"):
                return types.EmbeddedResource(
                    type="resource",
                    resource=types.BlobResourceContents(
                        blob=content.uri,  # type: ignore[attr-defined]
                        mimeType=content.media_type,
                        uri=(
                            content.additional_properties.get("uri", "af://binary")
                            if content.additional_properties
                            else "af://binary"
                        ),  # type: ignore[arg-type]
                    ),
                )
            return None
        if content.type == "uri":
            resource_name = (
                content.additional_properties.get("name", "Unknown") if content.additional_properties else "Unknown"
            )
            return types.ResourceLink(
                type="resource_link",
                uri=content.uri,  # type: ignore[arg-type,attr-defined]
                mimeType=content.media_type,
                name=resource_name,
            )
        return None

    def _prepare_message_for_mcp(
        self,
        content: Message,
    ) -> list[_MCPSamplingContentBlock]:
        """Prepare a Message for MCP format."""
        messages: list[_MCPSamplingContentBlock] = []
        for item in content.contents:
            mcp_content = self._prepare_content_for_mcp(item)
            if mcp_content:
                messages.append(mcp_content)
        return messages

    @property
    def functions(self) -> list[FunctionTool]:
        """Get the list of functions that are allowed."""
        if self.use_progressive_disclosure:
            return self._progressive_functions()
        return self._filtered_functions()

    def _filtered_functions(self) -> list[FunctionTool]:
        """Return loaded MCP functions after applying ``allowed_tools``."""
        if self.allowed_tools is None:
            return self._functions
        allowed_names = set(self.allowed_tools)
        filtered_functions: list[FunctionTool] = []
        for func in self._functions:
            if self._function_matches_names(func, allowed_names):
                filtered_functions.append(func)
        return filtered_functions

    def _function_matches_names(self, func: FunctionTool, names: set[str]) -> bool:
        """Return whether a generated MCP function matches a configured name set."""
        if not names:
            return False
        additional_properties = func.additional_properties or {}
        normalized_name = additional_properties.get(_MCP_NORMALIZED_NAME_KEY)
        remote_name = additional_properties.get(_MCP_REMOTE_NAME_KEY)
        if not isinstance(normalized_name, str) or not isinstance(remote_name, str):
            return False
        candidate_names = _mcp_config_candidate_names(
            local_name=func.name,
            normalized_name=normalized_name,
            remote_name=remote_name,
        )
        return any(name in names for name in candidate_names)

    def _progressive_functions(self) -> list[FunctionTool]:
        """Return the initial model-facing function list for progressive disclosure."""
        initial_functions = list(self._progressive_loader_tools())
        initial_functions.extend(
            func
            for func in self._filtered_functions()
            if (
                self._function_matches_names(func, self._always_load_names)
                or func.name in self._progressive_loaded_tool_names
            )
            and not self._function_collides_with_progressive_loader(func)
        )
        return initial_functions

    def _progressive_loader_names(self) -> set[str]:
        """Return the local names reserved for progressive disclosure loader tools."""
        return {
            _build_prefixed_mcp_name(_MCP_PROGRESSIVE_LIST_TOOL_NAME, self.tool_name_prefix),
            _build_prefixed_mcp_name(_MCP_PROGRESSIVE_LOAD_TOOL_NAME, self.tool_name_prefix),
            _build_prefixed_mcp_name(_MCP_PROGRESSIVE_UNLOAD_TOOL_NAME, self.tool_name_prefix),
        }

    def _function_collides_with_progressive_loader(self, func: FunctionTool) -> bool:
        """Return whether an MCP function's local name collides with a loader tool name."""
        return func.name in self._progressive_loader_names()

    def _progressive_loader_tools(self) -> list[FunctionTool]:
        """Create or return the generated progressive disclosure loader tools."""
        if self._progressive_loader_functions is not None:
            return self._progressive_loader_functions

        list_tool_name = _build_prefixed_mcp_name(_MCP_PROGRESSIVE_LIST_TOOL_NAME, self.tool_name_prefix)
        load_tool_name = _build_prefixed_mcp_name(_MCP_PROGRESSIVE_LOAD_TOOL_NAME, self.tool_name_prefix)
        unload_tool_name = _build_prefixed_mcp_name(_MCP_PROGRESSIVE_UNLOAD_TOOL_NAME, self.tool_name_prefix)
        self._progressive_loader_functions = [
            FunctionTool(
                func=self._list_progressive_mcp_tools,
                name=list_tool_name,
                description="List the MCP tools that can be loaded from this server.",
                approval_mode="never_require",
                input_model={"type": "object", "properties": {}},
            ),
            FunctionTool(
                func=self._load_progressive_mcp_tool,
                name=load_tool_name,
                description="Load an MCP tool from this server so it can be called on the next iteration.",
                approval_mode="never_require",
                input_model={
                    "type": "object",
                    "properties": {
                        "tool": {
                            "oneOf": [
                                {"type": "string"},
                                {"type": "array", "items": {"type": "string"}},
                            ],
                            "description": "The MCP tool name, or MCP tool names, to load.",
                        },
                    },
                    "required": ["tool"],
                },
            ),
            FunctionTool(
                func=self._unload_progressive_mcp_tool,
                name=unload_tool_name,
                description="Unload an MCP tool from this server when it is no longer relevant.",
                approval_mode="never_require",
                input_model={
                    "type": "object",
                    "properties": {
                        "tool": {
                            "oneOf": [
                                {"type": "string"},
                                {"type": "array", "items": {"type": "string"}},
                            ],
                            "description": "The MCP tool name, or MCP tool names, to unload.",
                        },
                    },
                    "required": ["tool"],
                },
            ),
        ]
        return self._progressive_loader_functions

    def _resolve_progressive_function(self, tool_name: str) -> FunctionTool:
        """Resolve a progressive disclosure tool name against allowed MCP functions."""
        matches = [func for func in self._filtered_functions() if self._function_matches_names(func, {tool_name})]
        matches.extend(func for func in self._filtered_functions() if func.name == tool_name and func not in matches)
        if not matches:
            available = (
                ", ".join(
                    func.name
                    for func in self._filtered_functions()
                    if not self._function_collides_with_progressive_loader(func)
                )
                or "none"
            )
            raise ToolExecutionException(f"MCP tool '{tool_name}' is not available. Available tools: {available}.")
        if len(matches) > 1:
            raise ToolExecutionException(f"MCP tool name '{tool_name}' is ambiguous.")
        return matches[0]

    @staticmethod
    def _progressive_tool_names(tool: str | Sequence[str]) -> list[str]:
        """Normalize a progressive loader request to a tool-name list."""
        if isinstance(tool, str):
            return [tool]
        if not isinstance(tool, Sequence):
            raise ToolExecutionException("Progressive MCP tool request must be a string or a list of strings.")
        tool_names = list(tool)
        if not all(isinstance(tool_name, str) for tool_name in tool_names):
            raise ToolExecutionException("Progressive MCP tool request must contain only strings.")
        return tool_names

    def _is_progressive_function_loaded(
        self,
        func: FunctionTool,
        ctx: FunctionInvocationContext | None,
    ) -> bool:
        """Return whether a progressive MCP function is already present in the live tool list."""
        if self._function_matches_names(func, self._always_load_names):
            return True
        if func.name in self._progressive_loaded_tool_names:
            return True
        if ctx is None or ctx.tools is None:
            return False
        return any(tool_item is func for tool_item in ctx.tools)

    def _list_progressive_mcp_tools(self, ctx: FunctionInvocationContext) -> list[dict[str, Any]]:
        """List allowed MCP tools that can be loaded progressively."""
        tools: list[dict[str, Any]] = []
        for func in self._filtered_functions():
            if self._function_collides_with_progressive_loader(func):
                continue
            additional_properties = func.additional_properties or {}
            remote_name = additional_properties.get(_MCP_REMOTE_NAME_KEY)
            tools.append({
                "name": func.name,
                "remote_name": remote_name if isinstance(remote_name, str) else func.name,
                "description": func.description,
                "parameters": func.parameters(),
                "approval_mode": func.approval_mode,
                "loaded": self._is_progressive_function_loaded(func, ctx),
                "always_loaded": self._function_matches_names(func, self._always_load_names),
            })
        return tools

    async def _load_progressive_mcp_tool(self, ctx: FunctionInvocationContext, tool: str | Sequence[str]) -> str:
        """Load an allowed MCP tool into the live function-calling tool list."""
        if ctx.tools is None:
            raise ToolExecutionException("load_tool can only be used inside an agent function-calling run.")
        messages: list[str] = []
        functions_to_load: list[FunctionTool] = []
        function_names_to_load: set[str] = set()
        for tool_name in self._progressive_tool_names(tool):
            try:
                func = self._resolve_progressive_function(tool_name)
            except ToolExecutionException as ex:
                messages.append(str(ex))
                continue
            if self._function_collides_with_progressive_loader(func):
                loader_names = ", ".join(sorted(self._progressive_loader_names()))
                messages.append(
                    f"MCP tool '{func.name}' conflicts with progressive disclosure loader tool name(s): "
                    f"{loader_names}. Set tool_name_prefix or exclude the colliding MCP tool."
                )
                continue
            if any(tool_item is func for tool_item in ctx.tools):
                self._progressive_loaded_tool_names.add(func.name)
                messages.append(f"MCP tool '{func.name}' is already available.")
                continue
            if func.name in function_names_to_load:
                messages.append(f"MCP tool '{func.name}' is already queued to load.")
                continue
            functions_to_load.append(func)
            function_names_to_load.add(func.name)
            messages.append(f"Loaded MCP tool '{func.name}'. It is available on the next model iteration.")
        if not messages:
            return "No MCP tools requested."
        if not functions_to_load:
            return "\n".join(messages)
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", ExperimentalWarning)
                ctx.add_tools(functions_to_load)
        except ValueError as ex:
            raise ToolExecutionException(str(ex), inner_exception=ex) from ex
        self._progressive_loaded_tool_names.update(func.name for func in functions_to_load)
        return "\n".join(messages)

    async def _unload_progressive_mcp_tool(self, ctx: FunctionInvocationContext, tool: str | Sequence[str]) -> str:
        """Unload a progressively loaded MCP tool from the live function-calling tool list."""
        if ctx.tools is None:
            raise ToolExecutionException("unload_tool can only be used inside an agent function-calling run.")
        messages: list[str] = []
        function_names_to_unload: set[str] = set()
        for tool_name in self._progressive_tool_names(tool):
            if tool_name in self._progressive_loader_names():
                messages.append(f"MCP loader tool '{tool_name}' cannot be unloaded.")
                continue
            try:
                func = self._resolve_progressive_function(tool_name)
            except ToolExecutionException as ex:
                messages.append(str(ex))
                continue
            if self._function_collides_with_progressive_loader(func):
                loader_names = ", ".join(sorted(self._progressive_loader_names()))
                messages.append(
                    f"MCP tool '{func.name}' conflicts with progressive disclosure loader tool name(s): "
                    f"{loader_names}. Set tool_name_prefix or exclude the colliding MCP tool."
                )
                continue
            if self._function_matches_names(func, self._always_load_names):
                messages.append(f"MCP tool '{func.name}' is configured in always_load and cannot be unloaded.")
                continue
            if func.name in function_names_to_unload:
                messages.append(f"MCP tool '{func.name}' is already queued to unload.")
                continue
            if func.name not in self._progressive_loaded_tool_names and not any(
                tool_item is func for tool_item in ctx.tools
            ):
                messages.append(f"MCP tool '{func.name}' is not currently loaded.")
                continue
            function_names_to_unload.add(func.name)
            messages.append(f"Unloaded MCP tool '{func.name}'. It will be removed on the next model iteration.")
        if not messages:
            return "No MCP tools requested."
        if not function_names_to_unload:
            return "\n".join(messages)
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", ExperimentalWarning)
                ctx.remove_tools(list(function_names_to_unload))
        except RuntimeError as ex:
            raise ToolExecutionException(str(ex), inner_exception=ex) from ex
        self._progressive_loaded_tool_names.difference_update(function_names_to_unload)
        return "\n".join(messages)

    async def _ensure_lifecycle_owner(self) -> None:
        async with self._lifecycle_lock:
            if self._lifecycle_owner_task is not None and not self._lifecycle_owner_task.done():
                return

            self._lifecycle_queue = asyncio.Queue()
            self._lifecycle_owner_task = asyncio.create_task(
                self._run_lifecycle_owner(),
                name=f"mcp-lifecycle:{self.name}",
            )

    async def _run_lifecycle_owner(self) -> None:
        queue = self._lifecycle_queue
        if queue is None:
            return

        stop_error: BaseException | None = None
        try:
            while True:
                action, reset, load_configured, future = await queue.get()

                try:
                    if action == "connect":
                        await self._connect_on_owner(reset=reset, load_configured=load_configured)
                    elif action == "close":
                        await self._close_on_owner()
                    else:
                        raise RuntimeError(f"Unknown MCP lifecycle action: {action}")
                except asyncio.CancelledError as ex:
                    stop_error = ex
                    if not future.done():
                        future.set_exception(ex)
                    raise
                except Exception as ex:
                    if not future.done():
                        future.set_exception(ex)
                else:
                    if not future.done():
                        future.set_result(None)

                if action == "close":
                    return
        except asyncio.CancelledError as ex:
            stop_error = ex
            raise
        finally:
            while True:
                try:
                    _, _, _, future = queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                if not future.done():
                    future.set_exception(stop_error or RuntimeError("MCP lifecycle owner stopped unexpectedly."))

            self._lifecycle_queue = None
            self._lifecycle_owner_task = None

    def _is_lifecycle_owner_task(self) -> bool:
        owner_task = self._lifecycle_owner_task
        return owner_task is not None and asyncio.current_task() is owner_task

    async def _run_on_lifecycle_owner(
        self,
        action: str,
        *,
        reset: bool = False,
        load_configured: bool = True,
    ) -> None:
        await self._ensure_lifecycle_owner()

        if self._is_lifecycle_owner_task():
            if action == "connect":
                await self._connect_on_owner(reset=reset, load_configured=load_configured)
            elif action == "close":
                await self._close_on_owner()
            else:
                raise RuntimeError(f"Unknown MCP lifecycle action: {action}")
            return

        queue = self._lifecycle_queue
        if queue is None:
            raise RuntimeError("MCP lifecycle owner is not available.")

        future = asyncio.get_running_loop().create_future()
        await queue.put((action, reset, load_configured, future))
        await future

    async def _safe_close_exit_stack(self) -> None:
        """Safely close the exit stack, handling unexpected cleanup failures."""
        try:
            await self._exit_stack.aclose()
        except RuntimeError as e:
            error_msg = str(e).lower()
            if "cancel scope" in error_msg:
                logger.warning(
                    "Could not cleanly close MCP exit stack due to cancel scope error. "
                    "This indicates MCP lifecycle ownership was lost. Error: %s",
                    e,
                )
            else:
                raise
        except asyncio.CancelledError:
            logger.warning("Could not cleanly close MCP exit stack because the lifecycle owner task was cancelled.")
        except Exception as e:
            if type(e).__name__ == "ExceptionGroup":
                logger.warning("Could not cleanly close MCP exit stack due to cleanup error group. Error: %s", e)
            else:
                raise

    async def _close_and_check_cancelled(self, ex: BaseException) -> bool:
        """Close the exit stack and return True if *ex* is a genuine task cancellation.

        Callers should immediately re-raise when this returns True::

            if await self._close_and_check_cancelled(ex):
                raise
        """
        await self._safe_close_exit_stack()
        return _should_propagate_cancelled_error(ex)

    def _reset_session_state(self) -> None:
        self._server_capabilities = None
        self._supports_tools = True
        self._supports_prompts = True
        self._supports_logging = None
        self._ping_available = True
        self._sampling_request_count = 0

    def _set_server_capabilities(self, capabilities: types.ServerCapabilities | None) -> None:
        self._server_capabilities = capabilities
        if capabilities is None:
            self._supports_tools = False
            self._supports_prompts = False
            self._supports_logging = False
            return

        self._supports_tools = getattr(capabilities, "tools", None) is not None
        self._supports_prompts = getattr(capabilities, "prompts", None) is not None
        self._supports_logging = getattr(capabilities, "logging", None) is not None

    async def _reconnect_without_loading(self) -> None:
        if self._is_lifecycle_owner_task():
            await self._connect_on_owner(reset=True, load_configured=False)
            return

        await self._run_on_lifecycle_owner("connect", reset=True, load_configured=False)

    async def connect(self, *, reset: bool = False) -> None:
        mark_feature_used(FeatureIndex.CORE_MCP)
        if self._is_lifecycle_owner_task():
            await self._connect_on_owner(reset=reset)
            return

        async with self._lifecycle_request_lock:
            await self._run_on_lifecycle_owner("connect", reset=reset)

    async def _connect_on_owner(self, *, reset: bool = False, load_configured: bool = True) -> None:
        """Connect to the MCP server.

        Establishes a connection to the MCP server, initializes the session,
        and loads tools and prompts if configured to do so.

        Keyword Args:
            reset: If True, forces a reconnection even if already connected.
            load_configured: If True, loads tools and prompts according to the constructor flags.

        Raises:
            ToolException: If connection or session initialization fails.
        """
        if reset:
            await self._safe_close_exit_stack()
            self.session = None
            self.is_connected = False
            self._reset_session_state()
            self._exit_stack = AsyncExitStack()
        if not self.session:
            try:
                transport = await self._exit_stack.enter_async_context(self.get_mcp_client())
            except (Exception, asyncio.CancelledError) as ex:
                # On Python >= 3.11, re-raise genuine task cancellation (task.cancelling() > 0)
                # instead of wrapping it in ToolException. On Python < 3.11, task.cancelling()
                # is unavailable so MCP-internal CancelledErrors cannot be distinguished from
                # caller-driven cancellation; they are wrapped as ToolException in that case.
                if await self._close_and_check_cancelled(ex):
                    raise
                command = getattr(self, "command", None)
                if command:
                    error_msg = f"Failed to start MCP server '{command}': {ex}"
                else:
                    error_msg = f"Failed to connect to MCP server: {ex}"
                # CancelledError is a BaseException (not Exception) on Python >= 3.8, so
                # inner_exception=None and ToolException.__init__ won't log exc_info.
                if isinstance(ex, asyncio.CancelledError):
                    logger.debug(error_msg, exc_info=True)
                raise ToolException(error_msg, inner_exception=ex if isinstance(ex, Exception) else None) from ex
            try:
                try:
                    from mcp import types
                    from mcp.client.session import ClientSession as runtime_client_session
                except ModuleNotFoundError as ex:
                    await self._safe_close_exit_stack()
                    raise ToolException(
                        "MCP support requires `mcp`. Please install `mcp`.",
                        inner_exception=ex,
                    ) from ex

                sampling_capabilities = None
                if self.client is not None:
                    sampling_capabilities = types.SamplingCapability(
                        tools=types.SamplingToolsCapability(),
                    )
                session = await self._exit_stack.enter_async_context(
                    runtime_client_session(
                        read_stream=transport[0],
                        write_stream=transport[1],
                        read_timeout_seconds=(
                            timedelta(seconds=self.request_timeout) if self.request_timeout else None
                        ),
                        message_handler=self.message_handler,
                        logging_callback=self.logging_callback,
                        sampling_callback=self.sampling_callback,
                        sampling_capabilities=sampling_capabilities,
                    )
                )
            except (Exception, asyncio.CancelledError) as ex:
                if await self._close_and_check_cancelled(ex):
                    raise
                session_error_msg = f"Failed to create MCP session: {ex}"
                if isinstance(ex, asyncio.CancelledError):
                    logger.debug(session_error_msg, exc_info=True)
                raise ToolException(
                    message=session_error_msg,
                    inner_exception=ex if isinstance(ex, Exception) else None,
                ) from ex
            try:
                with create_mcp_client_span("initialize", attributes=self._mcp_base_span_attributes()) as init_span:
                    initialize_result = await session.initialize()
                    init_span.set_attribute(OtelAttr.MCP_PROTOCOL_VERSION, initialize_result.protocolVersion)
                    self._set_server_capabilities(getattr(initialize_result, "capabilities", None))
            except (Exception, asyncio.CancelledError) as ex:
                if await self._close_and_check_cancelled(ex):
                    raise
                # Provide context about initialization failure
                command = getattr(self, "command", None)
                if command:
                    args_str = " ".join(getattr(self, "args", []))
                    full_command = f"{command} {args_str}".strip()
                    error_msg = f"MCP server '{full_command}' failed to initialize: {ex}"
                else:
                    error_msg = f"MCP server failed to initialize: {ex}"
                if isinstance(ex, asyncio.CancelledError):
                    logger.debug(error_msg, exc_info=True)
                raise ToolException(error_msg, inner_exception=ex if isinstance(ex, Exception) else None) from ex
            self.session = session
        elif self.session._request_id == 0:  # type: ignore[attr-defined]
            # If the session is not initialized, we need to reinitialize it
            with create_mcp_client_span("initialize", attributes=self._mcp_base_span_attributes()) as init_span:
                initialize_result = await self.session.initialize()
                init_span.set_attribute(OtelAttr.MCP_PROTOCOL_VERSION, initialize_result.protocolVersion)
                self._set_server_capabilities(getattr(initialize_result, "capabilities", None))
        elif self._server_capabilities is None:
            self._set_server_capabilities(getattr(self.session, "_server_capabilities", None))
        logger.debug("Connected to MCP server: %s", self.session)
        self.is_connected = True
        if load_configured and self.load_tools_flag:
            if self._supports_tools:
                await self.load_tools()
            self._tools_loaded = True
        if load_configured and self.load_prompts_flag:
            if self._supports_prompts:
                await self.load_prompts()
            self._prompts_loaded = True

        if logger.level != logging.NOTSET and self._supports_logging is not False:
            try:
                level_name = cast(
                    Any, next(level for level, value in LOG_LEVEL_MAPPING.items() if value == logger.level)
                )
                await self.session.set_logging_level(level_name)
            except Exception as exc:
                logger.warning("Failed to set log level to %s", logger.level, exc_info=exc)

    async def _sampling_request_approved(self, params: types.CreateMessageRequestParams) -> bool:
        """Run the configured sampling approval gate.

        Returns ``True`` only when an approval callback is configured and approves the request.
        When no callback is set, the request is denied (safe default for untrusted servers).
        """
        callback = self.sampling_approval_callback
        if callback is None:
            logger.warning(
                "Denying MCP sampling request from '%s': no 'sampling_approval_callback' configured.",
                self.name,
            )
            return False
        try:
            outcome = callback(params)
            if isawaitable(outcome):
                outcome = await outcome
        except Exception as ex:
            logger.warning(
                "Denying MCP sampling request from '%s': approval callback raised %s.",
                self.name,
                ex,
                exc_info=True,
            )
            return False
        approved = bool(outcome)
        if not approved:
            logger.warning("MCP sampling request from '%s' was denied by the approval callback.", self.name)
        return approved

    def _capped_sampling_max_tokens(self, requested: int) -> int:
        """Clamp the server-requested ``maxTokens`` to ``sampling_max_tokens`` when configured."""
        cap = self.sampling_max_tokens
        if cap is not None and requested > cap:
            logger.warning(
                "Capping MCP sampling maxTokens for '%s' from %d to %d.",
                self.name,
                requested,
                cap,
            )
            return cap
        return requested

    async def sampling_callback(
        self,
        context: RequestContext[ClientSession, Any],
        params: types.CreateMessageRequestParams,
    ) -> types.CreateMessageResult | types.CreateMessageResultWithTools | types.ErrorData:
        """Callback function for sampling.

        This function is called when the MCP server sends a ``sampling/createMessage``
        request. It enforces safety guardrails and, if the request is approved, uses the
        configured chat client to generate a response.

        Safety:
            MCP servers are untrusted third parties, so forwarding server-controlled prompts
            to the chat client without review is a confused-deputy risk. This callback
            therefore applies, in order: a per-session rate limit
            (``sampling_max_requests``), an approval gate (``sampling_approval_callback``,
            which **denies by default** when not configured), and a ``maxTokens`` cap
            (``sampling_max_tokens``). To allow sampling, pass a ``sampling_approval_callback``
            that returns a truthy value (use ``lambda params: True`` to auto-approve as an
            explicit opt-in).

        Note:
            This is the default implementation. It can be overridden to allow more complex
            sampling. It gets added to the session at initialization time, so overriding it is
            the best way to customize this behavior.

        Args:
            context: The request context from the MCP server.
            params: The message creation request parameters.

        Returns:
            Either a CreateMessageResult/CreateMessageResultWithTools with the generated message or ErrorData if the
            request is denied, rate limited, or generation fails.
        """
        from mcp import types

        if not self.client:
            return types.ErrorData(
                code=types.INTERNAL_ERROR,
                message="No chat client available. Please set a chat client.",
            )

        logger.warning(
            "MCP server '%s' sent a sampling/createMessage request (%d message(s), maxTokens=%s).",
            self.name,
            len(params.messages),
            params.maxTokens,
        )

        if self.sampling_max_requests is not None:
            if self._sampling_request_count >= self.sampling_max_requests:
                logger.warning(
                    "Denying MCP sampling request from '%s': per-session limit of %d reached.",
                    self.name,
                    self.sampling_max_requests,
                )
                return types.ErrorData(
                    code=types.INVALID_REQUEST,
                    message="Sampling rate limit exceeded for this MCP session.",
                )
            self._sampling_request_count += 1

        if not await self._sampling_request_approved(params):
            if self.sampling_approval_callback is None:
                message = (
                    "Sampling request denied. MCP sampling is disabled by default for untrusted "
                    "servers; provide a 'sampling_approval_callback' that approves the request to "
                    "enable it."
                )
            else:
                message = "Sampling request denied by the 'sampling_approval_callback'."
            return types.ErrorData(code=types.INVALID_REQUEST, message=message)

        messages: list[Message] = []
        for msg in params.messages:
            messages.append(self._parse_message_from_mcp(msg))

        options: ChatOptions[None] = {}
        if params.systemPrompt is not None:
            options["instructions"] = params.systemPrompt
        if params.tools is not None:
            options["tools"] = [
                FunctionTool(
                    name=tool.name,
                    description=tool.description or "",
                    input_model=tool.inputSchema,
                )
                for tool in params.tools
            ]
        if params.toolChoice is not None and params.toolChoice.mode is not None:
            options["tool_choice"] = params.toolChoice.mode

        if params.temperature is not None:
            options["temperature"] = params.temperature
        options["max_tokens"] = self._capped_sampling_max_tokens(params.maxTokens)
        if params.stopSequences is not None:
            options["stop"] = params.stopSequences

        try:
            chat_client: Any = self.client
            response: Any = await chat_client.get_response(
                messages,
                options=options or None,
            )
        except Exception as ex:
            logger.debug("Sampling callback error: %s", ex, exc_info=True)
            return types.ErrorData(
                code=types.INTERNAL_ERROR,
                message=f"Failed to get chat message content: {ex}",
            )
        if not response or not response.messages:
            return types.ErrorData(
                code=types.INTERNAL_ERROR,
                message="Failed to get chat message content.",
            )
        mcp_contents = [
            mcp_content for message in response.messages for mcp_content in self._prepare_message_for_mcp(message)
        ]
        tool_use_contents: list[types.SamplingMessageContentBlock] = []
        for content in mcp_contents:
            if isinstance(content, types.ToolUseContent):
                tool_use_contents.append(content)
        if tool_use_contents:
            return types.CreateMessageResultWithTools(
                role="assistant",
                content=tool_use_contents,
                model=response.model or "unknown",
                stopReason="toolUse",
            )

        # grab the first content that is of type TextContent or ImageContent
        mcp_content = next(
            (content for content in mcp_contents if isinstance(content, (types.TextContent, types.ImageContent))),
            None,
        )
        if not mcp_content:
            return types.ErrorData(
                code=types.INTERNAL_ERROR,
                message="Failed to get right content types from the response.",
            )
        return types.CreateMessageResult(
            role="assistant",
            content=mcp_content,
            model=response.model or "unknown",
        )

    async def logging_callback(self, params: types.LoggingMessageNotificationParams) -> None:
        """Callback function for logging.

        This function is called when the MCP Server sends a log message.
        By default it will log the message to the logger with the level set in the params.

        Note:
            Subclass MCPTool and override this function if you want to adapt the behavior.

        Args:
            params: The logging message notification parameters from the MCP server.
        """
        logger.log(LOG_LEVEL_MAPPING[params.level], params.data)

    async def message_handler(
        self,
        message: (RequestResponder[types.ServerRequest, types.ClientResult] | types.ServerNotification | Exception),
    ) -> None:
        """Handle messages from the MCP server.

        By default this function will handle exceptions on the server by logging them,
        and it will trigger a reload of the tools and prompts when the list changed
        notification is received.

        Note:
            If you want to extend this behavior, you can subclass MCPTool and override
            this function. If you want to keep the default behavior, make sure to call
            ``super().message_handler(message)``.

        Args:
            message: The message from the MCP server (request responder, notification, or exception).
        """
        from mcp import types

        if isinstance(message, Exception):
            logger.error("Error from MCP server: %s", message, exc_info=message)
            return
        if isinstance(message, types.ServerNotification):
            match message.root.method:
                case "notifications/tools/list_changed":
                    self._schedule_reload(self.load_tools())
                case "notifications/prompts/list_changed":
                    self._schedule_reload(self.load_prompts())
                case _:
                    logger.debug("Unhandled notification: %s", message.root.method)

    def _schedule_reload(self, coro: Coroutine[Any, Any, None]) -> None:
        """Schedule a reload coroutine as a background task.

        Reloads (load_tools / load_prompts) triggered by MCP server
        notifications must NOT be awaited inside the message handler because
        the handler runs on the MCP SDK's single-threaded receive loop.
        Awaiting a session request (e.g. ``list_tools``) from within that loop
        deadlocks: the receive loop cannot read the response while it is
        blocked waiting for the handler to return.

        Instead we fire the reload as an independent ``asyncio.Task`` and keep
        a strong reference in ``_pending_reload_tasks`` so it is not garbage-
        collected before completion.  Only one reload per kind (tools / prompts)
        is kept in flight; a new notification cancels the previous pending task
        for the same coroutine name to avoid unbounded growth.
        """
        # Cancel-and-replace: only one reload per kind should be in flight.
        reload_name = f"mcp-reload:{self.name}:{coro.__qualname__}"
        for existing in list(self._pending_reload_tasks):
            if existing.get_name() == reload_name and not existing.done():
                logger.debug("Cancelling in-flight reload %s; superseded by new notification", reload_name)
                existing.cancel()

        async def _safe_reload() -> None:
            try:
                await coro
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.warning("Background MCP reload failed", exc_info=True)

        task = asyncio.create_task(_safe_reload(), name=reload_name)
        self._pending_reload_tasks.add(task)
        task.add_done_callback(self._pending_reload_tasks.discard)

    def _determine_approval_mode(
        self,
        *candidate_names: str,
    ) -> Literal["always_require", "never_require"] | None:
        if isinstance(self.approval_mode, dict):
            if (always_require := self.approval_mode.get("always_require_approval")) and any(
                name in always_require for name in candidate_names
            ):
                return "always_require"
            if (never_require := self.approval_mode.get("never_require_approval")) and any(
                name in never_require for name in candidate_names
            ):
                return "never_require"
            return None
        return self.approval_mode  # type: ignore[return-value]

    async def load_prompts(self) -> None:
        """Load prompts from the MCP server.

        Retrieves available prompts from the connected MCP server and converts
        them into FunctionTool instances. Handles pagination automatically.

        Raises:
            ToolExecutionException: If the MCP server is not connected.
        """
        async with self._function_load_lock:
            await self._load_prompts_locked()

    async def _load_prompts_locked(self) -> None:
        from anyio import ClosedResourceError
        from mcp import types

        if not self._supports_prompts:
            logger.debug("Skipping MCP prompt loading because the server did not advertise prompts support.")
            return

        # Track existing function names to prevent duplicates
        existing_names = {func.name for func in self._functions}

        params: types.PaginatedRequestParams | None = None
        while True:
            prompt_list: types.ListPromptsResult | None = None
            for attempt in range(2):
                try:
                    # Ensure connection is still valid before each page request
                    await self._ensure_connected()
                    if not self._supports_prompts:
                        logger.debug(
                            "Skipping MCP prompt loading because the server did not advertise prompts support."
                        )
                        return
                    with create_mcp_client_span("prompts/list", attributes=self._mcp_base_span_attributes()):
                        prompt_list = await self.session.list_prompts(params=params)  # type: ignore[union-attr]
                    break
                except ClosedResourceError as cl_ex:
                    if attempt == 0:
                        logger.info("MCP connection closed unexpectedly while loading prompts. Reconnecting...")
                        try:
                            await self._reconnect_without_loading()
                        except Exception as reconn_ex:
                            raise ToolExecutionException(
                                "Failed to reconnect to MCP server.",
                                inner_exception=reconn_ex,
                            ) from reconn_ex
                        continue
                    logger.error("MCP connection closed unexpectedly after reconnection: %s", cl_ex)
                    raise ToolExecutionException(
                        "Failed to load prompts - connection lost.",
                        inner_exception=cl_ex,
                    ) from cl_ex

            if prompt_list is None:
                raise ToolExecutionException("Failed to load prompts.")

            for prompt in prompt_list.prompts:
                normalized_name = _normalize_mcp_name(prompt.name)
                local_name = _build_prefixed_mcp_name(normalized_name, self.tool_name_prefix)

                # Skip if already loaded
                if local_name in existing_names:
                    continue

                input_model = _get_input_model_from_mcp_prompt(prompt)
                approval_mode = self._determine_approval_mode(
                    *_mcp_config_candidate_names(
                        local_name=local_name,
                        normalized_name=normalized_name,
                        remote_name=prompt.name,
                    )
                )
                func: FunctionTool = FunctionTool(
                    func=partial(self.get_prompt, prompt.name),
                    name=local_name,
                    description=prompt.description or "",
                    approval_mode=approval_mode,
                    input_model=input_model,
                    additional_properties={
                        _MCP_REMOTE_NAME_KEY: prompt.name,
                        _MCP_NORMALIZED_NAME_KEY: normalized_name,
                    },
                )
                self._functions.append(func)
                existing_names.add(local_name)

            # Check if there are more pages
            if not prompt_list.nextCursor:
                break
            params = types.PaginatedRequestParams(cursor=prompt_list.nextCursor)

    async def load_tools(self) -> None:
        """Load tools from the MCP server.

        Retrieves available tools from the connected MCP server and converts
        them into FunctionTool instances. Handles pagination automatically.

        Raises:
            ToolExecutionException: If the MCP server is not connected.
        """
        async with self._function_load_lock:
            await self._load_tools_locked()

    async def _load_tools_locked(self) -> None:
        from anyio import ClosedResourceError
        from mcp import types

        if not self._supports_tools:
            logger.debug("Skipping MCP tool loading because the server did not advertise tools support.")
            return

        # Track existing function names to prevent duplicates
        existing_remote_by_local: dict[str, str] = {}
        for func in self._functions:
            remote_name = (func.additional_properties or {}).get(_MCP_REMOTE_NAME_KEY)
            if isinstance(remote_name, str):
                existing_remote_by_local[func.name] = remote_name
        tool_call_meta_by_name: dict[str, dict[str, Any]] = {}
        tool_task_support_by_name: dict[str, str] = {}
        tool_param_names_by_name: dict[str, set[str]] = {}

        params: types.PaginatedRequestParams | None = None
        while True:
            tool_list: types.ListToolsResult | None = None
            for attempt in range(2):
                try:
                    # Ensure connection is still valid before each page request
                    await self._ensure_connected()
                    if not self._supports_tools:
                        logger.debug("Skipping MCP tool loading because the server did not advertise tools support.")
                        return
                    with create_mcp_client_span("tools/list", attributes=self._mcp_base_span_attributes()):
                        tool_list = await self.session.list_tools(params=params)  # type: ignore[union-attr]
                    break
                except ClosedResourceError as cl_ex:
                    if attempt == 0:
                        logger.info("MCP connection closed unexpectedly while loading tools. Reconnecting...")
                        try:
                            await self._reconnect_without_loading()
                        except Exception as reconn_ex:
                            raise ToolExecutionException(
                                "Failed to reconnect to MCP server.",
                                inner_exception=reconn_ex,
                            ) from reconn_ex
                        continue
                    logger.error("MCP connection closed unexpectedly after reconnection: %s", cl_ex)
                    raise ToolExecutionException(
                        "Failed to load tools - connection lost.",
                        inner_exception=cl_ex,
                    ) from cl_ex

            if tool_list is None:
                raise ToolExecutionException("Failed to load tools.")

            for tool in tool_list.tools:
                if tool.meta is not None:
                    tool_call_meta_by_name[tool.name] = _validate_mcp_meta(tool.meta) or {}

                task_support = getattr(getattr(tool, "execution", None), "taskSupport", None)
                if task_support is not None:
                    tool_task_support_by_name[tool.name] = task_support

                # Normalize inputSchema: ensure "properties" exists for object schemas.
                # Some MCP servers (e.g. zero-argument tools) omit "properties",
                # which causes OpenAI API to reject the schema with a 400 error.
                # Guard against non-conforming MCP servers that send inputSchema=None
                # despite the MCP spec typing it as dict[str, Any].
                input_schema = dict(tool.inputSchema or {})
                if input_schema.get("type") == "object" and "properties" not in input_schema:
                    input_schema["properties"] = {}

                # Register declared param names before the existing-tool skip below so that
                # reloads (e.g. notifications/tools/list_changed) preserve the allowlist for
                # tools that are already loaded, consistent with tool_call_meta_by_name and
                # tool_task_support_by_name above.
                schema_properties = input_schema.get("properties")
                tool_param_names_by_name[tool.name] = (
                    set(cast(dict[str, Any], schema_properties)) if isinstance(schema_properties, dict) else set()
                )

                normalized_name = _normalize_mcp_name(tool.name)
                local_name = _build_prefixed_mcp_name(normalized_name, self.tool_name_prefix)

                # Skip if already loaded
                if local_name in existing_remote_by_local:
                    if existing_remote_by_local.get(local_name) != tool.name:
                        raise ToolExecutionException(
                            "MCP server advertised multiple tools that map to the same local function name: "
                            f"{existing_remote_by_local[local_name]!r} and {tool.name!r} both map to "
                            f"{local_name!r}."
                        )
                    continue

                existing_remote_by_local[local_name] = tool.name

                approval_mode = self._determine_approval_mode(
                    *_mcp_config_candidate_names(
                        local_name=local_name,
                        normalized_name=normalized_name,
                        remote_name=tool.name,
                    )
                )

                async def _call_tool_with_runtime_kwargs(
                    ctx: FunctionInvocationContext,
                    *,
                    _remote_tool_name: str = tool.name,
                    **kwargs: Any,
                ) -> str | list[Content]:
                    trusted_meta = ctx.kwargs.get("_meta")
                    call_kwargs = dict(ctx.kwargs)
                    call_kwargs.update(kwargs)
                    if trusted_meta is not None:
                        call_kwargs["_meta"] = trusted_meta
                    else:
                        call_kwargs.pop("_meta", None)
                    return await self.call_tool(_remote_tool_name, **call_kwargs)

                # Create FunctionTools out of each tool
                func: FunctionTool = FunctionTool(
                    func=_call_tool_with_runtime_kwargs,
                    name=local_name,
                    description=tool.description or "",
                    approval_mode=approval_mode,
                    input_model=input_schema,
                    additional_properties={
                        _MCP_REMOTE_NAME_KEY: tool.name,
                        _MCP_NORMALIZED_NAME_KEY: normalized_name,
                    },
                )
                self._functions.append(func)

            # Check if there are more pages
            if not tool_list.nextCursor:
                break
            params = types.PaginatedRequestParams(cursor=tool_list.nextCursor)

        self._tool_call_meta_by_name = tool_call_meta_by_name
        self._tool_task_support_by_name = tool_task_support_by_name
        self._tool_param_names_by_name = tool_param_names_by_name

    async def _close_on_owner(self) -> None:
        # Cancel any pending reload tasks before tearing down the session.
        tasks = list(self._pending_reload_tasks)
        for task in tasks:
            task.cancel()
        self._pending_reload_tasks.clear()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        await self._safe_close_exit_stack()
        self._exit_stack = AsyncExitStack()
        self.session = None
        self.is_connected = False
        self._reset_session_state()

    async def close(self) -> None:
        """Disconnect from the MCP server.

        Closes the connection and cleans up resources.
        """
        if self._is_lifecycle_owner_task():
            await self._close_on_owner()
            return

        async with self._lifecycle_request_lock:
            await self._run_on_lifecycle_owner("close")

    @abstractmethod
    def get_mcp_client(self) -> _AsyncGeneratorContextManager[Any, None]:
        """Get an MCP client.

        Returns:
            An async context manager for the MCP client transport.
        """
        pass

    async def _ensure_connected(self) -> None:
        """Ensure the connection is valid, reconnecting if necessary.

        This method proactively checks if the connection is valid and
        reconnects if it's not, avoiding the need to catch ClosedResourceError.

        Raises:
            ToolExecutionException: If reconnection fails.
        """
        from mcp.shared.exceptions import McpError

        if not self._ping_available:
            return

        try:
            await self.session.send_ping()  # type: ignore[union-attr]
        except McpError as mcp_exc:
            if mcp_exc.error.code == -32601:
                self._ping_available = False
                logger.debug("Skipping future MCP pings because the server does not support ping.")
                return
            logger.info("MCP connection invalid or closed. Reconnecting...")
            try:
                await self._reconnect_without_loading()
            except Exception as ex:
                raise ToolExecutionException(
                    "Failed to establish MCP connection.",
                    inner_exception=ex,
                ) from ex
        except Exception:
            logger.info("MCP connection invalid or closed. Reconnecting...")
            try:
                await self._reconnect_without_loading()
            except Exception as ex:
                raise ToolExecutionException(
                    "Failed to establish MCP connection.",
                    inner_exception=ex,
                ) from ex

    def _effective_task_options(self) -> MCPTaskOptions:
        """Return the effective MCPTaskOptions, lazily constructing defaults on first use.

        Defers the implicit ``MCPTaskOptions()`` so the experimental warning only
        fires when LRO is actually engaged (server advertises ``taskSupport=required``).
        """
        explicit = self._task_options_explicit
        if explicit is not None:
            return explicit
        if self._task_options_default is None:
            self._task_options_default = MCPTaskOptions()
        return self._task_options_default

    @property
    def task_options(self) -> MCPTaskOptions:
        """The effective MCPTaskOptions for this tool (lazy defaults)."""
        return self._effective_task_options()

    @task_options.setter
    def task_options(self, value: MCPTaskOptions | None) -> None:
        self._task_options_explicit = value
        self._task_options_default = None

    async def call_tool(self, tool_name: str, **kwargs: Any) -> str | list[Content]:
        """Call a tool with the given arguments.

        Args:
            tool_name: The name of the tool to call.

        Keyword Args:
            _meta: Optional ``dict[str, Any]`` of MCP request metadata. This reserved key is passed as the
                ``meta`` parameter of the underlying ``session.call_tool`` call rather than as a tool argument.
                OpenTelemetry propagation overrides caller-supplied keys, and metadata from ``tools/list``
                overrides both.
            kwargs: Remaining arguments to pass to the tool.

        Returns:
            A list of Content items representing the tool output.  The default
            ``parse_tool_results`` always returns ``list[Content]``; a custom
            callback may return a plain ``str`` which is also accepted.

        Raises:
            ToolExecutionException: If the MCP server is not connected, tools are not loaded,
                or the tool call fails.
        """
        if not self.load_tools_flag:
            raise ToolExecutionException(
                "Tools are not loaded for this server, please set load_tools=True in the constructor."
            )

        # Tools advertising taskSupport == "required" cannot complete via plain tools/call;
        # route through the long-running task lifecycle transparently.
        if self._tool_task_support_by_name.get(tool_name) == "required":
            return await self.call_tool_as_task(tool_name, **kwargs)

        filtered_kwargs, meta = self._prepare_call_kwargs(tool_name, kwargs)

        parser = self.parse_tool_results or self._parse_tool_result_from_mcp

        # Build MCP span attributes for tools/call
        mcp_span_attrs = self._mcp_base_span_attributes()
        mcp_span_attrs.update({
            OtelAttr.TOOL_NAME: tool_name,
            OtelAttr.OPERATION: OtelAttr.TOOL_EXECUTION_OPERATION,
        })
        with create_mcp_client_span("tools/call", target=tool_name, attributes=mcp_span_attrs) as span:
            return await self._call_tool_with_retries(tool_name, filtered_kwargs, meta, parser, span)

    async def _call_tool_with_retries(
        self,
        tool_name: str,
        filtered_kwargs: dict[str, Any],
        meta: dict[str, Any] | None,
        parser: Callable[..., str | list[Content]],
        span: otel_trace.Span,
    ) -> str | list[Content]:
        """Execute the MCP tools/call RPC with retry logic."""
        from anyio import ClosedResourceError
        from mcp.shared.exceptions import McpError

        for attempt in range(2):
            try:
                result = await self.session.call_tool(tool_name, arguments=filtered_kwargs, meta=meta)  # type: ignore
                if result.isError:
                    parsed = parser(result)
                    text = (
                        "\n".join(c.text for c in parsed if c.type == "text" and c.text)
                        if isinstance(parsed, list)
                        else str(parsed)
                    )
                    # Per OTel MCP semconv: set error.type="tool_error" for isError results
                    if span.is_recording():
                        set_mcp_span_error(span, "tool_error", text or str(parsed))
                    raise ToolExecutionException(text or str(parsed))
                return parser(result)
            except ToolExecutionException:
                raise
            except (ClosedResourceError, McpError) as call_ex:
                is_session_terminated = (
                    isinstance(call_ex, McpError) and "session terminated" in call_ex.error.message.lower()
                )
                is_connection_lost = isinstance(call_ex, ClosedResourceError) or is_session_terminated
                if not is_connection_lost:
                    error_message = call_ex.error.message if isinstance(call_ex, McpError) else str(call_ex)
                    if span.is_recording():
                        set_mcp_span_error(span, type(call_ex).__name__, error_message)
                    raise ToolExecutionException(error_message, inner_exception=call_ex) from call_ex

                if attempt == 0:
                    # First attempt failed, try reconnecting.
                    logger.info("MCP connection closed or terminated unexpectedly. Reconnecting...")
                    try:
                        await self.connect(reset=True)
                        continue
                    except Exception as reconn_ex:
                        raise ToolExecutionException(
                            "Failed to reconnect to MCP server.",
                            inner_exception=reconn_ex,
                        ) from reconn_ex

                # Second attempt also failed, give up.
                logger.error("MCP connection closed unexpectedly after reconnection: %s", call_ex)
                if span.is_recording():
                    set_mcp_span_error(span, type(call_ex).__name__, str(call_ex))
                raise ToolExecutionException(
                    f"Failed to call tool '{tool_name}' - connection lost.",
                    inner_exception=call_ex,
                ) from call_ex
            except Exception as ex:
                if span.is_recording():
                    set_mcp_span_error(span, type(ex).__name__, str(ex))
                raise ToolExecutionException(f"Failed to call tool '{tool_name}'.", inner_exception=ex) from ex
        raise ToolExecutionException(f"Failed to call tool '{tool_name}' after retries.")

    def _resolved_extra_args(self, tool_name: str) -> set[str]:
        """Return the user-configured extra argument names allowed for a tool."""
        return self._global_extra_arg_names | self._tool_extra_arg_names.get(tool_name, set())

    def _prepare_call_kwargs(
        self, tool_name: str, kwargs: dict[str, Any]
    ) -> tuple[dict[str, Any], dict[str, Any] | None]:
        """Filter kwargs down to the tool's arguments and build the merged MCP request metadata."""
        user_meta = _validate_mcp_meta(kwargs.get("_meta"))

        # Allowlist: forward only the tool's declared parameters (from inputSchema.properties)
        # plus any user-configured extra argument names. Everything else - notably the
        # framework runtime kwargs injected through the function-invocation pipeline - is
        # stripped so it is never forwarded to the MCP server. Tools that declare no usable
        # properties forward only the user-configured extras.
        #
        # The extra names come exclusively from additional_tool_argument_names, which is set in
        # user code at construction time; there is no per-call override, so a model-issued tool
        # call cannot change which names are allowed through.
        #
        # The framework denylist acts as a safety net for keys a server *declares* in its
        # schema that collide with internal, non-serializable framework objects (e.g. a tool
        # that declares a parameter literally named "thread"): such declared-but-denylisted
        # keys are dropped. Names the user explicitly opts in via additional_tool_argument_names
        # always win. The reserved _meta key is handled separately above and never forwarded as
        # an argument.
        declared = self._tool_param_names_by_name.get(tool_name, set())
        extras = self._resolved_extra_args(tool_name)
        filtered_kwargs = {
            k: v
            for k, v in kwargs.items()
            if k != "_meta" and (k in extras or (k in declared and k not in _MCP_FRAMEWORK_DENYLIST))
        }

        # Some MCP proxies require their tools/list metadata to be echoed on tools/call.
        request_meta = dict(user_meta) if user_meta is not None else None
        request_meta = _inject_otel_into_mcp_meta(request_meta, overwrite=True)
        tool_meta = _validate_mcp_meta(self._tool_call_meta_by_name.get(tool_name))
        if tool_meta is not None:
            request_meta = {**(request_meta or {}), **tool_meta}
        return filtered_kwargs, request_meta

    async def call_tool_as_task(self, tool_name: str, **kwargs: Any) -> str | list[Content]:
        """Call an MCP tool via the long-running task lifecycle (SEP-2663).

        Issues an augmented ``tools/call`` with ``params.task`` set from
        ``self.task_options``, then polls ``tasks/get`` until the server reports a
        terminal status. On ``completed`` the payload is fetched via ``tasks/result``,
        validated as a ``CallToolResult`` and parsed identically to :meth:`call_tool`.

        Local cancellation triggers a best-effort ``tasks/cancel`` (controlled by
        :attr:`MCPTaskOptions.cancel_remote_task_on_local_cancellation`) before
        ``asyncio.CancelledError`` is re-raised.

        Args:
            tool_name: The remote MCP tool name.

        Keyword Args:
            kwargs: Arguments forwarded to the tool. See :meth:`call_tool` for the
                framework kwargs that are filtered out.

        Returns:
            A list of Content items (or a string when a custom ``parse_tool_results``
            callback is configured).
        """
        from anyio import ClosedResourceError
        from mcp.shared.exceptions import McpError

        if not self.load_tools_flag:
            raise ToolExecutionException(
                "Tools are not loaded for this server, please set load_tools=True in the constructor."
            )

        filtered_kwargs, meta = self._prepare_call_kwargs(tool_name, kwargs)
        parser = self.parse_tool_results or self._parse_tool_result_from_mcp

        # Submit the task: issue augmented tools/call. Do NOT retry on connection loss here:
        # the server may have accepted the request and created a task before the
        # response was lost, so retrying could start the long-running operation twice.
        # Reconnect-and-retry is only safe after the task_id is known.
        try:
            task_id, fallback_result = await self._call_tool_as_task_create(tool_name, filtered_kwargs, meta)
        except (ClosedResourceError, McpError) as ex:
            if not self._is_connection_lost(ex):
                error_message = ex.error.message if isinstance(ex, McpError) else str(ex)
                raise ToolExecutionException(error_message, inner_exception=ex) from ex
            raise ToolExecutionException(
                f"Failed to call tool '{tool_name}' - connection lost; task state unknown.",
                inner_exception=ex,
            ) from ex
        except ToolExecutionException:
            raise
        except Exception as ex:
            raise ToolExecutionException(f"Failed to call tool '{tool_name}'.", inner_exception=ex) from ex

        # Server returned a CallToolResult (no task created) or fell back to plain tools/call.
        if fallback_result is not None:
            if fallback_result.isError:
                parsed = parser(fallback_result)
                text = (
                    "\n".join(c.text for c in parsed if c.type == "text" and c.text)
                    if isinstance(parsed, list)
                    else str(parsed)
                )
                raise ToolExecutionException(text or str(parsed))
            return parser(fallback_result)

        if task_id is None:
            raise ToolExecutionException(f"MCP server did not return a task_id or fallback result for '{tool_name}'.")

        # Track to completion: poll until terminal, then fetch payload. Never re-issue
        # tools/call past this point; reconnect-and-retry only against the same task_id.
        opts = self._effective_task_options()
        max_wait_s = opts.max_task_wait.total_seconds() if opts.max_task_wait is not None else None

        async def _await_task_completion() -> str | list[Content]:
            terminal = await self._poll_task_until_terminal(task_id)
            return await self._handle_terminal_task(tool_name, task_id, terminal, parser)

        try:
            if max_wait_s is not None:
                try:
                    result = await self._await_with_deadline(_await_task_completion(), max_wait_s)
                    return cast("str | list[Content]", result)
                except _MCPDeadlineExpired as ex:
                    self._spawn_best_effort_cancel(task_id)
                    raise ToolExecutionException(
                        f"MCP task '{task_id}' exceeded max_task_wait of {max_wait_s}s.",
                        inner_exception=ex,
                    ) from ex
            else:
                return await _await_task_completion()
        except asyncio.CancelledError:
            if opts.cancel_remote_task_on_local_cancellation:
                self._spawn_best_effort_cancel(task_id)
            raise
        except _MCPTaskAbandoned:
            # Pre-terminal abandonment (hard poll error, malformed get, second
            # disconnect, reconnect failure): cancel + re-raise as plain
            # ToolExecutionException to the function-calling loop.
            self._spawn_best_effort_cancel(task_id)
            raise
        # Plain ToolExecutionException from terminal failures (failed/cancelled/
        # input_required, completed+isError, malformed result post-completion)
        # propagates without cancel — server is already done.

    async def _call_tool_as_task_create(
        self, tool_name: str, arguments: dict[str, Any], meta: dict[str, Any] | None
    ) -> tuple[str | None, types.CallToolResult | None]:
        """Send the augmented tools/call.

        Returns ``(task_id, None)`` when the server created a task,
        ``(None, CallToolResult)`` when it returned a non-task result, falling back
        to plain ``tools/call`` if the server rejects the ``task`` field outright.
        """
        from mcp import types
        from mcp.shared.exceptions import McpError
        from pydantic import ValidationError

        opts = self._effective_task_options()
        ttl_ms: int | None = None
        if opts.default_ttl is not None:
            ttl_ms = int(opts.default_ttl.total_seconds() * 1000)
        # Always send TaskMetadata to mark the call as task-augmented; ttl may be omitted.
        task_metadata = types.TaskMetadata(ttl=ttl_ms)

        request_meta = types.RequestParams.Meta(**meta) if meta else None
        params = types.CallToolRequestParams(
            name=tool_name,
            arguments=arguments,
            task=task_metadata,
            _meta=request_meta,
        )
        request = types.ClientRequest(types.CallToolRequest(params=params))

        # Use the lenient Result type so we can extract the task_id even when
        # the strict CreateTaskResult schema rejects the payload (the MCP Python
        # SDK requires Task.ttl, but servers may legitimately omit it).
        try:
            lenient = await self.session.send_request(  # type: ignore[union-attr]
                request,
                types.Result,
            )
        except McpError as ex:
            if ex.error.code not in (types.METHOD_NOT_FOUND, types.INVALID_PARAMS):
                raise
            logger.debug(
                "Server rejected augmented tools/call for '%s' (code=%s); falling back.",
                tool_name,
                ex.error.code,
            )
            fallback = await self.session.call_tool(tool_name, arguments=arguments, meta=meta)  # type: ignore[union-attr]
            return None, fallback

        # Inspect the raw payload: a CreateTaskResult carries `task.taskId`;
        # a legacy CallToolResult carries `content` and/or `isError`.
        raw: dict[str, Any] = lenient.model_dump(by_alias=True, exclude_none=True)
        raw.pop("_meta", None)

        task_field = raw.get("task")
        if isinstance(task_field, dict):
            task_id_val = cast(dict[str, Any], task_field).get("taskId")
            if isinstance(task_id_val, str):
                return task_id_val, None

        try:
            legacy = types.CallToolResult.model_validate(raw)
        except ValidationError as ex:
            # Augmented call succeeded server-side; re-issuing a plain tools/call
            # could double-execute a side-effecting tool.
            raise ToolExecutionException(
                f"MCP server returned an unparseable response to augmented tools/call "
                f"for '{tool_name}'; cannot safely retry (server may have started the operation).",
                inner_exception=ex,
            ) from ex

        return None, legacy

    async def _poll_task_until_terminal(self, task_id: str) -> types.GetTaskResult:
        """Poll ``tasks/get`` until the task reaches a terminal status."""
        import httpx
        from mcp import types
        from mcp.shared.exceptions import McpError

        # SDK raises McpError(code=httpx.REQUEST_TIMEOUT=408) on session read timeout.
        transient_codes: frozenset[int] = frozenset({int(httpx.codes.REQUEST_TIMEOUT)})

        while True:
            request = types.ClientRequest(types.GetTaskRequest(params=types.GetTaskRequestParams(taskId=task_id)))
            try:
                # GetTaskResult.ttl is required-but-Optional in the SDK; coerce below.
                lenient = await self._send_with_one_reconnect(
                    request, types.Result, operation="tasks/get", task_id=task_id
                )
            except McpError as ex:
                if ex.error.code in transient_codes:
                    logger.debug("Transient %s on tasks/get for '%s'; will retry.", ex.error.code, task_id)
                    await asyncio.sleep(_MCP_TASK_MIN_POLL_INTERVAL.total_seconds())
                    continue
                # Hard server error mid-poll: task may still be running.
                raise _MCPTaskAbandoned(ex.error.message, inner_exception=ex) from ex

            try:
                snapshot = self._coerce_get_task_result(lenient, task_id)
            except ToolExecutionException as ex:
                # Malformed tasks/get response; task may still be running.
                raise _MCPTaskAbandoned(str(ex), inner_exception=ex) from ex

            if snapshot.status in _MCP_TASK_TERMINAL_STATUSES:
                return snapshot

            await asyncio.sleep(self._compute_poll_delay(snapshot.pollInterval).total_seconds())

    @staticmethod
    def _coerce_get_task_result(lenient: types.Result, task_id: str) -> types.GetTaskResult:
        """Coerce a lenient Result into GetTaskResult, defaulting ``ttl`` when absent."""
        from mcp import types

        raw = lenient.model_dump(by_alias=True, exclude_none=True)
        raw.pop("_meta", None)
        raw.setdefault("ttl", None)
        try:
            return types.GetTaskResult.model_validate(raw)
        except Exception as ex:
            raise ToolExecutionException(
                f"MCP server returned a malformed tasks/get response for task '{task_id}'.",
                inner_exception=ex,
            ) from ex

    @staticmethod
    def _compute_poll_delay(server_interval_ms: int | None) -> timedelta:
        """Clamp the server-suggested poll interval to ``[min, max]``."""
        if server_interval_ms is None or server_interval_ms <= 0:
            return _MCP_TASK_MIN_POLL_INTERVAL
        suggested = timedelta(milliseconds=server_interval_ms)
        if suggested < _MCP_TASK_MIN_POLL_INTERVAL:
            return _MCP_TASK_MIN_POLL_INTERVAL
        if suggested > _MCP_TASK_MAX_POLL_INTERVAL:
            return _MCP_TASK_MAX_POLL_INTERVAL
        return suggested

    async def _handle_terminal_task(
        self,
        tool_name: str,
        task_id: str,
        snapshot: types.GetTaskResult,
        parser: Callable[[types.CallToolResult], str | list[Content]],
    ) -> str | list[Content]:
        """Map a terminal task snapshot to either a parsed result or an exception."""
        status = snapshot.status
        if status == "completed":
            payload = await self._fetch_task_result(task_id)
            if payload.isError:
                parsed = parser(payload)
                text = (
                    "\n".join(c.text for c in parsed if c.type == "text" and c.text)
                    if isinstance(parsed, list)
                    else str(parsed)
                )
                raise ToolExecutionException(text or str(parsed))
            return parser(payload)

        # Non-completed terminal statuses surface as ToolExecutionException so the
        # function-calling loop sees a normal failure for tool_name.
        message = snapshot.statusMessage or f"MCP task ended with status '{status}'."
        if status == "input_required":
            # Spec-non-terminal; treated as terminal here because the framework does
            # not implement the interactive input flow.
            message = snapshot.statusMessage or "MCP task requires additional input and cannot continue."
        raise ToolExecutionException(f"Tool '{tool_name}' task {status}: {message}")

    async def _fetch_task_result(self, task_id: str) -> types.CallToolResult:
        """Send ``tasks/result`` and reinterpret the open-typed payload as a CallToolResult."""
        from mcp import types
        from mcp.shared.exceptions import McpError
        from pydantic import ValidationError

        request = types.ClientRequest(
            types.GetTaskPayloadRequest(params=types.GetTaskPayloadRequestParams(taskId=task_id))
        )
        # Connection-loss retry only via the helper; no transient-code retry — server
        # has already completed the task, so a slow payload fetch is anomalous.
        try:
            payload = await self._send_with_one_reconnect(
                request, types.GetTaskPayloadResult, operation="tasks/result", task_id=task_id
            )
        except McpError as ex:
            # Server reported completed; a hard fetch error is a plain failure (no cancel).
            raise ToolExecutionException(ex.error.message, inner_exception=ex) from ex

        # GetTaskPayloadResult carries the tool result via extra fields; reinterpret as CallToolResult.
        payload_dict = payload.model_dump(by_alias=True, exclude_none=True)
        payload_dict.pop("_meta", None)
        try:
            return types.CallToolResult.model_validate(payload_dict)
        except ValidationError as ex:
            # Server reported completed; malformed payload is a plain failure (no cancel needed).
            raise ToolExecutionException(
                f"MCP task '{task_id}' result payload could not be parsed as a CallToolResult.",
                inner_exception=ex,
            ) from ex

    async def _send_with_one_reconnect(
        self,
        request: types.ClientRequest,
        result_type: type[Any],
        *,
        operation: str,
        task_id: str,
    ) -> Any:
        """Send ``request`` with one reconnect-and-retry on connection loss.

        After a second loss (or reconnect failure), raise ``_MCPTaskAbandoned``.
        Non-connection errors propagate unchanged.
        """
        from anyio import ClosedResourceError
        from mcp.shared.exceptions import McpError

        for attempt in range(_MCP_RECONNECT_ATTEMPTS):
            try:
                return await self.session.send_request(request, result_type)  # type: ignore[union-attr]
            except (ClosedResourceError, McpError) as ex:
                if not self._is_connection_lost(ex):
                    raise
                if attempt < _MCP_RECONNECT_ATTEMPTS - 1:
                    logger.info("MCP connection lost during %s; reconnecting (task_id=%s).", operation, task_id)
                    try:
                        await self.connect(reset=True)
                    except Exception as reconn_ex:
                        # Reconnect failure: task may still be running.
                        raise _MCPTaskAbandoned(
                            "Failed to reconnect to MCP server.", inner_exception=reconn_ex
                        ) from reconn_ex
                    continue
                # Final attempt also lost the connection: task may still be running.
                raise _MCPTaskAbandoned(
                    f"MCP connection lost; task state unknown (task_id={task_id}).",
                    inner_exception=ex,
                ) from ex
        raise AssertionError(f"unreachable: {operation} for {task_id}")  # pragma: no cover

    @staticmethod
    async def _await_with_deadline(coro: Coroutine[Any, Any, Any], timeout_s: float) -> Any:
        """Await ``coro`` with a deadline; raise ``_MCPDeadlineExpired`` only on deadline.

        Unlike ``asyncio.wait_for``, an ``asyncio.TimeoutError`` raised by ``coro``
        itself propagates unchanged so callers can distinguish their own deadline
        from a stray inner timeout.
        """
        inner = asyncio.ensure_future(coro)
        try:
            done, _pending = await asyncio.wait({inner}, timeout=timeout_s)
        except BaseException:
            # Outer caller cancelled (or another exception): cancel inner + drain.
            inner.cancel()
            with contextlib.suppress(BaseException):
                await inner
            raise
        if inner in done:
            return inner.result()
        # Deadline fired before inner finished.
        inner.cancel()
        with contextlib.suppress(BaseException):
            await inner
        raise _MCPDeadlineExpired

    def _spawn_best_effort_cancel(self, task_id: str) -> None:
        """Fire-and-forget ``tasks/cancel`` so local cancellation propagates server-side."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        cancel_task = loop.create_task(self._try_cancel_task(task_id))
        # Reuse pending-reload bookkeeping so close-on-owner waits/cancels these too.
        self._pending_reload_tasks.add(cancel_task)
        cancel_task.add_done_callback(self._pending_reload_tasks.discard)

    async def _try_cancel_task(self, task_id: str) -> None:
        """Send ``tasks/cancel``; bounded by ``_MCP_TASK_CANCEL_TIMEOUT``.

        Failures log at warning so unattributed orphan tasks are debuggable.
        """
        from mcp import types

        request = types.ClientRequest(types.CancelTaskRequest(params=types.CancelTaskRequestParams(taskId=task_id)))
        try:
            await asyncio.wait_for(
                self.session.send_request(request, types.CancelTaskResult),  # type: ignore[union-attr]
                timeout=_MCP_TASK_CANCEL_TIMEOUT.total_seconds(),
            )
        except asyncio.CancelledError:
            raise
        except asyncio.TimeoutError:
            logger.warning(
                "Best-effort tasks/cancel for '%s' timed out after %.1fs; remote task may still be running.",
                task_id,
                _MCP_TASK_CANCEL_TIMEOUT.total_seconds(),
            )
        except Exception:
            logger.warning(
                "Best-effort tasks/cancel for '%s' failed; remote task may still be running.",
                task_id,
                exc_info=True,
            )

    @staticmethod
    def _is_connection_lost(ex: BaseException) -> bool:
        """Return True if *ex* indicates the MCP transport was torn down."""
        from anyio import ClosedResourceError
        from mcp.shared.exceptions import McpError

        if isinstance(ex, ClosedResourceError):
            return True
        if isinstance(ex, McpError):
            return "session terminated" in ex.error.message.lower()
        return False

    async def get_prompt(self, prompt_name: str, **kwargs: Any) -> str:
        """Call a prompt with the given arguments.

        Args:
            prompt_name: The name of the prompt to retrieve.

        Keyword Args:
            kwargs: Arguments to pass to the prompt.

        Returns:
            A string representation of the prompt result — either plain text or serialized JSON.

        Raises:
            ToolExecutionException: If the MCP server is not connected, prompts are not loaded,
                or the prompt call fails.
        """
        from anyio import ClosedResourceError
        from mcp.shared.exceptions import McpError

        if not self.load_prompts_flag:
            raise ToolExecutionException(
                "Prompts are not loaded for this server, please set load_prompts=True in the constructor."
            )

        parser = self.parse_prompt_results or self._parse_prompt_result_from_mcp
        mcp_span_attrs = self._mcp_base_span_attributes()
        mcp_span_attrs.update({OtelAttr.PROMPT_NAME: prompt_name})

        with create_mcp_client_span("prompts/get", target=prompt_name, attributes=mcp_span_attrs) as span:
            for attempt in range(2):
                try:
                    prompt_result = await self.session.get_prompt(prompt_name, arguments=kwargs)  # type: ignore
                    return parser(prompt_result)
                except ClosedResourceError as cl_ex:
                    if attempt == 0:
                        # First attempt failed, try reconnecting
                        logger.info("MCP connection closed unexpectedly. Reconnecting...")
                        try:
                            await self.connect(reset=True)
                            continue  # Retry the operation
                        except Exception as reconn_ex:
                            raise ToolExecutionException(
                                "Failed to reconnect to MCP server.",
                                inner_exception=reconn_ex,
                            ) from reconn_ex
                    else:
                        # Second attempt also failed, give up
                        logger.error(f"MCP connection closed unexpectedly after reconnection: {cl_ex}")
                        set_mcp_span_error(span, type(cl_ex).__name__, str(cl_ex))
                        raise ToolExecutionException(
                            f"Failed to call prompt '{prompt_name}' - connection lost.",
                            inner_exception=cl_ex,
                        ) from cl_ex
                except McpError as mcp_exc:
                    error_message = mcp_exc.error.message
                    set_mcp_span_error(span, type(mcp_exc).__name__, error_message)
                    raise ToolExecutionException(error_message, inner_exception=mcp_exc) from mcp_exc
                except Exception as ex:
                    set_mcp_span_error(span, type(ex).__name__, str(ex))
                    raise ToolExecutionException(f"Failed to call prompt '{prompt_name}'.", inner_exception=ex) from ex
            raise ToolExecutionException(f"Failed to get prompt '{prompt_name}' after retries.")

    async def __aenter__(self) -> Self:
        """Enter the async context manager.

        Connects to the MCP server automatically.

        Returns:
            The MCPTool instance.

        Raises:
            ToolException: If connection fails.
            ToolExecutionException: If context manager setup fails.
        """
        try:
            await self.connect()
            return self
        except ToolException:
            raise
        except Exception as ex:
            await self.close()
            raise ToolExecutionException("Failed to enter context manager.", inner_exception=ex) from ex

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: Any,
    ) -> None:
        """Exit the async context manager.

        Closes the connection and cleans up resources.

        Args:
            exc_type: The exception type if an exception was raised, None otherwise.
            exc_value: The exception value if an exception was raised, None otherwise.
            traceback: The exception traceback if an exception was raised, None otherwise.
        """
        await self.close()


# region: MCP Plugin Implementations


class MCPStdioTool(MCPTool):
    """MCP tool for connecting to stdio-based MCP servers.

    This class connects to MCP servers that communicate via standard input/output,
    typically used for local processes.

    Examples:
        .. code-block:: python

            from agent_framework import MCPStdioTool, Agent

            # Create an MCP stdio tool
            mcp_tool = MCPStdioTool(
                name="filesystem",
                command="npx",
                args=["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
                description="File system operations",
            )

            # Use with a chat agent
            async with mcp_tool:
                agent = Agent(client=client, name="assistant", tools=mcp_tool)
                response = await agent.run("List files in the directory")
    """

    def __init__(
        self,
        name: str,
        command: str,
        *,
        tool_name_prefix: str | None = None,
        load_tools: bool = True,
        parse_tool_results: Callable[[types.CallToolResult], str | list[Content]] | None = None,
        load_prompts: bool = True,
        parse_prompt_results: Callable[[types.GetPromptResult], str] | None = None,
        request_timeout: int | None = None,
        session: ClientSession | None = None,
        description: str | None = None,
        approval_mode: (Literal["always_require", "never_require"] | MCPSpecificApproval | None) = None,
        allowed_tools: Collection[str] | None = None,
        use_progressive_disclosure: bool = False,
        always_load: Collection[str] | None = None,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
        encoding: str | None = None,
        client: SupportsChatGetResponse | None = None,
        sampling_approval_callback: SamplingApprovalCallback | None = None,
        sampling_max_tokens: int | None = _DEFAULT_SAMPLING_MAX_TOKENS,
        sampling_max_requests: int | None = _DEFAULT_SAMPLING_MAX_REQUESTS,
        additional_properties: dict[str, Any] | None = None,
        task_options: MCPTaskOptions | None = None,
        additional_tool_argument_names: Sequence[str] | Mapping[str, Sequence[str]] | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize the MCP stdio tool.

        Note:
            The arguments are used to create a StdioServerParameters object,
            which is then used to create a stdio client. See ``mcp.client.stdio.stdio_client``
            and ``mcp.client.stdio.stdio_server_parameters`` for more details.

        Args:
            name: The name of the tool.
            command: The command to run the MCP server.

        Keyword Args:
            tool_name_prefix: Optional prefix to prepend to exposed MCP function names.
            load_tools: Whether to load tools from the MCP server.
            parse_tool_results: An optional callable with signature
                ``Callable[[types.CallToolResult], str]`` that overrides the default result
                parsing. When ``None`` (the default), the built-in parser converts MCP types
                directly to a string. If you need per-function result parsing, access the
                ``.functions`` list after connecting and set ``result_parser`` on individual
                ``FunctionTool`` instances.
            load_prompts: Whether to load prompts from the MCP server.
            parse_prompt_results: An optional callable with signature
                ``Callable[[types.GetPromptResult], str]`` that overrides the default prompt
                result parsing. When ``None`` (the default), the built-in parser converts
                MCP prompt results to a string. If you need per-function result parsing,
                access the ``.functions`` list after connecting and set ``result_parser`` on
                individual ``FunctionTool`` instances.
            request_timeout: The default timeout in seconds for all requests.
            session: The session to use for the MCP connection.
            description: The description of the tool.
            approval_mode: The approval mode for the tool. This can be:
                - "always_require": The tool always requires approval before use.
                - "never_require": The tool never requires approval before use.
                - A dict with keys `always_require_approval` or `never_require_approval`,
                  followed by a sequence of strings with the names of the relevant tools.
                A tool should not be listed in both, if so, it will require approval.
            allowed_tools: Optional allow-list of MCP tool names to expose as functions.
                ``None`` (the default) exposes every tool advertised by the MCP server.
                A non-empty collection exposes only the tools whose names appear in it.
                An empty collection (``[]``) exposes no tools — if you simply want to
                disable tool execution, prefer ``load_tools=False`` instead. ``[]`` is
                useful as a runtime guard or when you want to load tool metadata for
                inspection without exposing the tools for invocation.
            use_progressive_disclosure: When ``True``, expose discovery and loader tools plus
                ``always_load`` tools initially, and let the model load and unload other allowed MCP tools on demand.
            always_load: MCP tool names to keep visible from the start when progressive disclosure
                is enabled. Names use the same safe matching rules as ``allowed_tools``; unmatched
                entries are ignored.
            additional_properties: Additional properties.
            args: The arguments to pass to the command.
            env: The environment variables to set for the command.
            encoding: The encoding to use for the command output.
            client: The chat client to use for sampling.
            sampling_approval_callback: Optional gate run before each server-initiated
                ``sampling/createMessage`` request reaches ``client``. Receives the raw
                ``CreateMessageRequestParams`` (sync or async); a truthy return approves the
                request, a falsy return denies it. When ``None`` (the default) every sampling
                request is **denied**, since MCP servers are untrusted (confused-deputy risk).
                Pass ``lambda params: True`` to auto-approve as an explicit opt-in.
            sampling_max_tokens: Cap applied to an approved request's ``maxTokens``
                (``min(requested, cap)``); ``None`` disables it.
            sampling_max_requests: Per-session cap on the number of sampling requests; further
                requests are rejected. Resets on reconnect. ``None`` disables it.
            task_options: Options for tools that advertise
                ``execution.taskSupport == "required"``. See :class:`MCPTaskOptions`.
            additional_tool_argument_names: Extra argument names to forward to the MCP server in
                addition to each tool's declared parameters (from its ``inputSchema.properties``).
                By default only declared parameters are sent; framework runtime kwargs injected
                through the function-invocation pipeline are stripped. Use this to opt specific
                keys back in. Accepts either a ``Sequence[str]`` applied to every tool, or a
                ``Mapping[str, Sequence[str]]`` keyed by remote tool name where the reserved key
                ``"*"`` applies to every tool. This is configured only here in user code; there is
                no per-call override, so a model-issued tool call cannot change which names pass
                through. To use a server that accepts ``additionalProperties: true``, list the
                extra names here and then either (1) manually extend that tool's ``inputSchema``
                (via the ``.functions`` list after connecting) so the model is prompted to supply
                them, or (2) supply the values yourself through ``function_invocation_kwargs``. If
                a name is supplied via both the model and ``function_invocation_kwargs``, the
                model-supplied value wins.
            kwargs: Any extra arguments to pass to the stdio client.
        """
        super().__init__(
            name=name,
            description=description,
            approval_mode=approval_mode,
            allowed_tools=allowed_tools,
            use_progressive_disclosure=use_progressive_disclosure,
            always_load=always_load,
            tool_name_prefix=tool_name_prefix,
            additional_properties=additional_properties,
            session=session,
            client=client,
            load_tools=load_tools,
            parse_tool_results=parse_tool_results,
            load_prompts=load_prompts,
            parse_prompt_results=parse_prompt_results,
            request_timeout=request_timeout,
            task_options=task_options,
            additional_tool_argument_names=additional_tool_argument_names,
            sampling_approval_callback=sampling_approval_callback,
            sampling_max_tokens=sampling_max_tokens,
            sampling_max_requests=sampling_max_requests,
        )
        self.command = command
        self.args = args or []
        self.env = env
        self.encoding = encoding
        self._client_kwargs = kwargs

    def _mcp_base_span_attributes(self) -> dict[str, Any]:
        attrs = super()._mcp_base_span_attributes()
        attrs[OtelAttr.NETWORK_TRANSPORT] = "pipe"
        return attrs

    def get_mcp_client(self) -> _AsyncGeneratorContextManager[Any, None]:
        """Get an MCP stdio client.

        Returns:
            An async context manager for the stdio client transport.
        """
        args: dict[str, Any] = {
            "command": self.command,
            "args": self.args,
            "env": self.env,
        }
        if self.encoding:
            args["encoding"] = self.encoding
        if self._client_kwargs:
            args.update(self._client_kwargs)
        try:
            from mcp.client.stdio import StdioServerParameters, stdio_client
        except ModuleNotFoundError as ex:
            raise ModuleNotFoundError("`mcp` is required to use `MCPStdioTool`. Please install `mcp`.") from ex

        return stdio_client(server=StdioServerParameters(**args))


class MCPStreamableHTTPTool(MCPTool):
    """MCP tool for connecting to HTTP-based MCP servers.

    This class connects to MCP servers that communicate via streamable HTTP/SSE.

    Examples:
        .. code-block:: python

            from agent_framework import MCPStreamableHTTPTool, Agent

            # Create an MCP HTTP tool
            mcp_tool = MCPStreamableHTTPTool(
                name="web-api",
                url="https://api.example.com/mcp",
                description="Web API operations",
            )

            # Use with a chat agent
            async with mcp_tool:
                agent = Agent(client=client, name="assistant", tools=mcp_tool)
                response = await agent.run("Fetch data from the API")
    """

    def __init__(
        self,
        name: str,
        url: str,
        *,
        tool_name_prefix: str | None = None,
        load_tools: bool = True,
        parse_tool_results: Callable[[types.CallToolResult], str | list[Content]] | None = None,
        load_prompts: bool = True,
        parse_prompt_results: Callable[[types.GetPromptResult], str] | None = None,
        request_timeout: int | None = None,
        session: ClientSession | None = None,
        description: str | None = None,
        approval_mode: (Literal["always_require", "never_require"] | MCPSpecificApproval | None) = None,
        allowed_tools: Collection[str] | None = None,
        use_progressive_disclosure: bool = False,
        always_load: Collection[str] | None = None,
        terminate_on_close: bool | None = None,
        client: SupportsChatGetResponse | None = None,
        sampling_approval_callback: SamplingApprovalCallback | None = None,
        sampling_max_tokens: int | None = _DEFAULT_SAMPLING_MAX_TOKENS,
        sampling_max_requests: int | None = _DEFAULT_SAMPLING_MAX_REQUESTS,
        additional_properties: dict[str, Any] | None = None,
        http_client: AsyncClient | None = None,
        header_provider: Callable[[dict[str, Any]], dict[str, str]] | None = None,
        task_options: MCPTaskOptions | None = None,
        additional_tool_argument_names: Sequence[str] | Mapping[str, Sequence[str]] | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize the MCP streamable HTTP tool.

        Note:
            The arguments are used to create a streamable HTTP client using the
            new ``mcp.client.streamable_http.streamable_http_client`` API.
            If an asyncClient is provided via ``http_client``, it will be used directly.
            Otherwise, the ``streamable_http_client`` API will create and manage a default client.

        Args:
            name: The name of the tool.
            url: The URL of the MCP server.

        Keyword Args:
            tool_name_prefix: Optional prefix to prepend to exposed MCP function names.
            load_tools: Whether to load tools from the MCP server.
            parse_tool_results: An optional callable with signature
                ``Callable[[types.CallToolResult], str]`` that overrides the default result
                parsing. When ``None`` (the default), the built-in parser converts MCP types
                directly to a string. If you need per-function result parsing, access the
                ``.functions`` list after connecting and set ``result_parser`` on individual
                ``FunctionTool`` instances.
            load_prompts: Whether to load prompts from the MCP server.
            parse_prompt_results: An optional callable with signature
                ``Callable[[types.GetPromptResult], str]`` that overrides the default prompt
                result parsing. When ``None`` (the default), the built-in parser converts
                MCP prompt results to a string. If you need per-function result parsing,
                access the ``.functions`` list after connecting and set ``result_parser`` on
                individual ``FunctionTool`` instances.
            request_timeout: The default timeout in seconds for all requests.
            session: The session to use for the MCP connection.
            description: The description of the tool.
            approval_mode: The approval mode for the tool. This can be:
                - "always_require": The tool always requires approval before use.
                - "never_require": The tool never requires approval before use.
                - A dict with keys `always_require_approval` or `never_require_approval`,
                  followed by a sequence of strings with the names of the relevant tools.
                A tool should not be listed in both, if so, it will require approval.
            allowed_tools: Optional allow-list of MCP tool names to expose as functions.
                ``None`` (the default) exposes every tool advertised by the MCP server.
                A non-empty collection exposes only the tools whose names appear in it.
                An empty collection (``[]``) exposes no tools — if you simply want to
                disable tool execution, prefer ``load_tools=False`` instead. ``[]`` is
                useful as a runtime guard or when you want to load tool metadata for
                inspection without exposing the tools for invocation.
            use_progressive_disclosure: When ``True``, expose discovery and loader tools plus
                ``always_load`` tools initially, and let the model load and unload other allowed MCP tools on demand.
            always_load: MCP tool names to keep visible from the start when progressive disclosure
                is enabled. Names use the same safe matching rules as ``allowed_tools``; unmatched
                entries are ignored.
            additional_properties: Additional properties.
            terminate_on_close: Close the transport when the MCP client is terminated.
            client: The chat client to use for sampling.
            sampling_approval_callback: Optional gate run before each server-initiated
                ``sampling/createMessage`` request reaches ``client``. Receives the raw
                ``CreateMessageRequestParams`` (sync or async); a truthy return approves the
                request, a falsy return denies it. When ``None`` (the default) every sampling
                request is **denied**, since MCP servers are untrusted (confused-deputy risk).
                Pass ``lambda params: True`` to auto-approve as an explicit opt-in.
            sampling_max_tokens: Cap applied to an approved request's ``maxTokens``
                (``min(requested, cap)``); ``None`` disables it.
            sampling_max_requests: Per-session cap on the number of sampling requests; further
                requests are rejected. Resets on reconnect. ``None`` disables it.
            http_client: Optional asyncClient to use. If not provided, the
                ``streamable_http_client`` API will create and manage a default client.
                To configure headers, timeouts, or other HTTP client settings, create
                and pass your own ``asyncClient`` instance.
                Security: when you attach sensitive headers (e.g. authentication tokens)
                via a custom ``http_client``, you are responsible for enforcing the same
                origin-scoped header policy that the built-in ``header_provider`` hook
                applies. The framework only injects ``header_provider`` headers on requests
                whose origin (scheme, host, port) matches the configured ``url``, so tokens
                are not leaked to third-party origins on cross-origin redirects. A custom
                client that sets headers unconditionally (e.g. via ``AsyncClient(headers=...)``
                or ``follow_redirects=True`` without an origin check) can leak those headers
                to other origins; scope them to the target origin yourself.
            header_provider: Optional callable that receives the runtime keyword arguments
                (from ``FunctionInvocationContext.kwargs``) and returns a ``dict[str, str]``
                of HTTP headers to inject into every outbound request to the MCP server.
                Use this to forward per-request context (e.g. authentication tokens set in
                agent middleware) without creating a separate ``httpx.AsyncClient``.
                The framework attaches these headers only to requests whose origin (scheme,
                host, port) matches the configured ``url``, so they are not leaked to other
                origins on cross-origin redirects. If you instead supply sensitive headers
                through a custom ``http_client``, you must enforce this same origin-scoped
                policy yourself.
            task_options: Options for tools that advertise
                ``execution.taskSupport == "required"``. See :class:`MCPTaskOptions`.
            additional_tool_argument_names: Extra argument names to forward to the MCP server in
                addition to each tool's declared parameters (from its ``inputSchema.properties``).
                By default only declared parameters are sent; framework runtime kwargs injected
                through the function-invocation pipeline are stripped. Use this to opt specific
                keys back in. Accepts either a ``Sequence[str]`` applied to every tool, or a
                ``Mapping[str, Sequence[str]]`` keyed by remote tool name where the reserved key
                ``"*"`` applies to every tool. This is configured only here in user code; there is
                no per-call override, so a model-issued tool call cannot change which names pass
                through. To use a server that accepts ``additionalProperties: true``, list the
                extra names here and then either (1) manually extend that tool's ``inputSchema``
                (via the ``.functions`` list after connecting) so the model is prompted to supply
                them, or (2) supply the values yourself through ``function_invocation_kwargs``. If
                a name is supplied via both the model and ``function_invocation_kwargs``, the
                model-supplied value wins.
            kwargs: Additional keyword arguments (accepted for backward compatibility but not used).
        """
        super().__init__(
            name=name,
            description=description,
            approval_mode=approval_mode,
            allowed_tools=allowed_tools,
            use_progressive_disclosure=use_progressive_disclosure,
            always_load=always_load,
            tool_name_prefix=tool_name_prefix,
            additional_properties=additional_properties,
            session=session,
            client=client,
            load_tools=load_tools,
            parse_tool_results=parse_tool_results,
            load_prompts=load_prompts,
            parse_prompt_results=parse_prompt_results,
            request_timeout=request_timeout,
            task_options=task_options,
            additional_tool_argument_names=additional_tool_argument_names,
            sampling_approval_callback=sampling_approval_callback,
            sampling_max_tokens=sampling_max_tokens,
            sampling_max_requests=sampling_max_requests,
        )
        self.url = url
        self.terminate_on_close = terminate_on_close
        self._httpx_client: AsyncClient | None = http_client
        self._header_provider = header_provider
        # Headers for the in-flight call_tool invocation. The streamable HTTP transport
        # sends requests from tasks spawned at connect time, whose contexts never observe
        # ContextVar values set later inside call_tool, so the request hook needs this
        # instance-level snapshot as a cross-task fallback. The lock serializes tool calls
        # when a header_provider is set: parallel invocations on the same instance would
        # otherwise overwrite each other's snapshot and attach the wrong per-call headers.
        self._active_call_headers: dict[str, str] | None = None
        self._call_headers_lock = asyncio.Lock()

    def _mcp_base_span_attributes(self) -> dict[str, Any]:
        attrs = super()._mcp_base_span_attributes()
        attrs[OtelAttr.NETWORK_TRANSPORT] = "tcp"
        attrs[OtelAttr.NETWORK_PROTOCOL_NAME] = "http"
        try:
            from httpx import URL

            parsed = URL(self.url)
            if parsed.host:
                attrs[OtelAttr.ADDRESS] = parsed.host
            port = parsed.port
            if port is None:
                port = 443 if parsed.scheme == "https" else 80
            attrs[OtelAttr.PORT] = port
        except Exception:
            logger.debug("Failed to parse URL for MCP span transport attributes", exc_info=True)
        return attrs

    def get_mcp_client(self) -> _AsyncGeneratorContextManager[Any, None]:
        """Get an MCP streamable HTTP client.

        Returns:
            An async context manager for the streamable HTTP client transport.
        """
        from httpx import URL, AsyncClient, Request, Timeout

        http_client = self._httpx_client
        if self._header_provider is not None:
            target_origin = _url_origin(URL(self.url))
            if http_client is None:
                http_client = AsyncClient(
                    follow_redirects=True,
                    timeout=Timeout(MCP_DEFAULT_TIMEOUT, read=MCP_DEFAULT_SSE_READ_TIMEOUT),
                )
                self._httpx_client = http_client

            if not hasattr(self, "_inject_headers_hook"):

                async def _inject_headers(request: Request) -> None:  # ruff:ignore[unused-async]
                    if _url_origin(request.url) != target_origin:
                        return
                    # The transport may send this request from a task whose context was
                    # captured before call_tool set the ContextVar; fall back to the
                    # instance-level snapshot of the active call's headers.
                    headers = _mcp_call_headers.get({}) or self._active_call_headers or {}
                    for key, value in headers.items():
                        request.headers[key] = value

                self._inject_headers_hook = _inject_headers
                http_client.event_hooks["request"].append(self._inject_headers_hook)

        return streamable_http_client(
            url=self.url,
            http_client=http_client,
            terminate_on_close=self.terminate_on_close if self.terminate_on_close is not None else True,
        )

    async def call_tool(self, tool_name: str, **kwargs: Any) -> str | list[Content]:
        """Call a tool, injecting headers from the header_provider if configured.

        When a ``header_provider`` was supplied at construction time, the runtime
        *kwargs* (originating from ``FunctionInvocationContext.kwargs``) are passed
        to the provider.  The returned headers are attached to every HTTP request
        made during this tool call via a request hook on the underlying HTTP client.

        Args:
            tool_name: The name of the tool to call.

        Keyword Args:
            kwargs: Arguments to pass to the tool.

        Returns:
            A list of Content items representing the tool output.
        """
        if self._header_provider is not None:
            headers = self._header_provider(kwargs)
            async with self._call_headers_lock:
                token = _mcp_call_headers.set(headers)
                self._active_call_headers = headers
                try:
                    return await super().call_tool(tool_name, **kwargs)
                finally:
                    self._active_call_headers = None
                    _mcp_call_headers.reset(token)
        return await super().call_tool(tool_name, **kwargs)


class MCPWebsocketTool(MCPTool):
    """MCP tool for connecting to WebSocket-based MCP servers.

    This class connects to MCP servers that communicate via WebSocket.

    Examples:
        .. code-block:: python

            from agent_framework import MCPWebsocketTool, Agent

            # Create an MCP WebSocket tool
            mcp_tool = MCPWebsocketTool(
                name="realtime-service", url="wss://service.example.com/mcp", description="Real-time service operations"
            )

            # Use with a chat agent
            async with mcp_tool:
                agent = Agent(client=client, name="assistant", tools=mcp_tool)
                response = await agent.run("Connect to the real-time service")
    """

    def __init__(
        self,
        name: str,
        url: str,
        *,
        tool_name_prefix: str | None = None,
        load_tools: bool = True,
        parse_tool_results: Callable[[types.CallToolResult], str | list[Content]] | None = None,
        load_prompts: bool = True,
        parse_prompt_results: Callable[[types.GetPromptResult], str] | None = None,
        request_timeout: int | None = None,
        session: ClientSession | None = None,
        description: str | None = None,
        approval_mode: (Literal["always_require", "never_require"] | MCPSpecificApproval | None) = None,
        allowed_tools: Collection[str] | None = None,
        use_progressive_disclosure: bool = False,
        always_load: Collection[str] | None = None,
        client: SupportsChatGetResponse | None = None,
        sampling_approval_callback: SamplingApprovalCallback | None = None,
        sampling_max_tokens: int | None = _DEFAULT_SAMPLING_MAX_TOKENS,
        sampling_max_requests: int | None = _DEFAULT_SAMPLING_MAX_REQUESTS,
        additional_properties: dict[str, Any] | None = None,
        task_options: MCPTaskOptions | None = None,
        additional_tool_argument_names: Sequence[str] | Mapping[str, Sequence[str]] | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize the MCP WebSocket tool.

        Note:
            The arguments are used to create a WebSocket client.
            See ``mcp.client.websocket.websocket_client`` for more details.
            Any extra arguments passed to the constructor will be passed to the
            WebSocket client constructor.

        Args:
            name: The name of the tool.
            url: The URL of the MCP server.

        Keyword Args:
            tool_name_prefix: Optional prefix to prepend to exposed MCP function names.
            load_tools: Whether to load tools from the MCP server.
            parse_tool_results: An optional callable with signature
                ``Callable[[types.CallToolResult], str]`` that overrides the default result
                parsing. When ``None`` (the default), the built-in parser converts MCP types
                directly to a string. If you need per-function result parsing, access the
                ``.functions`` list after connecting and set ``result_parser`` on individual
                ``FunctionTool`` instances.
            load_prompts: Whether to load prompts from the MCP server.
            parse_prompt_results: An optional callable with signature
                ``Callable[[types.GetPromptResult], str]`` that overrides the default prompt
                result parsing. When ``None`` (the default), the built-in parser converts
                MCP prompt results to a string. If you need per-function result parsing,
                access the ``.functions`` list after connecting and set ``result_parser`` on
                individual ``FunctionTool`` instances.
            request_timeout: The default timeout in seconds for all requests.
            session: The session to use for the MCP connection.
            description: The description of the tool.
            approval_mode: The approval mode for the tool. This can be:
                - "always_require": The tool always requires approval before use.
                - "never_require": The tool never requires approval before use.
                - A dict with keys `always_require_approval` or `never_require_approval`,
                  followed by a sequence of strings with the names of the relevant tools.
                A tool should not be listed in both, if so, it will require approval.
            allowed_tools: Optional allow-list of MCP tool names to expose as functions.
                ``None`` (the default) exposes every tool advertised by the MCP server.
                A non-empty collection exposes only the tools whose names appear in it.
                An empty collection (``[]``) exposes no tools — if you simply want to
                disable tool execution, prefer ``load_tools=False`` instead. ``[]`` is
                useful as a runtime guard or when you want to load tool metadata for
                inspection without exposing the tools for invocation.
            use_progressive_disclosure: When ``True``, expose discovery and loader tools plus
                ``always_load`` tools initially, and let the model load and unload other allowed MCP tools on demand.
            always_load: MCP tool names to keep visible from the start when progressive disclosure
                is enabled. Names use the same safe matching rules as ``allowed_tools``; unmatched
                entries are ignored.
            additional_properties: Additional properties.
            client: The chat client to use for sampling.
            sampling_approval_callback: Optional gate run before each server-initiated
                ``sampling/createMessage`` request reaches ``client``. Receives the raw
                ``CreateMessageRequestParams`` (sync or async); a truthy return approves the
                request, a falsy return denies it. When ``None`` (the default) every sampling
                request is **denied**, since MCP servers are untrusted (confused-deputy risk).
                Pass ``lambda params: True`` to auto-approve as an explicit opt-in.
            sampling_max_tokens: Cap applied to an approved request's ``maxTokens``
                (``min(requested, cap)``); ``None`` disables it.
            sampling_max_requests: Per-session cap on the number of sampling requests; further
                requests are rejected. Resets on reconnect. ``None`` disables it.
            task_options: Options for tools that advertise
                ``execution.taskSupport == "required"``. See :class:`MCPTaskOptions`.
            additional_tool_argument_names: Extra argument names to forward to the MCP server in
                addition to each tool's declared parameters (from its ``inputSchema.properties``).
                By default only declared parameters are sent; framework runtime kwargs injected
                through the function-invocation pipeline are stripped. Use this to opt specific
                keys back in. Accepts either a ``Sequence[str]`` applied to every tool, or a
                ``Mapping[str, Sequence[str]]`` keyed by remote tool name where the reserved key
                ``"*"`` applies to every tool. This is configured only here in user code; there is
                no per-call override, so a model-issued tool call cannot change which names pass
                through. To use a server that accepts ``additionalProperties: true``, list the
                extra names here and then either (1) manually extend that tool's ``inputSchema``
                (via the ``.functions`` list after connecting) so the model is prompted to supply
                them, or (2) supply the values yourself through ``function_invocation_kwargs``. If
                a name is supplied via both the model and ``function_invocation_kwargs``, the
                model-supplied value wins.
            kwargs: Any extra arguments to pass to the WebSocket client.
        """
        super().__init__(
            name=name,
            description=description,
            approval_mode=approval_mode,
            allowed_tools=allowed_tools,
            use_progressive_disclosure=use_progressive_disclosure,
            always_load=always_load,
            tool_name_prefix=tool_name_prefix,
            additional_properties=additional_properties,
            session=session,
            client=client,
            load_tools=load_tools,
            parse_tool_results=parse_tool_results,
            load_prompts=load_prompts,
            parse_prompt_results=parse_prompt_results,
            request_timeout=request_timeout,
            task_options=task_options,
            additional_tool_argument_names=additional_tool_argument_names,
            sampling_approval_callback=sampling_approval_callback,
            sampling_max_tokens=sampling_max_tokens,
            sampling_max_requests=sampling_max_requests,
        )
        self.url = url
        self._client_kwargs = kwargs

    def _mcp_base_span_attributes(self) -> dict[str, Any]:
        attrs = super()._mcp_base_span_attributes()
        attrs[OtelAttr.NETWORK_TRANSPORT] = "tcp"
        attrs[OtelAttr.NETWORK_PROTOCOL_NAME] = "websocket"
        try:
            from urllib.parse import urlparse

            parsed = urlparse(self.url)
            if parsed.hostname:
                attrs[OtelAttr.ADDRESS] = parsed.hostname
            port = parsed.port
            if port is None:
                port = 443 if parsed.scheme == "wss" else 80
            attrs[OtelAttr.PORT] = port
        except Exception:
            logger.debug("Failed to parse URL for MCP span transport attributes", exc_info=True)
        return attrs

    def get_mcp_client(self) -> _AsyncGeneratorContextManager[Any, None]:
        """Get an MCP WebSocket client.

        Returns:
            An async context manager for the WebSocket client transport.
        """
        try:
            websocket_module = __import__("mcp.client.websocket", fromlist=["websocket_client"])
        except ModuleNotFoundError as ex:
            missing_name = ex.name or "mcp/websocket dependencies"
            if missing_name == "mcp" or missing_name.startswith("mcp."):
                reason = "The `mcp` package is not installed."
            elif missing_name == "websockets" or missing_name.startswith("websockets."):
                reason = "WebSocket transport support is not installed."
            else:
                reason = f"The optional dependency `{missing_name}` is not installed."
            raise ModuleNotFoundError(
                f"`MCPWebsocketTool` requires websocket transport support. {reason} "
                "Please install `mcp[ws]` and update your dependencies."
            ) from ex

        # Support MCP releases from before and after the transport gained its deprecation marker.
        websocket_client = websocket_module.websocket_client
        args: dict[str, Any] = {
            "url": self.url,
        }
        if self._client_kwargs:
            args.update(self._client_kwargs)
        return websocket_client(**args)
