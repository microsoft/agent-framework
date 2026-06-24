# Copyright (c) Microsoft. All rights reserved.

"""The :class:`AgentFrameworkHost` and its :class:`ChannelContext` bridge.

The host is a small Starlette wrapper:

- ``__init__`` accepts a hostable target (``SupportsAgentRun`` agent or
  ``Workflow``) and a sequence of channels.
- :meth:`AgentFrameworkHost.app` lazily builds a Starlette app by calling
  every channel's ``contribute`` and mounting the returned routes under
  the channel's ``path`` (empty path → mount at the app root).
- :class:`ChannelContext` exposes ``run`` / ``run_stream`` for channels to
  invoke; the host handles hook invocation and per-``isolation_key`` session
  caching.

Per SPEC-002 (and ADR-0026), the host is intentionally thin so the bulk
of channel-specific behaviour stays in the channel package. Identity
linking, multicast delivery, background runs, and durable delivery are
follow-up enhancements layered outside this v1 host contract.
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from collections.abc import AsyncGenerator, AsyncIterator, Awaitable, Callable, Mapping, Sequence
from contextlib import AbstractContextManager, ExitStack, asynccontextmanager, contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from agent_framework import (
    AgentResponse,
    AgentResponseUpdate,
    CheckpointStorage,
    Content,
    FileCheckpointStorage,
    Message,
    ResponseStream,
    SupportsAgentRun,
    Workflow,
    WorkflowEvent,
)
from opentelemetry import context as otel_context
from opentelemetry import trace
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import BaseRoute, Mount, Route, WebSocketRoute
from starlette.types import ASGIApp, Receive, Scope, Send

from ._isolation import (
    ISOLATION_HEADER_CHAT,
    ISOLATION_HEADER_USER,
    IsolationKeys,
    reset_current_isolation_keys,
    set_current_isolation_keys,
)
from ._persistence import normalize_state_dir
from ._state_store import SessionsStateStore, build_session_aliases
from ._types import (
    Channel,
    ChannelRequest,
    ChannelResponseHook,
    ChannelRunHook,
    ChannelStreamUpdateHook,
    HostedRunResult,
    HostStatePaths,
)

if TYPE_CHECKING:
    from agent_framework._workflows._workflow import WorkflowRunResult

logger = logging.getLogger("agent_framework.hosting")


def _exact_path_route(path: str, route: BaseRoute) -> BaseRoute | None:
    """Clone a root route so ``Mount('/x', Route('/'))`` also handles ``/x`` without a redirect."""
    if isinstance(route, Route) and route.path == "/":
        return Route(
            path,
            route.endpoint,
            methods=route.methods,
            name=route.name,
            include_in_schema=route.include_in_schema,
        )
    if isinstance(route, WebSocketRoute) and route.path == "/":
        return WebSocketRoute(path, route.endpoint, name=route.name)
    return None


def _checkpoint_path_for_isolation_key(root: Path, isolation_key: str) -> Path:
    r"""Return ``root / isolation_key`` after rejecting path-traversal patterns.

    Isolation keys are intentionally caller-controlled: they may come from
    host/platform headers, channel-supplied derivations such as
    ``telegram:<chat_id>``, body fields parsed by a channel ``run_hook``,
    route/path segments, or environment-provided context in an ephemeral host.
    Joining such a value into a filesystem path without validation is CWE-22:
    a value such as ``../../../etc/foo`` or ``\\foo`` (Windows UNC) would let
    the resulting checkpoint directory escape the configured root.

    The check intentionally uses a denylist so legitimate namespaced keys
    (``telegram:42``, ``entra:abc-def``) are preserved as-is. Rejected:

    * any key containing ``/``, ``\\``, or NUL;
    * keys that reduce to empty after stripping dots (``.``, ``..``, ``...``,
      ...);
    * absolute paths (``os.path.isabs``);
    * keys carrying a drive letter prefix (``os.path.splitdrive`` — catches
      Windows ``C:/...`` and single-letter ``X:foo`` constructs that
      ``Path("/root") / "X:foo"`` would otherwise interpret as drive-rooted).

    After joining, both ``root`` and the resolved target are normalised and
    the target is verified to stay under the resolved root as defence in
    depth — if the denylist ever misses a pattern, this final check still
    refuses the join.

    Raises:
        ValueError: If ``isolation_key`` is not a non-empty string or fails
            any of the validation steps above.
    """
    if not isinstance(isolation_key, str) or not isolation_key:
        raise ValueError("isolation_key must be a non-empty string")
    if (
        "/" in isolation_key
        or "\\" in isolation_key
        or "\x00" in isolation_key
        or isolation_key.strip(".") == ""
        or os.path.isabs(isolation_key)
        or os.path.splitdrive(isolation_key)[0]
        # ``splitdrive`` only recognises drive letters on Windows; reject
        # the ``X:rest`` pattern explicitly so a payload crafted on a
        # POSIX host still fails closed if the resulting directory ever
        # round-trips to Windows storage.
        or (len(isolation_key) >= 2 and isolation_key[0].isalpha() and isolation_key[1] == ":")
    ):
        raise ValueError(f"Invalid isolation_key for checkpoint path: {isolation_key!r}")

    root_resolved = root.resolve()
    target = (root_resolved / isolation_key).resolve()
    if not target.is_relative_to(root_resolved):
        raise ValueError(f"Invalid isolation_key for checkpoint path: {isolation_key!r}")
    return target


def _workflow_output_to_text(value: Any) -> str:
    """Render a single workflow ``output`` payload as plain text.

    Used by the streaming path (``_workflow_event_to_update``) when an
    executor emits an arbitrary Python object that the host then has to
    serialise into an :class:`AgentResponseUpdate` content for the SSE
    stream. ``AgentResponse`` and ``AgentResponseUpdate`` carry text
    natively; everything else is best-effort ``str()``.
    """
    text = getattr(value, "text", None)
    if isinstance(text, str):
        return text
    return str(value)


async def _apply_run_hook(
    hook: ChannelRunHook,
    request: ChannelRequest,
    *,
    target: SupportsAgentRun | Workflow,
    protocol_request: Any | None,
) -> ChannelRequest:
    """Invoke a run hook with the host-owned calling convention."""
    result = hook(request, target=target, protocol_request=protocol_request)
    if isinstance(result, Awaitable):
        return await result
    return result


async def _apply_response_hook(
    hook: ChannelResponseHook,
    result: HostedRunResult[Any],
    *,
    request: ChannelRequest,
    channel_name: str | None,
) -> HostedRunResult[Any]:
    """Invoke a response hook with the host-owned calling convention."""
    out = hook(result, request=request, channel_name=channel_name or request.channel)
    if isinstance(out, Awaitable):
        return await out
    return out


def _capture_current_otel_context() -> object | None:
    """Capture the current OTel context when a valid span is active.

    Streaming channels can defer target iteration until after the route handler
    has returned (for example, `StreamingResponse`). Capturing the current OTel
    context at stream-construction time lets the host restore strict parent-child
    span linkage during deferred pulls and finalization.
    """
    current_span_context = trace.get_current_span().get_span_context()
    if not current_span_context.is_valid:
        return None
    return otel_context.get_current()


def _workflow_event_to_update(event: WorkflowEvent[Any]) -> AgentResponseUpdate | None:
    """Map a :class:`WorkflowEvent` to a channel-friendly :class:`AgentResponseUpdate`.

    Returns ``None`` for events the host should drop (anything that is not
    user-visible output). The original event is preserved on the update's
    ``raw_representation`` so consumers can recover full workflow context.
    """
    if event.type != "output":
        return None
    payload: Any = event.data
    if isinstance(payload, AgentResponseUpdate):
        # Already a streaming update — pass through but tag the source so
        # downstream hooks can tell it came from a workflow executor.
        if payload.raw_representation is None:
            payload.raw_representation = event
        return payload
    if isinstance(payload, Content):
        # Preserve the original content (image, function call, audio, …)
        # rather than stringifying — the host stays modality-agnostic
        # and lets each destination channel decide what it can render.
        return AgentResponseUpdate(
            contents=[payload],
            role="assistant",
            author_name=event.executor_id,
            raw_representation=event,
        )
    text = _workflow_output_to_text(payload)
    return AgentResponseUpdate(
        contents=[Content.from_text(text=text)],
        role="assistant",
        author_name=event.executor_id,
        raw_representation=event,
    )


@asynccontextmanager
async def _suppress_already_consumed() -> AsyncGenerator[None]:
    """Yield, swallowing finalizer failures so consumer cleanup never crashes the host.

    The bridge stream calls ``get_final_response()`` after iterating the
    workflow stream so the workflow's cleanup hooks run; on some paths the
    stream considers itself already finalized (or its inner stream was
    closed by ``__anext__`` auto-finalization) and the finalizer raises.
    We are inside an async-generator ``finally`` block during teardown,
    so we MUST NOT propagate — that would mask the iteration's real
    result and cascade into the channel's own cleanup. We always log
    with ``exc_info=True`` so the swallowed failure is observable in
    operator logs (a regression in the workflow's own cleanup hooks
    would otherwise vanish into a clean run).
    """
    try:
        yield
    except RuntimeError as exc:
        # Narrow match: only the two documented benign messages produced
        # by ``ResponseStream`` / async-iteration teardown should be
        # swallowed. Anything else (executor-side ``RuntimeError`` from a
        # ``raise RuntimeError(...)`` in user code, runner-context state
        # error, checkpoint-store ``RuntimeError`` during the post-run
        # flush, …) is a real bug and is escalated to the unexpected-error
        # branch so it's logged with a full stack trace at ERROR. We
        # still don't propagate (we're in an async-generator ``finally``
        # during teardown) — see the docstring.
        message = str(exc)
        if "Inner stream not available" in message or "Event loop is closed" in message:
            logger.warning("workflow stream finalize raised RuntimeError; cleanup skipped", exc_info=True)
        else:
            logger.exception("workflow stream finalize raised an unexpected RuntimeError; cleanup skipped")
    except Exception:
        # Anything else (checkpoint write failure, context-provider
        # error in a cleanup hook, executor-side bug, …) is a real
        # problem. ``logger.exception`` includes the traceback and
        # routes at ERROR so it's grep-able in production. We still
        # don't propagate — see the docstring.
        logger.exception("workflow stream finalize raised an unexpected error; cleanup skipped")


class _BoundResponseStream:
    """Adapter that keeps an :class:`ExitStack` open across stream iteration.

    Streaming runs return a :class:`ResponseStream` synchronously, but
    consumption happens later (the channel iterates). For host-bound
    request context (e.g. Foundry response-id binding) to survive that
    gap, we hold the stack open until the underlying stream is exhausted
    or :meth:`aclose` is called. We forward awaitable + async-iterator +
    ``get_final_response`` semantics so the channel sees a normal
    ``ResponseStream``-shaped object.

    Lifecycle:

    * Async iteration (``async for u in stream``) — the stack is closed
      in the iterator's ``finally`` after the inner stream is drained.
    * ``await stream`` — convenience for ``await get_final_response()``;
      the stack is closed when ``get_final_response`` runs because that
      path also routes through :meth:`_close`.
    * ``await stream.get_final_response()`` — closes the stack in
      ``finally``.
    * Manual cleanup — call :meth:`aclose` (idempotent). Safe to call
      from a ``finally`` even after iteration / ``get_final_response``
      already closed the stack.
    """

    def __init__(
        self,
        inner: Any,
        stack: ExitStack,
        *,
        otel_context_snapshot: object | None = None,
    ) -> None:
        self._inner = inner
        self._stack = stack
        self._otel_context_snapshot = otel_context_snapshot
        self._closed = False

    def _close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._stack.close()

    @contextmanager
    def _activate_otel_context(self) -> Any:
        """Re-activate the captured OTel parent context for deferred work."""
        if self._otel_context_snapshot is None:
            yield
            return
        token = otel_context.attach(cast("Any", self._otel_context_snapshot))
        try:
            yield
        finally:
            otel_context.detach(token)

    async def aclose(self) -> None:
        """Idempotently release the bound request context.

        Channels that abandon the stream without iterating it (e.g.
        early-return on a validation failure) MUST call this in a
        ``finally`` so the host-bound contextvars don't leak for the
        lifetime of the host. Calling after the stack already closed
        (via iteration / ``get_final_response``) is a no-op.
        """
        self._close()

    def __await__(self) -> Any:
        # Convenience: ``await stream`` ≡ ``await stream.get_final_response()``.
        # We route through ``get_final_response`` so the stack closes in
        # its ``finally`` block, instead of leaking the binding for the
        # host's lifetime as the previous direct-await delegation did.
        return self.get_final_response().__await__()

    def __aiter__(self) -> AsyncIterator[Any]:
        return self._wrap()

    async def _wrap(self) -> AsyncIterator[Any]:
        with self._activate_otel_context():
            iterator = self._inner.__aiter__()
        try:
            while True:
                try:
                    with self._activate_otel_context():
                        item = await iterator.__anext__()
                except StopAsyncIteration:
                    break
                yield item
        finally:
            self._close()

    async def get_final_response(self) -> Any:
        try:
            with self._activate_otel_context():
                return await self._inner.get_final_response()
        finally:
            self._close()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


class _HostResponseStream:
    """Adapter that applies host-owned stream and final-response hooks."""

    def __init__(
        self,
        inner: Any,
        *,
        request: ChannelRequest,
        stream_update_hook: ChannelStreamUpdateHook | None = None,
        response_hook: ChannelResponseHook | None = None,
        channel_name: str | None = None,
    ) -> None:
        self._inner = inner
        self._request = request
        self._stream_update_hook = stream_update_hook
        self._response_hook = response_hook
        self._channel_name = channel_name

    def __await__(self) -> Any:
        return self.get_final_response().__await__()

    def __aiter__(self) -> AsyncIterator[Any]:
        return self._wrap()

    async def _wrap(self) -> AsyncIterator[Any]:
        async for update in self._inner:
            if self._stream_update_hook is None:
                yield update
                continue
            transformed = self._stream_update_hook(update)
            if isinstance(transformed, Awaitable):
                transformed = await transformed
            if transformed is None:
                continue
            yield transformed

    async def get_final_response(self) -> Any:
        result = await self._inner.get_final_response()
        if self._response_hook is None:
            return result
        shaped = await _apply_response_hook(
            self._response_hook,
            HostedRunResult(result),
            request=self._request,
            channel_name=self._channel_name,
        )
        return shaped.result

    async def aclose(self) -> None:
        close = getattr(self._inner, "aclose", None)
        if close is not None:
            await close()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


class ChannelContext:
    """Host-owned bridge that channels call to invoke the target."""

    def __init__(self, host: AgentFrameworkHost) -> None:
        """Bind the context to its owning :class:`AgentFrameworkHost`.

        The host instance is the source of truth for the target, registered
        channels, sessions, and lifecycle state. Channels only ever receive a
        context; they never see the host directly.
        """
        self._host = host

    @property
    def target(self) -> SupportsAgentRun | Workflow:
        """The hostable target the channel should invoke."""
        return self._host.target

    async def run(
        self,
        request: ChannelRequest,
        *,
        run_hook: ChannelRunHook | None = None,
        protocol_request: Any | None = None,
        response_hook: ChannelResponseHook | None = None,
        channel_name: str | None = None,
    ) -> HostedRunResult[Any]:
        """Invoke the target for ``request`` and return a channel-neutral result.

        For agent targets the return type narrows to
        ``HostedRunResult[AgentResponse]``; for workflow targets to
        ``HostedRunResult[WorkflowRunResult]``. The static return is left
        as ``HostedRunResult[Any]`` because :class:`ChannelContext` is
        agnostic to which target shape the host was constructed with;
        channels narrow at the call site if they need it.

        Args:
            request: The channel-built request envelope.

        Keyword Args:
            run_hook: Optional channel-supplied hook the host applies before
                invoking the target.
            protocol_request: Raw channel-native payload passed to
                ``run_hook``.
            response_hook: Optional channel-supplied hook the host applies to
                the completed result before returning it.
            channel_name: Channel name passed to ``response_hook``. Defaults
                to ``request.channel``.
        """
        prepared = await self._host._apply_run_hook(  # pyright: ignore[reportPrivateUsage]
            request,
            hook=run_hook,
            protocol_request=protocol_request,
        )
        result = await self._host._invoke(prepared)  # pyright: ignore[reportPrivateUsage]
        return await self._host._apply_response_hook(  # pyright: ignore[reportPrivateUsage]
            result,
            request=prepared,
            hook=response_hook,
            channel_name=channel_name,
        )

    async def run_stream(
        self,
        request: ChannelRequest,
        *,
        run_hook: ChannelRunHook | None = None,
        protocol_request: Any | None = None,
        stream_update_hook: ChannelStreamUpdateHook | None = None,
        response_hook: ChannelResponseHook | None = None,
        channel_name: str | None = None,
    ) -> ResponseStream[AgentResponseUpdate, AgentResponse]:
        """Apply host-owned hooks and invoke the target with ``stream=True``.

        Channels iterate the stream directly (it acts like an AsyncGenerator)
        and are responsible for delivering updates to their wire protocol.
        When ``stream_update_hook`` is supplied, the host applies it during
        iteration to rewrite or drop individual updates before they hit the wire.

        Args:
            request: The channel-built request envelope.

        Keyword Args:
            run_hook: Optional channel-supplied hook the host applies before
                opening the target stream.
            protocol_request: Raw channel-native payload passed to
                ``run_hook``.
            stream_update_hook: Optional host-applied update transform.
            response_hook: Optional host-applied final-response transform.
            channel_name: Channel name passed to ``response_hook``. Defaults
                to ``request.channel``.
        """
        prepared = await self._host._apply_run_hook(  # pyright: ignore[reportPrivateUsage]
            request,
            hook=run_hook,
            protocol_request=protocol_request,
        )
        stream = self._host._invoke_stream(prepared)  # pyright: ignore[reportPrivateUsage]
        if stream_update_hook is None and response_hook is None:
            return stream
        return _HostResponseStream(
            stream,
            request=prepared,
            stream_update_hook=stream_update_hook,
            response_hook=response_hook,
            channel_name=channel_name,
        )  # type: ignore[return-value]


class _FoundryIsolationASGIMiddleware:
    """Lift platform-provided isolation headers into a contextvar.

    The Foundry Hosted Agents runtime injects
    ``x-agent-{user,chat}-isolation-key`` on every inbound HTTP request.
    Storage providers that need partition-aware writes (notably
    :class:`FoundryHostedAgentHistoryProvider`) read those keys via
    :func:`get_current_isolation_keys` to avoid every channel having to
    parse platform-specific headers itself. We intentionally inspect only HTTP
    scopes; lifespan/websocket scopes are forwarded untouched. When neither
    header is present the contextvar stays at its default ``None``, so local-dev
    requests behave as before.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        user_key: str | None = None
        chat_key: str | None = None
        for raw_name, raw_value in scope.get("headers") or ():
            name = raw_name.decode("latin-1").lower()
            if name == ISOLATION_HEADER_USER:
                user_key = raw_value.decode("latin-1") or None
            elif name == ISOLATION_HEADER_CHAT:
                chat_key = raw_value.decode("latin-1") or None
        if user_key is None and chat_key is None:
            await self.app(scope, receive, send)
            return
        token = set_current_isolation_keys(IsolationKeys(user_key=user_key, chat_key=chat_key))
        try:
            await self.app(scope, receive, send)
        finally:
            reset_current_isolation_keys(token)


