# Copyright (c) Microsoft. All rights reserved.

"""MCP tool handler abstraction for declarative workflows.

Mirrors the .NET ``IMcpToolHandler`` / ``DefaultMcpToolHandler`` pair from
``Microsoft.Agents.AI.Workflows.Declarative.Mcp``. Provides:

- :class:`MCPToolInvocation` — request input data passed from the executor.
- :class:`MCPToolResult` — response data returned to the executor.
- :class:`MCPToolHandler` — :class:`typing.Protocol` callers implement to plug
  in custom transports (e.g. with allowlisting, Foundry connection resolution,
  per-server auth, etc.).
- :class:`DefaultMCPToolHandler` — production-grade default backed by
  :class:`agent_framework.MCPStreamableHTTPTool`.

Security note: :class:`DefaultMCPToolHandler` performs **no** URL filtering or
SSRF protection. Production deployments should supply a custom handler that
enforces an allowlist or DNS-rebinding-resistant policy. This split mirrors the
.NET design.

Prompt-injection note: MCP tool outputs flow back into agent conversations
(via ``conversationId`` and Tool-role messages emitted by the executor) so
they share the same risk surface as ``HttpRequestAction``. Workflow authors
must trust the MCP server they invoke.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar, Protocol, cast, runtime_checkable

import httpx

if TYPE_CHECKING:
    from agent_framework import Content

__all__ = [
    "ClientProvider",
    "DefaultMCPToolHandler",
    "MCPToolHandler",
    "MCPToolInvocation",
    "MCPToolResult",
]

logger = logging.getLogger(__name__)

_DEFAULT_CACHE_MAX_SIZE = 32


@dataclass
class MCPToolInvocation:
    """Description of an MCP tool call to be dispatched by a :class:`MCPToolHandler`.

    Mirrors the input parameters of the .NET ``IMcpToolHandler.InvokeToolAsync``
    method. Field semantics:

    - ``server_url``: Absolute URL of the MCP server. Already evaluated from
      the YAML expression.
    - ``server_label``: Optional human-readable label used for diagnostics
      and as the underlying ``MCPStreamableHTTPTool`` name.
    - ``tool_name``: Name of the tool to invoke on the MCP server.
    - ``arguments``: Tool arguments. Already evaluated; values may be any
      JSON-serialisable Python object (str, int, bool, dict, list, None).
    - ``headers``: Outbound HTTP headers (e.g. authentication). Empty values
      are skipped by the executor before construction.
    - ``connection_name``: Optional Foundry connection name forwarded for
      handlers that resolve auth/credentials by connection. The default
      handler does not consume this field.
    """

    server_url: str
    tool_name: str
    server_label: str | None = None
    arguments: dict[str, Any] = field(default_factory=dict)  # type: ignore[reportUnknownVariableType]
    headers: dict[str, str] = field(default_factory=dict)  # type: ignore[reportUnknownVariableType]
    connection_name: str | None = None


def _empty_outputs() -> list[Any]:
    """Default factory for ``MCPToolResult.outputs``.

    Typed as ``list[Any]`` here to keep the dataclass field's runtime
    factory simple; the public type on :class:`MCPToolResult` is
    ``list[Content]``.
    """
    return []


@dataclass
class MCPToolResult:
    """Response returned by an :class:`MCPToolHandler`.

    Mirrors the .NET ``McpServerToolResultContent`` shape. ``outputs`` is a
    list of :class:`agent_framework.Content` items as parsed by the MCP
    transport (TextContent / DataContent / UriContent / etc.).

    On error, ``is_error`` is ``True``, ``error_message`` carries a human
    readable description, and ``outputs`` typically contains a single
    ``Content.from_text("Error: ...")`` entry for downstream display.
    """

    outputs: list[Content] = field(default_factory=_empty_outputs)
    is_error: bool = False
    error_message: str | None = None


@runtime_checkable
class MCPToolHandler(Protocol):
    """Protocol for MCP tool handlers used by ``InvokeMcpTool``.

    Mirrors :class:`HttpRequestHandler` — declares ONLY the invocation method.
    Lifecycle methods (``aclose`` / ``__aenter__`` / ``__aexit__``) are NOT
    part of the Protocol; concrete implementations may add them as
    appropriate.

    Implementations must be safe to call concurrently from multiple workflow
    runs. Implementations are responsible for any URL allowlisting, SSRF
    guards, retry policies, auth resolution, and other policies the workflow
    author wants applied.
    """

    async def invoke_tool(self, invocation: MCPToolInvocation) -> MCPToolResult:
        """Dispatch ``invocation`` and return the result.

        Args:
            invocation: Description of the MCP tool call to perform.

        Returns:
            The :class:`MCPToolResult` carrying the parsed outputs (or an
            error flag if the tool raised). Implementations SHOULD return a
            result with ``is_error=True`` rather than raising for transport
            or tool-level failures, so the workflow can store the message in
            ``output.result`` (matching .NET ``AssignErrorAsync`` behaviour).
            They MAY raise on unexpected programming errors — these will be
            propagated unchanged by the executor so they fail loudly.
        """
        ...


ClientProvider = Callable[[MCPToolInvocation], Awaitable["httpx.AsyncClient | None"]]


@dataclass
class _CacheEntry:
    """Internal record stored in the LRU cache."""

    tool: Any  # MCPStreamableHTTPTool — typed Any to avoid import at module load
    owned_httpx_client: httpx.AsyncClient | None


class DefaultMCPToolHandler:
    """Default :class:`MCPToolHandler` backed by :class:`agent_framework.MCPStreamableHTTPTool`.

    Without a ``client_provider``, caches one
    :class:`agent_framework.MCPStreamableHTTPTool` instance per
    ``(server_url, server_label, connection_name, headers_hash)`` in a bounded
    LRU. The cache prevents re-establishing an MCP session for every
    invocation while ensuring different header sets (auth tokens) cannot
    share a session — matches the .NET design intent while bounding
    cardinality. ``server_label`` and ``connection_name`` also participate
    in the key to distinguish logical connections.
    Header *names* are lower-cased inside the hash payload only — the
    headers passed on the wire keep the caller's original casing — so two
    YAML actions that spell ``Authorization`` differently still share a
    cache entry.

    Construction modes:

    1. ``DefaultMCPToolHandler()`` — owns its own ``httpx.AsyncClient``
       instances created lazily per cache entry. Closed by :meth:`aclose`.
    2. ``DefaultMCPToolHandler(client_provider=cb)`` — per-invocation client
       lookup (parity with .NET ``httpClientProvider`` callback). The
       callback receives the full :class:`MCPToolInvocation` so it can
       dispatch on ``server_url`` / ``connection_name`` / ``server_label``.
       The callback is invoked for every call, including ``tools/list``.
       Each call creates and closes its own MCP tool/session, even when the
       callback returns ``None`` or the same client object. Returning ``None``
       falls back to an internally-created client, closed with the invocation.
       Caller-supplied clients are never closed by this handler.

       This intentionally trades connection/session reuse for invocation
       isolation. Server session state is not retained across invocations;
       callers needing shared session ownership must implement an explicitly
       scoped custom :class:`MCPToolHandler`.

    .. warning::

       This handler performs **no** URL filtering or SSRF protection. Wrap
       or replace it with a custom handler in production deployments.

    Args:
        client_provider: Optional per-invocation ``httpx.AsyncClient`` provider.
        cache_max_size: Maximum number of cached MCP clients in no-provider mode.
            When exceeded, the least-recently-used entry is evicted and its
            owned client closed. Defaults to ``32``. Does not enable session
            caching when a provider is configured.
    """

    LIST_TOOLS_TOOL_NAME: ClassVar[str] = "tools/list"
    """Reserved ``tool_name`` that maps an :class:`MCPToolHandler` invocation
    to the MCP protocol ``tools/list`` discovery operation.

    The constant matches the underlying MCP method name so a single
    string travels unchanged through host code, YAML, and the protocol
    wire. When this handler receives an invocation with this name it
    pages through ``session.list_tools()`` and returns the catalog as a
    single ``TextContent`` containing JSON of shape
    ``{"tools": [{name, description, inputSchema, outputSchema}, ...]}``.
    Workflows can reference this name from an ``InvokeMcpTool`` declarative
    action to introspect a server's tool surface without an extra round-trip
    from host code.
    """

    def __init__(
        self,
        *,
        client_provider: ClientProvider | None = None,
        cache_max_size: int = _DEFAULT_CACHE_MAX_SIZE,
    ) -> None:
        if cache_max_size <= 0:
            raise ValueError(f"cache_max_size must be positive, got {cache_max_size}")
        self._client_provider = client_provider
        self._cache_max_size = cache_max_size
        self._cache: OrderedDict[tuple[str, str, str, str], _CacheEntry] = OrderedDict()
        # Outer lock guards the cache + in-flight-future map only — never
        # held across network I/O.
        self._cache_lock = asyncio.Lock()
        # Per-key in-flight futures: while one task is connecting, other
        # tasks awaiting the same key will await the same future and share
        # the resulting cache entry.
        self._inflight: dict[tuple[str, str, str, str], asyncio.Future[_CacheEntry]] = {}
        # Completion signals only: provider-backed calls never share entries.
        self._active_invocations: set[asyncio.Future[None]] = set()
        # Keep ancestry so a completed nested call cannot hide an active parent
        # in the context inherited by child tasks, including cleanup tasks.
        self._invocation_context: ContextVar[tuple[asyncio.Future[None], ...]] = ContextVar(
            f"default_mcp_tool_handler_invocations_{id(self)}", default=()
        )
        # Set by ``aclose`` to prevent post-close cache insertions and to
        # reject new ``invoke_tool`` calls. Once set, never cleared.
        self._closed = False

    async def invoke_tool(self, invocation: MCPToolInvocation) -> MCPToolResult:
        """Invoke ``invocation.tool_name`` on an MCP client for the server.

        The reserved name :attr:`LIST_TOOLS_TOOL_NAME` (``"tools/list"``) is
        intercepted client-side: instead of being forwarded as a tool call,
        it is translated to an MCP ``session.list_tools()`` discovery
        operation (paginated automatically) and returned as a single
        ``TextContent`` containing a JSON tool catalog.
        """
        from agent_framework import Content

        # Reserved-name args validation runs before connect: rejecting bad
        # input shouldn't require establishing an MCP session.
        if invocation.tool_name == self.LIST_TOOLS_TOOL_NAME and invocation.arguments:
            message = f"The reserved MCP '{self.LIST_TOOLS_TOOL_NAME}' operation does not accept tool arguments."
            return MCPToolResult(
                outputs=[Content.from_text(f"Error: {message}")],
                is_error=True,
                error_message=message,
            )

        entry: _CacheEntry | None = None
        completion: asyncio.Future[None] | None = None
        context_token: Token[tuple[asyncio.Future[None], ...]] | None = None
        try:
            try:
                if self._client_provider is None:
                    entry = await self._get_or_create_entry(invocation)
                else:
                    async with self._cache_lock:
                        if self._closed:
                            raise RuntimeError("DefaultMCPToolHandler is closed")
                        completion = asyncio.get_running_loop().create_future()
                        self._active_invocations.add(completion)
                    context_token = self._invocation_context.set((*self._invocation_context.get(), completion))
                    entry = await self._create_entry(invocation)
                    if self._closed:
                        raise RuntimeError("DefaultMCPToolHandler is closed")
            except Exception as exc:
                # Connect / cache lookup failures surface as tool errors so the
                # workflow can store them at output.result without crashing.
                logger.warning(
                    "DefaultMCPToolHandler: failed to obtain MCP client for url=%s tool=%s: %s",
                    invocation.server_url,
                    invocation.tool_name,
                    exc,
                )
                message = f"Failed to connect to MCP server: {type(exc).__name__}: {exc}".rstrip(": ")
                return MCPToolResult(
                    outputs=[Content.from_text(f"Error: {message}")],
                    is_error=True,
                    error_message=message,
                )

            return await self._invoke_entry(entry, invocation)
        finally:
            if completion is not None:
                try:
                    if entry is not None:
                        await self._close_invocation_entry(entry)
                finally:
                    if context_token is not None:
                        self._invocation_context.reset(context_token)
                    self._active_invocations.discard(completion)
                    completion.set_result(None)

    async def _invoke_entry(self, entry: _CacheEntry, invocation: MCPToolInvocation) -> MCPToolResult:
        """Dispatch a connected invocation and preserve tool error mapping."""
        from agent_framework import Content
        from agent_framework.exceptions import ToolExecutionException

        try:
            if invocation.tool_name == self.LIST_TOOLS_TOOL_NAME:
                return await self._invoke_list_tools(entry)
            raw = await entry.tool.call_tool(invocation.tool_name, **invocation.arguments)
        except ToolExecutionException as exc:
            logger.info(
                "DefaultMCPToolHandler: tool '%s' on '%s' raised ToolExecutionException",
                invocation.tool_name,
                invocation.server_url,
            )
            message = str(exc) or type(exc).__name__
            return MCPToolResult(
                outputs=[Content.from_text(f"Error: {message}")],
                is_error=True,
                error_message=message,
            )
        except httpx.HTTPError as exc:
            message = f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__
            return MCPToolResult(
                outputs=[Content.from_text(f"Error: {message}")],
                is_error=True,
                error_message=message,
            )
        except Exception as exc:
            # Be defensive about MCP errors that may bubble up without being
            # wrapped in ToolExecutionException by custom parsers.
            try:
                from mcp.shared.exceptions import McpError
            except ImportError:  # pragma: no cover - mcp is a hard dep but stay defensive
                raise
            if isinstance(exc, McpError):
                message = str(exc) or type(exc).__name__
                return MCPToolResult(
                    outputs=[Content.from_text(f"Error: {message}")],
                    is_error=True,
                    error_message=message,
                )
            raise

        # Defensive normalisation: call_tool is typed ``str | list[Content]``.
        # Default parser returns list, but custom parse_tool_results may return str.
        if isinstance(raw, str):
            outputs: list[Content] = [Content.from_text(raw)]
        else:
            outputs = list(raw)
        return MCPToolResult(outputs=outputs)

    @staticmethod
    async def _invoke_list_tools(entry: _CacheEntry) -> MCPToolResult:
        """Handle the reserved :attr:`LIST_TOOLS_TOOL_NAME` invocation.

        Pages through ``session.list_tools()`` (mirroring the pagination loop
        in :meth:`agent_framework.MCPTool.load_tools`) and serialises the
        full catalog as a single ``TextContent`` containing JSON of shape
        ``{"tools": [{name, description, inputSchema, outputSchema}, ...]}``.

        The output shape, property names, and property order are stable so
        downstream PowerFx expressions can rely on the schema. ``indent=2``
        produces human-readable JSON for the conversation log;
        ``allow_nan=False`` guards against producing non-conformant JSON
        ``NaN``/``Infinity`` tokens if a misbehaving server returns such
        values in a schema.
        """
        from agent_framework import Content

        session = getattr(entry.tool, "session", None)
        if session is None:
            message = "MCP session is not connected; cannot list tools."
            return MCPToolResult(
                outputs=[Content.from_text(f"Error: {message}")],
                is_error=True,
                error_message=message,
            )

        # Lazy import keeps ``mcp`` types out of module import time.
        from mcp import types as mcp_types

        collected: list[Any] = []
        params: mcp_types.PaginatedRequestParams | None = None
        while True:
            tool_list = await session.list_tools(params=params)
            collected.extend(tool_list.tools)
            next_cursor = getattr(tool_list, "nextCursor", None)
            if not next_cursor:
                break
            params = mcp_types.PaginatedRequestParams(cursor=next_cursor)

        payload = {
            "tools": [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "inputSchema": tool.inputSchema,
                    "outputSchema": tool.outputSchema,
                }
                for tool in collected
            ],
        }
        return MCPToolResult(outputs=[Content.from_text(json.dumps(payload, indent=2, allow_nan=False))])

    async def aclose(self) -> None:
        """Close cached clients and wait for provider-backed invocations to clean up.

        Caller-supplied :class:`httpx.AsyncClient` instances (returned by the
        ``client_provider`` callback) are NOT closed.

        Provider-backed calls already executing may finish; pending connections
        are rejected after connecting and cleaned up by their invocation.
        Concurrent shutdown calls wait for those invocations as well.

        Idempotent. In no-provider mode, a second call returns immediately.
        Drains any in-flight ``_create_entry`` tasks before returning so their resources are
        cleaned up; the in-flight tasks see ``self._closed`` in phase 3 of
        :meth:`_get_or_create_entry`, close their own entry, and resolve
        their future with ``RuntimeError("DefaultMCPToolHandler is closed")``.

        Raises:
            RuntimeError: If called from an active provider-backed invocation's
                context, including inherited child tasks and cleanup. Rejected
                before changing handler state to avoid waiting on itself.
        """
        if any(not completion.done() for completion in self._invocation_context.get()):
            raise RuntimeError(
                "DefaultMCPToolHandler.aclose() cannot be called from an active provider-backed invocation"
            )
        async with self._cache_lock:
            if self._closed and self._client_provider is None:
                return
            self._closed = True
            entries = list(self._cache.values())
            self._cache.clear()
            inflight_futures = list(self._inflight.values())
            active_invocations = list(self._active_invocations)

        for completion in active_invocations:
            # Cancelling shutdown must not cancel an invocation's completion signal.
            await asyncio.shield(completion)

        # Wait for in-flight creations to finish their self-cleanup. Each
        # in-flight task self-closes its entry under the closed-flag branch
        # in phase 3 and resolves its future with ``RuntimeError``; we
        # swallow it here because the failure is expected at shutdown.
        for fut in inflight_futures:
            try:
                await fut
            except BaseException:
                logger.debug("DefaultMCPToolHandler: in-flight future raised during aclose", exc_info=True)
                continue

        for entry in entries:
            await self._close_entry(entry)

    async def __aenter__(self) -> DefaultMCPToolHandler:
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        await self.aclose()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _get_or_create_entry(self, invocation: MCPToolInvocation) -> _CacheEntry:
        """Look up (or create) the cached MCP client for this invocation."""
        key = self._cache_key(
            invocation.server_url,
            invocation.server_label,
            invocation.connection_name,
            invocation.headers,
        )

        # Phase 1: check the cache and either claim creation or wait for an
        # already in-flight creation.
        creating = False
        async with self._cache_lock:
            if self._closed:
                raise RuntimeError("DefaultMCPToolHandler is closed")
            existing = self._cache.get(key)
            if existing is not None:
                self._cache.move_to_end(key)
                return existing
            inflight = self._inflight.get(key)
            if inflight is None:
                inflight = asyncio.get_running_loop().create_future()
                self._inflight[key] = inflight
                creating = True

        if not creating:
            return await inflight

        # Phase 2: we own creation. Build the entry outside the lock.
        try:
            entry = await self._create_entry(invocation)
        except BaseException as exc:
            async with self._cache_lock:
                self._inflight.pop(key, None)
            if not inflight.done():
                inflight.set_exception(exc if isinstance(exc, BaseException) else RuntimeError(str(exc)))
            # Mark the exception retrieved to suppress noisy "Future exception
            # was never retrieved" warnings when there are no other awaiters
            # (other awaiters still see the exception through their ``await``).
            inflight.exception()
            raise

        # Phase 3: insert with LRU eviction; resolve the in-flight future.
        # If ``aclose`` ran while we were connecting, ``_closed`` is now
        # True; don't insert into the cache (it has been drained), close
        # the just-built entry, and surface the closed-handler error to
        # all awaiters of the future.
        evicted: _CacheEntry | None = None
        duplicate: _CacheEntry | None = None
        handler_closed = False
        async with self._cache_lock:
            self._inflight.pop(key, None)
            if self._closed:
                handler_closed = True
            else:
                existing = self._cache.get(key)
                if existing is not None:
                    # Another writer beat us; prefer the existing entry and
                    # discard ours after the lock is released.
                    self._cache.move_to_end(key)
                    duplicate = entry
                    entry = existing
                else:
                    self._cache[key] = entry
                    self._cache.move_to_end(key)
                    if len(self._cache) > self._cache_max_size:
                        _evicted_key, evicted = self._cache.popitem(last=False)
                if not inflight.done():
                    inflight.set_result(entry)

        if handler_closed:
            # Close our orphaned entry; resolve the future with a clear
            # error so the caller (and any other awaiters) surface a
            # consistent "handler is closed" failure rather than receiving
            # an entry we are about to close behind their back.
            await self._close_entry(entry)
            err = RuntimeError("DefaultMCPToolHandler is closed")
            if not inflight.done():
                inflight.set_exception(err)
            inflight.exception()
            raise err
        if duplicate is not None:
            await self._close_entry(duplicate)
        if evicted is not None:
            await self._close_entry(evicted)
        return entry

    async def _create_entry(self, invocation: MCPToolInvocation) -> _CacheEntry:
        """Construct (and connect) a fresh MCP client for ``invocation``."""
        from agent_framework import MCPStreamableHTTPTool

        provided_client: httpx.AsyncClient | None = None
        if self._client_provider is not None:
            provided_client = await self._client_provider(invocation)
            if self._closed:
                raise RuntimeError("DefaultMCPToolHandler is closed")
        # Capture headers for this entry so the header_provider closure
        # always returns the same set, regardless of the runtime kwargs.
        captured_headers = dict(invocation.headers)

        def _header_provider(_kwargs: dict[str, Any]) -> dict[str, str]:
            return captured_headers

        tool: Any = MCPStreamableHTTPTool(
            name=invocation.server_label or "McpClient",
            url=invocation.server_url,
            load_prompts=False,
            http_client=provided_client,
            header_provider=_header_provider if captured_headers else None,
        )
        try:
            await tool.connect()
        except BaseException:
            failed_entry = _CacheEntry(
                tool=tool,
                owned_httpx_client=(
                    cast("httpx.AsyncClient | None", getattr(tool, "_httpx_client", None))
                    if provided_client is None
                    else None
                ),
            )
            if self._client_provider is not None:
                await self._close_invocation_entry(failed_entry)
            else:
                await self._close_entry(failed_entry)
            raise

        # ``MCPStreamableHTTPTool.get_mcp_client`` lazily creates an
        # ``httpx.AsyncClient`` when no caller client was provided AND a
        # ``header_provider`` was set. We treat any client allocated this
        # way as owned (closed by the handler). When the caller supplies
        # one, we never close it.
        owned_client: httpx.AsyncClient | None = None
        if provided_client is None:
            owned_client = cast("httpx.AsyncClient | None", getattr(tool, "_httpx_client", None))
        return _CacheEntry(tool=tool, owned_httpx_client=owned_client)

    async def _close_invocation_entry(self, entry: _CacheEntry) -> None:
        """Finish invocation cleanup even if the caller is cancelled again."""
        # MCPStreamableHTTPTool dispatches connect/close to its lifecycle owner,
        # keeping the SDK's cancel-scope entry and exit on that same task.
        cleanup = asyncio.create_task(self._close_entry(entry))
        cancelled = False
        while not cleanup.done():
            try:
                await asyncio.shield(cleanup)
            except asyncio.CancelledError:
                cancelled = True
        cleanup.result()  # Propagate cancellation/errors from cleanup itself.
        if cancelled:
            raise asyncio.CancelledError

    async def _close_entry(self, entry: _CacheEntry) -> None:
        """Close the MCP tool and any owned httpx client."""
        try:
            try:
                await entry.tool.close()
            except Exception:  # pragma: no cover - best effort
                logger.debug("DefaultMCPToolHandler: error closing MCP tool", exc_info=True)
        finally:
            if entry.owned_httpx_client is not None and not entry.owned_httpx_client.is_closed:
                try:
                    await entry.owned_httpx_client.aclose()
                except Exception:  # pragma: no cover - best effort
                    logger.debug("DefaultMCPToolHandler: error closing owned httpx client", exc_info=True)

    @staticmethod
    def _cache_key(
        server_url: str,
        server_label: str | None,
        connection_name: str | None,
        headers: dict[str, str] | None,
    ) -> tuple[str, str, str, str]:
        """Build an order-independent cache key for the invocation identity.

        Used only without a ``client_provider``. The key includes
        ``server_label`` and ``connection_name`` to distinguish logical
        connections.

        Header *names* are lower-cased inside the hash payload only so
        that ``Authorization`` and ``authorization`` map to the same
        cache entry. Header values remain case-sensitive (per RFC 7235).
        """
        if not headers:
            headers_hash = "0"
        else:
            normalized = sorted((k.lower(), v) for k, v in headers.items())
            payload = json.dumps(normalized, ensure_ascii=False)
            headers_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        return (server_url, server_label or "", connection_name or "", headers_hash)