class AgentFrameworkHost:
    """Owns one Starlette app, one hostable target, and a sequence of channels."""

    def __init__(
        self,
        target: SupportsAgentRun | Workflow,
        *,
        channels: Sequence[Channel],
        debug: bool = False,
        checkpoint_location: str | os.PathLike[str] | CheckpointStorage | None = None,
        state_dir: str | os.PathLike[str] | HostStatePaths | Mapping[str, str | os.PathLike[str]] | None = None,
    ) -> None:
        """Create a host for ``target`` and its channels.

        Args:
            target: The hostable target to invoke from channels — either a
                ``SupportsAgentRun``-compatible agent or a ``Workflow``. The
                host detects the kind and dispatches to the appropriate
                execution seam (``agent.run(...)`` vs ``workflow.run(message=...)``).
                For workflow targets, channels (or their ``run_hook``) are
                responsible for shaping ``ChannelRequest.input`` into the
                workflow start executor's typed input.

        Keyword Args:
            channels: The channels to expose. Each channel contributes routes
                and commands that are mounted under ``channel.path`` (defaulting
                to the channel name).
            debug: Whether to enable Starlette's debug mode (stack traces in
                responses, etc.) and per-channel debug logging.
            checkpoint_location: When ``target`` is a :class:`Workflow`, the
                location used to persist workflow checkpoints across requests.
                Either a filesystem path (``str`` / ``PathLike``) — the host
                creates a per-conversation
                :class:`~agent_framework.FileCheckpointStorage` rooted at
                ``checkpoint_location / <isolation_key>`` — or a
                :class:`~agent_framework.CheckpointStorage` instance the host
                uses as-is (caller owns scoping). Per-request behaviour:
                requests without ``ChannelRequest.session.isolation_key``
                are run without checkpointing. When set on a workflow that
                already has its own checkpoint storage configured
                (``WorkflowBuilder(checkpoint_storage=...)``), the host
                refuses to start so ownership of checkpointing is
                unambiguous. Ignored for ``SupportsAgentRun`` targets (a
                warning is emitted). Takes precedence over
                ``state_dir['checkpoints']`` (or the auto-derived
                ``state_dir/checkpoints/`` subfolder); a warning surfaces
                the double-configuration.
            state_dir: Opt-in disk persistence for host-managed state.
                When set, the host writes session aliases created by
                :meth:`reset_session` to a :mod:`diskcache`-backed store
                under ``state_dir``. When the target is a
                :class:`Workflow`, the auto-derived
                ``state_dir/checkpoints/`` subfolder (or the
                ``checkpoints`` key of the mapping form) is also used
                as the workflow checkpoint location (equivalent to
                passing ``checkpoint_location`` directly). Accepts:

                * ``None`` (default) — everything stays in memory; the
                  process owns its state and loses it on exit. Matches
                  today's behaviour exactly.
                * ``str`` / :class:`os.PathLike` — the host derives
                  default subpaths ``state_dir/sessions/`` and
                  (for workflow targets) ``state_dir/checkpoints/``.
                  Recommended for most
                  long-running-host deployments — one path, no extra
                  config, all components persist together. Note: when
                  the target is a Workflow this enables workflow
                  checkpoint persistence; use the mapping form below
                  and omit ``checkpoints`` to opt out.
                * :class:`HostStatePaths` typed dict / plain
                  ``Mapping`` — per-component overrides for callers that
                  want each component on a different volume (fast local
                  SSD for checkpoints, network-attached volume for
                  sessions, …). Components missing from the mapping fall
                  back to in-memory (or, for ``checkpoints``, to no
                  checkpoint persistence). Unknown keys raise
                  ``ValueError`` to surface typos early.

                The ``sessions`` component requires the
                optional ``diskcache`` dependency (install with
                ``pip install 'agent-framework-hosting[disk]'``);
                ``checkpoints`` uses the core
                :class:`~agent_framework.FileCheckpointStorage` and has
                no extra dependency. The disk-cache-backed sessions
                component acquires an OS-level advisory lock on its
                directory; a second host pointed at the same path raises
                :class:`RuntimeError` at construction so two processes
                do not race session-alias writes. When
                ``checkpoint_location`` is supplied explicitly, the
                ``checkpoints`` sub-path is ignored.
        """
        self.target: SupportsAgentRun | Workflow = target
        self._is_workflow = isinstance(target, Workflow)
        self.channels = list(channels)
        self._debug = debug
        self._app: Starlette | None = None
        self._workflow_lock = asyncio.Lock()
        self._state_paths: dict[str, Path | None] = normalize_state_dir(state_dir)
        checkpoints_explicit_in_mapping = isinstance(state_dir, Mapping) and "checkpoints" in state_dir
        derived_checkpoint_path = self._state_paths.get("checkpoints")
        self._checkpoint_location: Path | CheckpointStorage | None = None
        effective_checkpoint_source: str | os.PathLike[str] | CheckpointStorage | None = checkpoint_location
        if checkpoint_location is None and derived_checkpoint_path is not None:
            # Only consume the derived path when the target is a
            # Workflow; non-workflow targets get a warning (explicit
            # mapping case) or a silent ignore (single-path case).
            if self._is_workflow:
                effective_checkpoint_source = derived_checkpoint_path
            elif checkpoints_explicit_in_mapping:
                logger.warning("state_dir['checkpoints'] is set but target is not a Workflow; ignoring.")
        elif checkpoint_location is not None and derived_checkpoint_path is not None:
            # Both the legacy parameter and the new state_dir component
            # configure the same thing. Keep the explicit one and
            # surface the double-config so the user notices the no-op.
            logger.warning(
                "Both checkpoint_location and state_dir['checkpoints'] are set "
                "(state_dir['checkpoints']=%s); the explicit checkpoint_location "
                "takes precedence and the state_dir sub-path is ignored. "
                "Use the HostStatePaths mapping form and omit 'checkpoints' to "
                "configure session-alias persistence without also enabling "
                "host-managed workflow checkpointing.",
                derived_checkpoint_path,
            )
        if effective_checkpoint_source is not None:
            if not self._is_workflow:
                # Only the legacy parameter path can reach here for a
                # non-workflow target (the derived path was already
                # short-circuited above). Preserve the historical
                # warning text so existing users see the same message.
                logger.warning("checkpoint_location is set but target is not a Workflow; ignoring.")
            else:
                workflow: Workflow = target  # type: ignore[assignment]
                if workflow._runner_context.has_checkpointing():  # type: ignore[reportPrivateUsage]
                    raise RuntimeError(
                        "Workflow already has checkpoint storage configured "
                        "(WorkflowBuilder(checkpoint_storage=...)). The host "
                        "manages checkpoints when checkpoint_location (or "
                        "state_dir['checkpoints']) is set; remove one of the "
                        "two configurations."
                    )
                if isinstance(effective_checkpoint_source, (str, os.PathLike)):
                    self._checkpoint_location = Path(os.fspath(effective_checkpoint_source))
                else:
                    # Anything else is treated as a CheckpointStorage instance.
                    # ``CheckpointStorage`` is a non-runtime-checkable Protocol,
                    # so we cannot ``isinstance``-check it directly.
                    self._checkpoint_location = effective_checkpoint_source
        self._sessions: dict[str, Any] = {}
        sessions_path = self._state_paths.get("sessions")
        self._sessions_store: SessionsStateStore | None
        if sessions_path is not None:
            self._sessions_store = SessionsStateStore(sessions_path)
            self._session_aliases: dict[str, str] = build_session_aliases(self._sessions_store)
        else:
            self._sessions_store = None
            self._session_aliases = {}
        # Set by ``serve()`` so the lifespan startup handler doesn't
        # double-log the banner; remains ``False`` when callers mount
        # ``host.app`` under their own ASGI server.
        self._startup_logged: bool = False

    @property
    def app(self) -> Starlette:
        """Lazily build (and cache) the Starlette application."""
        if self._app is None:
            self._app = self._build_app()
        return self._app

    def serve(
        self,
        *,
        host: str = "127.0.0.1",
        port: int = 8000,
        workers: int = 1,
        **config_kwargs: Any,
    ) -> None:
        """Start the host on ``host:port`` using Hypercorn.

        Hypercorn is the same ASGI server the Foundry Hosted Agents
        runtime uses for production deployments, so running locally with
        the same server keeps dev/prod parity (Trio fallbacks, lifespan
        semantics, HTTP/2 support, …). Install with the ``serve`` extra
        (``pip install agent-framework-hosting[serve]``).

        Args:
            host: Interface to bind. Defaults to ``127.0.0.1``.
            port: TCP port to bind. Defaults to ``8000``.
            workers: Number of worker processes. Defaults to ``1``;
                Hypercorn's process model only kicks in for ``>1``.
            **config_kwargs: Forwarded to :class:`hypercorn.config.Config`
                via attribute assignment, so any documented Hypercorn
                config field (e.g. ``keep_alive_timeout=...``,
                ``access_log_format=...``) can be set directly.
        """
        try:
            from hypercorn.asyncio import serve as _hypercorn_serve  # pyright: ignore[reportUnknownVariableType]
            from hypercorn.config import Config
        except ImportError as exc:  # pragma: no cover - exercised at runtime
            raise RuntimeError(
                "AgentFrameworkHost.serve() requires hypercorn. "
                "Install with `pip install agent-framework-hosting[serve]` or `pip install hypercorn`."
            ) from exc

        config = Config()
        config.bind = [f"{host}:{port}"]
        config.workers = workers
        for key, value in config_kwargs.items():
            setattr(config, key, value)

        # Touch ``self.app`` so the lifespan startup log fires once before
        # we hand off to hypercorn — gives a single, readable banner of
        # what the host is exposing without requiring channels to log
        # individually.
        app = self.app
        self._log_startup(host=host, port=port, workers=workers)
        # Mark as already logged so the lifespan startup handler does not
        # double-log the same banner.
        self._startup_logged = True

        # ``hypercorn.asyncio.serve`` has a complex partially-typed signature
        # (multiple ASGI/WSGI app overloads) and its ``Scope`` definition
        # diverges from Starlette's; cast both sides to ``Any`` to keep the
        # call site readable without sprinkling per-error suppressions.
        serve_callable = cast(Any, _hypercorn_serve)
        asyncio.run(serve_callable(app, config))

    def reset_session(self, isolation_key: str) -> None:
        """Rotate ``isolation_key`` to a fresh session id without deleting history.

        Old turns are preserved on disk under their original session id and
        remain accessible by passing that id explicitly (e.g. as
        ``previous_response_id``). Future requests using ``isolation_key``
        get a new, empty ``AgentSession``.
        """
        new_id = f"{isolation_key}#{uuid.uuid4().hex[:8]}"
        self._session_aliases[isolation_key] = new_id
        self._sessions.pop(isolation_key, None)

    # -- internals --------------------------------------------------------- #

    def _log_startup(
        self,
        *,
        host: str | None = None,
        port: int | None = None,
        workers: int | None = None,
    ) -> None:
        """Emit a single human-friendly startup banner.

        Mirrors the ``AgentServerHost`` convention from
        ``azure.ai.agentserver.core``: one INFO line that captures the
        target type, every channel + its endpoint path, the bind address
        (when known), whether we're running inside a Foundry Hosted
        Agents container, and the worker count. Keeps log noise low
        while still giving an operator a single grep-able anchor when
        triaging.

        Called from both :meth:`serve` (which knows the bind triple)
        and the ASGI lifespan ``startup`` phase (which does not — the
        host may be embedded under any caller-managed ASGI server).
        Bind fields are omitted from the log line when unknown.
        """
        target_kind = "Workflow" if isinstance(self.target, Workflow) else type(self.target).__name__
        target_name = getattr(self.target, "name", None) or target_kind
        channels_repr = ", ".join(
            f"{ch.name}@{ch.path or '/'}"  # blank path means "mounted at root"
            for ch in self.channels
        )
        is_hosted = bool(os.environ.get("FOUNDRY_HOSTING_ENVIRONMENT"))
        bind = f"{host}:{port}" if host is not None and port is not None else "<embedded>"
        logger.info(
            "AgentFrameworkHost starting: target=%s (%s) bind=%s workers=%s hosted=%s channels=[%s]",
            target_name,
            target_kind,
            bind,
            workers if workers is not None else "<embedded>",
            is_hosted,
            channels_repr or "<none>",
        )

    def _build_app(self) -> Starlette:
        context = ChannelContext(self)
        routes: list[BaseRoute] = []
        on_startup: list[Callable[[], Awaitable[None]]] = []
        on_shutdown: list[Callable[[], Awaitable[None]]] = []

        # ``/readiness`` is the standard probe path the Foundry Hosted Agents
        # runtime hits to gate traffic. We expose it unconditionally — once the
        # ASGI app is up the host considers itself ready (channels register
        # their own startup hooks and may run before the first request, but
        # readiness is intentionally cheap so the platform's probe never times
        # out on transient channel work). Mounted first so a channel cannot
        # accidentally shadow it.
        async def _readiness(_request: Request) -> PlainTextResponse:  # noqa: RUF029
            """Liveness/readiness probe handler used by Foundry Hosted Agents."""
            return PlainTextResponse("ok")

        routes.append(Route("/readiness", _readiness, methods=["GET"]))

        for channel in self.channels:
            contribution = channel.contribute(context)
            # Channels publish routes relative to their root; mount under channel.path.
            # An empty path means "mount at the app root" — useful when an external
            # platform requires the channel endpoint at "/" or at a route contributed
            # by the channel.
            if contribution.routes:
                if channel.path:
                    channel_routes = list(contribution.routes)
                    exact_routes = [
                        exact_route
                        for route in channel_routes
                        if (exact_route := _exact_path_route(channel.path, route)) is not None
                    ]
                    routes.extend(exact_routes)
                    routes.append(Mount(channel.path, routes=channel_routes))
                else:
                    routes.extend(contribution.routes)
            on_startup.extend(contribution.on_startup)
            on_shutdown.extend(contribution.on_shutdown)

        @asynccontextmanager
        async def lifespan(_app: Starlette) -> AsyncGenerator[None]:
            # Emit the startup banner once. ``serve()`` may have already
            # logged it (it logs eagerly so the banner appears before
            # control passes to hypercorn); the lifespan still logs it
            # for callers that mount ``host.app`` directly under their
            # own ASGI server.
            if not self._startup_logged:
                self._log_startup()
                self._startup_logged = True
            # Run every startup callback; collect (don't propagate) so
            # one bad channel doesn't leave its peers half-initialised
            # AND deny us a chance to pair-up shutdown calls. After all
            # callbacks have been attempted, raise the FIRST error so
            # Starlette / the ASGI server still aborts boot — and log
            # every other failure so operators can see them all in one
            # log scrape rather than discovering them turn-by-turn.
            startup_errors: list[tuple[str, BaseException]] = []
            for cb in on_startup:
                try:
                    await cb()
                except Exception as exc:
                    name = getattr(cb, "__qualname__", repr(cb))
                    logger.exception("lifespan startup: callback %s failed", name)
                    startup_errors.append((name, exc))
            if startup_errors:
                _, first_exc = startup_errors[0]
                if len(startup_errors) > 1:
                    logger.error(
                        "lifespan startup: %d callback(s) failed; first error re-raised, "
                        "remaining failures already logged above (%s)",
                        len(startup_errors),
                        ", ".join(n for n, _ in startup_errors[1:]),
                    )
                raise first_exc
            try:
                yield
            finally:
                # Same shape on the shutdown side: walk every callback
                # so a bad one can't leave its peers leaking
                # tasks/sockets/sessions, then raise the first if any
                # failed so the server's exit code reflects the failure.
                shutdown_errors: list[tuple[str, BaseException]] = []
                for cb in on_shutdown:
                    try:
                        await cb()
                    except Exception as exc:
                        name = getattr(cb, "__qualname__", repr(cb))
                        logger.exception("lifespan shutdown: callback %s failed", name)
                        shutdown_errors.append((name, exc))
                if self._sessions_store is not None:
                    try:
                        self._sessions_store.close()
                    except Exception as exc:  # pragma: no cover - defensive
                        logger.exception("lifespan shutdown: sessions store close failed")
                        shutdown_errors.append(("SessionsStateStore.close", exc))
                if shutdown_errors:
                    _, first_exc = shutdown_errors[0]
                    if len(shutdown_errors) > 1:
                        logger.error(
                            "lifespan shutdown: %d callback(s) failed; first error re-raised, "
                            "remaining failures already logged above (%s)",
                            len(shutdown_errors),
                            ", ".join(n for n, _ in shutdown_errors[1:]),
                        )
                    raise first_exc

        middleware = (
            [Middleware(_FoundryIsolationASGIMiddleware)] if os.environ.get("FOUNDRY_HOSTING_ENVIRONMENT") else []
        )
        return Starlette(
            debug=self._debug,
            routes=routes,
            lifespan=lifespan,
            middleware=middleware,
        )

    def _build_run_kwargs(self, request: ChannelRequest) -> dict[str, Any]:
        # The host keys a per-isolation_key AgentSession off the channel's
        # session hint so context providers (FileHistoryProvider, …) on the
        # target see one session per end user.
        session = None
        if request.session_mode != "disabled" and request.session is not None:
            isolation_key = request.session.isolation_key
            if isolation_key is not None and hasattr(self.target, "create_session"):
                session_id = self._session_aliases.get(isolation_key, isolation_key)
                session = self._sessions.get(isolation_key)
                if session is None:
                    # Concurrency note: ``create_session`` is sync today,
                    # so the get/set window has no await point and CPython
                    # serialises us against other tasks. ``setdefault`` is
                    # the atomic primitive that keeps us safe even if a
                    # future ``create_session`` ever yields — both racers
                    # would see ``session is None``, both construct a new
                    # session, but only the first ``setdefault`` wins; the
                    # loser's just-built session is discarded (one
                    # transient orphan max per race window) instead of
                    # silently overwriting a peer-bound session that
                    # other in-flight requests are already using.
                    # ``create_session`` lives on agent-typed targets but not on
                    # ``Workflow``; the ``hasattr`` above guards the call site.
                    create_session = cast("Callable[..., Any]", self.target.create_session)  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]
                    new_session = create_session(session_id=session_id)
                    session = self._sessions.setdefault(isolation_key, new_session)

        run_kwargs: dict[str, Any] = {}
        if session is not None:
            run_kwargs["session"] = session
        if request.options:
            run_kwargs["options"] = request.options
        return run_kwargs

    async def _apply_run_hook(
        self,
        request: ChannelRequest,
        *,
        hook: ChannelRunHook | None,
        protocol_request: Any | None,
    ) -> ChannelRequest:
        """Apply a channel-supplied run hook under host ownership."""
        if hook is None:
            return request
        return await _apply_run_hook(
            hook,
            request,
            target=self.target,
            protocol_request=protocol_request,
        )

    async def _apply_response_hook(
        self,
        result: HostedRunResult[Any],
        *,
        request: ChannelRequest,
        hook: ChannelResponseHook | None,
        channel_name: str | None,
    ) -> HostedRunResult[Any]:
        """Apply a channel-supplied response hook under host ownership."""
        if hook is None:
            return result
        return await _apply_response_hook(hook, result, request=request, channel_name=channel_name)

    def _log_incoming(self, request: ChannelRequest, *, stream: bool) -> None:
        """Emit a structured INFO summary for every incoming target invocation.

        When ``debug=True`` is set on the host, also dump the channel-native
        settings the channel attached to the ``ChannelRequest`` — ``options``
        (if the channel or its ``run_hook`` chose to add any), plus
        ``attributes`` / ``metadata`` (the channel's protocol-specific bag,
        e.g. ``chat_id`` / ``callback_query_id`` for Telegram).

        Uses ``extra={...}`` so structured-logging consumers (the
        Foundry hosted-agent log shipper, OpenTelemetry handlers, …)
        can index per-field rather than re-parsing a template string.
        """
        isolation_key = request.session.isolation_key if request.session is not None else None
        logger.info(
            "channel request",
            extra={
                "channel": request.channel,
                "operation": request.operation,
                "stream": stream,
                "session": isolation_key,
                "session_mode": request.session_mode,
            },
        )
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                "channel request details",
                extra={
                    "channel": request.channel,
                    "options": dict(request.options) if request.options else {},
                    "attributes": dict(request.attributes) if request.attributes else {},
                    "metadata": dict(request.metadata) if request.metadata else {},
                },
            )

    def _bind_request_context(self, request: ChannelRequest) -> ExitStack:
        """Bind any per-request anchors a target's context-providers expose.

        Channels announce per-request anchors (currently ``response_id``
        and ``previous_response_id``) via ``ChannelRequest.attributes``.
        Some history providers — notably the Foundry hosted-agent history
        provider — need to write storage under the same ``response_id``
        the channel surfaces on its envelope so the next turn's
        ``previous_response_id`` walks the chain. Rather than the host
        knowing about specific provider classes, we duck-type: any
        context provider on the target that exposes a
        ``bind_request_context(response_id=..., previous_response_id=...,
        **_)`` context-manager gets it called with the request's
        attribute values. Per-request platform isolation keys are handled
        separately by :class:`_FoundryIsolationASGIMiddleware` (lifted
        off the inbound headers into a contextvar) so providers don't
        depend on channels to forward them. Bindings are scoped to the
        returned :class:`ExitStack` which the caller must enter before
        invoking the target and leave after the run completes.
        """
        stack = ExitStack()
        attrs = request.attributes or {}
        response_id = attrs.get("response_id")
        if not isinstance(response_id, str) or not response_id:
            return stack
        previous_response_id = attrs.get("previous_response_id")
        if previous_response_id is not None and not isinstance(previous_response_id, str):
            previous_response_id = None

        providers: Sequence[Any] = getattr(self.target, "context_providers", None) or ()

        for provider in providers:
            bind = getattr(provider, "bind_request_context", None)
            if not callable(bind):
                continue
            stack.enter_context(
                cast(
                    "AbstractContextManager[Any]",
                    bind(
                        response_id=response_id,
                        previous_response_id=previous_response_id,
                    ),
                )
            )
        return stack

    async def _invoke(self, request: ChannelRequest) -> HostedRunResult[AgentResponse]:
        self._log_incoming(request, stream=False)
        if self._is_workflow:
            # Workflow targets follow a separate path; the dedicated dispatch
            # is parameterised on ``WorkflowRunResult`` so the static return
            # type of ``_invoke`` itself stays the agent-shaped envelope.
            # Workflow instances own mutable runner context and do not support
            # concurrent ``run`` calls. Keep the normal Workflow programming
            # model intact by serializing requests to the shared workflow
            # instance supplied to this host.
            async with self._workflow_lock:
                return await self._invoke_workflow(request)  # type: ignore[return-value]
        run_kwargs = self._build_run_kwargs(request)
        with self._bind_request_context(request):
            # ``_is_workflow`` is False here so ``self.target`` is an
            # ``Agent``-shaped target whose ``.run`` returns
            # :class:`AgentResponse`. Narrow back to keep ``result.messages``
            # well-typed without conditional imports of ``Agent``.
            agent_target = cast("SupportsAgentRun", self.target)
            result = await agent_target.run(self._wrap_input(request), **run_kwargs)
        # Carry the full :class:`AgentResponse` as the typed envelope
        # ``result`` so channels (and developer-supplied response hooks)
        # can read ``messages``, ``value``, ``usage_details``,
        # ``response_id`` … directly off the target output without the
        # host pre-shaping any of it. The bound session (if any) is
        # surfaced so channels that want to render session metadata
        # don't have to re-resolve it.
        return HostedRunResult(result, session=run_kwargs.get("session"))

    def _invoke_stream(self, request: ChannelRequest) -> ResponseStream[AgentResponseUpdate, AgentResponse]:
        self._log_incoming(request, stream=True)
        if self._is_workflow:
            return self._invoke_workflow_stream(request)
        run_kwargs = self._build_run_kwargs(request)
        # ``run(stream=True)`` returns a ResponseStream synchronously (it is
        # itself awaitable / async-iterable). We hand it back to the channel
        # so the channel can drive iteration and apply its transform hook.
        # Streaming flows iterate after this method returns, which is
        # *outside* a sync ``with`` block — so we wrap the underlying
        # stream in an adapter that holds the binding open across the
        # iteration lifecycle.
        binder = self._bind_request_context(request)
        # Capture the request-parent OTel context BEFORE ``target.run``.
        # Python evaluates positional args before keyword args, so doing
        # this inline in the ``_BoundResponseStream(...)`` call would run
        # ``target.run(...)`` first and may capture a shifted context.
        otel_context_snapshot = _capture_current_otel_context()
        return _BoundResponseStream(  # type: ignore[return-value]
            self.target.run(self._wrap_input(request), stream=True, **run_kwargs),
            binder,
            otel_context_snapshot=otel_context_snapshot,
        )

    def _resolve_checkpoint_storage(self, request: ChannelRequest) -> CheckpointStorage | None:
        """Build (or return) the per-request checkpoint storage, or ``None``.

        Returns ``None`` when no ``checkpoint_location`` is configured or
        when the request lacks a stable session key — without a key we
        cannot scope checkpoints per conversation, and we'd rather skip
        checkpointing than pollute a single shared store.

        When ``checkpoint_location`` is a path, the per-conversation
        directory is built via :func:`_checkpoint_path_for_isolation_key`
        which rejects path-traversal patterns in ``isolation_key`` and
        verifies the resolved directory stays under the configured root
        (CWE-22 defence). Invalid keys cause the request to skip
        checkpointing with a WARNING rather than escape the root or
        crash the request.
        """
        if self._checkpoint_location is None:
            return None
        if request.session is None or not request.session.isolation_key:
            return None
        if isinstance(self._checkpoint_location, Path):
            try:
                target = _checkpoint_path_for_isolation_key(self._checkpoint_location, request.session.isolation_key)
            except ValueError as exc:
                logger.warning(
                    "Skipping checkpoint storage for request: %s",
                    exc,
                )
                return None
            return FileCheckpointStorage(str(target))
        # Caller-supplied storage — used as-is; caller owns scoping.
        return self._checkpoint_location

    async def _invoke_workflow(self, request: ChannelRequest) -> HostedRunResult[WorkflowRunResult]:
        """Dispatch to ``Workflow.run`` and wrap the result in a typed envelope.

        The channel's ``run_hook`` is the canonical adapter for shaping
        ``request.input`` into the workflow start executor's typed input
        (free-form text from a Telegram message, structured ``Responses``
        ``input`` items, …). When no hook is wired, ``request.input`` is
        forwarded verbatim — appropriate for workflows whose start executor
        accepts the channel's native input type (commonly ``str``).

        When ``checkpoint_location`` is configured on the host, a
        per-conversation checkpoint storage is resolved, the workflow is
        restored from its latest checkpoint (if any) and then re-run with
        the new input — mirroring the resume semantics of the Foundry
        Responses host.

        The full :class:`~agent_framework._workflows._workflow.WorkflowRunResult`
        is carried unchanged on :attr:`HostedRunResult.result` so
        destination channels can iterate :meth:`WorkflowRunResult.get_outputs`,
        inspect :meth:`WorkflowRunResult.get_final_state`, or pull other
        per-executor events themselves. The host intentionally does not
        map outputs onto messages — channels (and developer-supplied
        response hooks) own that projection because what counts as a
        "renderable output" is wire-format-specific.

        Workflows do not own session state in the agent sense, so
        ``HostedRunResult.session`` is ``None`` for workflow targets.
        """
        # Workflows do not own session state in the agent sense and do not
        # accept ``session=`` / ``options=`` kwargs. The channel's run_hook is
        # the seam for any per-run customization; nothing flows through here.
        workflow: Workflow = self.target  # type: ignore[assignment]
        storage = self._resolve_checkpoint_storage(request)
        await self._restore_workflow_checkpoint(workflow, storage)
        result = (
            await workflow.run(request.input, checkpoint_storage=storage)
            if storage is not None
            else await workflow.run(request.input)
        )
        return HostedRunResult(result)

    @staticmethod
    async def _restore_workflow_checkpoint(
        workflow: Workflow,
        storage: CheckpointStorage | None,
    ) -> None:
        """Rehydrate ``workflow`` from its latest checkpoint, if any.

        Shared between the blocking and streaming workflow paths so the
        restore step stays in lockstep across both — both must observe
        the same in-memory state when they apply the new input.

        If ``storage.get_latest`` returns ``None`` (no prior checkpoint
        recorded) the call is a benign no-op. A non-``None`` checkpoint
        whose stored events are empty (stale or partially-written
        ``checkpoint_id``) is logged at WARNING so operators can detect
        the silent-state-loss case without sifting through INFO logs.
        """
        if storage is None:
            return
        latest = await storage.get_latest(workflow_name=workflow.name)
        if latest is None:
            return
        # The blocking restore call is a no-op invocation that just
        # rehydrates state; the streaming path drains the same
        # restoration stream below to achieve the same effect.
        result = await workflow.run(checkpoint_id=latest.checkpoint_id, checkpoint_storage=storage)
        events = getattr(result, "events", None)
        if events is not None and not events:
            logger.warning(
                "workflow checkpoint restore produced zero events "
                "(workflow=%s checkpoint_id=%s) — state may not be rehydrated",
                workflow.name,
                latest.checkpoint_id,
            )

    def _invoke_workflow_stream(self, request: ChannelRequest) -> ResponseStream[AgentResponseUpdate, AgentResponse]:
        """Bridge ``Workflow.run(stream=True)`` to a channel-facing ``ResponseStream``.

        Wraps the workflow's ``ResponseStream[WorkflowEvent, WorkflowRunResult]``
        in a new ``ResponseStream[AgentResponseUpdate, AgentResponse]`` so
        channels can iterate it identically to an agent stream and apply
        their ``stream_update_hook`` callables.

        Mapping rules:

        - ``output`` events whose ``data`` is already an
          :class:`AgentResponseUpdate` (the common case for workflows
          containing :class:`AgentExecutor`) pass through unchanged.
        - ``output`` events with any other ``data`` are wrapped into a
          single-text-content :class:`AgentResponseUpdate`.
        - All other event types (``status``, ``executor_invoked``,
          ``superstep_*``, lifecycle, …) are filtered out — channels only
          care about user-visible text. Hooks can opt back in by inspecting
          ``raw_representation`` on the produced updates.

        The original :class:`WorkflowEvent` is stashed on
        ``AgentResponseUpdate.raw_representation`` so advanced consumers
        (telemetry, debug UIs) can recover the full workflow timeline.

        Checkpoint restoration (when ``checkpoint_location`` is set) runs
        before the input stream is opened so the new turn observes the
        restored state.
        """
        workflow: Workflow = self.target  # type: ignore[assignment]
        storage = self._resolve_checkpoint_storage(request)

        async def _bridge() -> AsyncIterator[AgentResponseUpdate]:
            # Same restore step the blocking path runs (see
            # ``_restore_workflow_checkpoint``) — kept inside the bridge
            # so the in-memory state is rehydrated lazily on first
            # iteration rather than at stream-construction time.
            async with self._workflow_lock:
                await self._restore_workflow_checkpoint_streaming(workflow, storage)
                workflow_stream = workflow.run(request.input, stream=True, checkpoint_storage=storage)
                try:
                    async for event in workflow_stream:
                        update = _workflow_event_to_update(event)
                        if update is not None:
                            yield update
                finally:
                    async with _suppress_already_consumed():
                        await workflow_stream.get_final_response()

        async def _finalize(updates: Sequence[AgentResponseUpdate]) -> AgentResponse:  # noqa: RUF029
            return AgentResponse.from_updates(updates)

        return ResponseStream[AgentResponseUpdate, AgentResponse](_bridge(), finalizer=_finalize)

    @staticmethod
    async def _restore_workflow_checkpoint_streaming(
        workflow: Workflow,
        storage: CheckpointStorage | None,
    ) -> None:
        """Streaming-path counterpart to :meth:`_restore_workflow_checkpoint`.

        ``Workflow.run(stream=True, checkpoint_id=...)`` returns a stream
        whose updates we don't care about — we just need the side-effect
        of rehydration. Drained inline so the new-input run that follows
        observes the restored state.

        A latest checkpoint that drains to zero events (stale or
        partially-written ``checkpoint_id``) is logged at WARNING so
        operators can detect the silent-state-loss case, mirroring the
        blocking helper.
        """
        if storage is None:
            return
        latest = await storage.get_latest(workflow_name=workflow.name)
        if latest is None:
            return
        drained = 0
        async for _ in workflow.run(
            stream=True,
            checkpoint_id=latest.checkpoint_id,
            checkpoint_storage=storage,
        ):
            drained += 1
        if drained == 0:
            logger.warning(
                "workflow checkpoint restore stream produced zero events "
                "(workflow=%s checkpoint_id=%s) — state may not be rehydrated",
                workflow.name,
                latest.checkpoint_id,
            )

    def _wrap_input(self, request: ChannelRequest) -> Message | list[Message]:
        """Promote ``request.input`` to ``Message``(s) carrying channel metadata.

        Channels deliver inputs as plain text, a single ``Message``, or a list
        of ``Message`` (e.g. a Responses-API request that includes a ``system``
        instruction plus the user turn). To preserve channel provenance and
        optional identity metadata on the persisted history record (and make it
        visible to context providers, evals, audits), we attach a ``hosting``
        block under ``additional_properties``. AF's
        ``Message.to_dict`` round-trips ``additional_properties`` through any
        ``HistoryProvider`` that serializes via ``to_dict`` (e.g.
        ``FileHistoryProvider``) and the framework explicitly does *not*
        forward these fields to model providers, so they are safe to attach.

        For a list of messages we attach the metadata to the LAST message that
        will be persisted (typically the user turn) — this keeps a single,
        searchable record of where the inbound message came from.
        """
        hosting_meta: dict[str, Any] = {"channel": request.channel}
        if request.identity is not None:
            hosting_meta["identity"] = {
                "channel": request.identity.channel,
                "native_id": request.identity.native_id,
                "attributes": dict(request.identity.attributes) if request.identity.attributes else {},
            }
        raw = request.input
        if isinstance(raw, Message):
            raw.additional_properties = {**(raw.additional_properties or {}), "hosting": hosting_meta}
            return raw
        if isinstance(raw, list) and raw and all(isinstance(m, Message) for m in raw):
            messages: list[Message] = [m for m in raw if isinstance(m, Message)]
            last = messages[-1]
            last.additional_properties = {**(last.additional_properties or {}), "hosting": hosting_meta}
            return messages
        # ``raw`` is typed as ``AgentRunInputs`` (str | Content | Message | Sequence[…]).
        # The remaining cases are str / Content / Mapping — wrap as a single user message.
        return Message(
            role="user",
            contents=[raw],  # type: ignore[list-item]
            additional_properties={"hosting": hosting_meta},
        )


__all__ = ["AgentFrameworkHost", "ChannelContext", "logger"]
