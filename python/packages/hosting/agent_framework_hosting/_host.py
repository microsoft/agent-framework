# Copyright (c) Microsoft. All rights reserved.

"""The :class:`AgentFrameworkHost` and its :class:`ChannelContext` bridge.

The host is a tiny Starlette wrapper:

- ``__init__`` accepts a hostable target (``SupportsAgentRun`` agent or
  ``Workflow``) and a sequence of channels.
- :meth:`AgentFrameworkHost.app` lazily builds a Starlette app by calling
  every channel's ``contribute`` and mounting the returned routes under
  the channel's ``path`` (empty path → mount at the app root).
- :class:`ChannelContext` exposes ``run`` / ``run_stream`` /
  ``deliver_response`` for channels to invoke; the host handles
  per-``isolation_key`` session caching, identity tracking, and
  :class:`ResponseTarget` fan-out.

Per SPEC-002 (and ADR-0026), the host is intentionally thin so the bulk
of channel-specific behaviour stays in the channel package. Identity
linking, link policies, response targets, background runs, and the like
are pluggable extensions that the future identity/foundry packages will
contribute on top of this surface.
"""

from __future__ import annotations

import logging
import os
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from contextlib import AbstractContextManager, ExitStack, asynccontextmanager
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
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import BaseRoute, Mount, Route
from starlette.types import ASGIApp, Receive, Scope, Send

from ._isolation import (
    ISOLATION_HEADER_CHAT,
    ISOLATION_HEADER_USER,
    IsolationKeys,
    reset_current_isolation_keys,
    set_current_isolation_keys,
)
from ._types import (
    Channel,
    ChannelIdentity,
    ChannelPush,
    ChannelRequest,
    DeliveryReport,
    HostedRunResult,
    ResponseTargetKind,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger("agent_framework.hosting")


def _workflow_output_to_text(value: Any) -> str:
    """Render a single workflow ``output`` payload as plain text.

    ``AgentResponse`` and ``AgentResponseUpdate`` carry text natively;
    everything else is best-effort ``str()``.
    """
    text = getattr(value, "text", None)
    if isinstance(text, str):
        return text
    return str(value)


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
    text = _workflow_output_to_text(payload)
    return AgentResponseUpdate(
        contents=[Content.from_text(text=text)],
        role="assistant",
        author_name=event.executor_id,
        raw_representation=event,
    )


@asynccontextmanager
async def _suppress_already_consumed() -> AsyncIterator[None]:  # noqa: RUF029
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
    except RuntimeError:
        # Documented benign cases: ``ResponseStream`` raises
        # ``RuntimeError("Inner stream not available")`` on certain
        # double-finalize paths, and async-iteration teardown of a
        # workflow whose tasks were already cancelled can surface
        # ``RuntimeError("Event loop is closed")`` here. Promoted from
        # ``debug`` to ``warning`` so production deploys see the
        # signal and a real bug doesn't masquerade as benign noise.
        logger.warning("workflow stream finalize raised RuntimeError; cleanup skipped", exc_info=True)
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

    def __init__(self, inner: Any, stack: ExitStack) -> None:
        self._inner = inner
        self._stack = stack
        self._closed = False

    def _close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._stack.close()

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
        try:
            async for item in self._inner:
                yield item
        finally:
            self._close()

    async def get_final_response(self) -> Any:
        try:
            return await self._inner.get_final_response()
        finally:
            self._close()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


class ChannelContext:
    """Host-owned bridge that channels call to invoke the target."""

    def __init__(self, host: AgentFrameworkHost) -> None:
        """Bind the context to its owning :class:`AgentFrameworkHost`.

        The host instance is the source of truth for the target, registered
        channels, identity stores, sessions, and lifecycle state. Channels
        only ever receive a context; they never see the host directly.
        """
        self._host = host

    @property
    def target(self) -> SupportsAgentRun | Workflow:
        """The hostable target the channel should invoke."""
        return self._host.target

    async def run(self, request: ChannelRequest) -> HostedRunResult:
        """Invoke the target for ``request`` and return a channel-neutral result."""
        return await self._host._invoke(request)  # pyright: ignore[reportPrivateUsage]

    def run_stream(self, request: ChannelRequest) -> ResponseStream[AgentResponseUpdate, AgentResponse]:
        """Invoke the target with ``stream=True`` and return the agent's ResponseStream.

        Channels iterate the stream directly (it acts like an AsyncGenerator)
        and are responsible for delivering updates to their wire protocol.
        Apply per-channel ``transform_hook`` callables during iteration to
        rewrite or drop individual updates before they hit the wire.
        """
        return self._host._invoke_stream(request)  # pyright: ignore[reportPrivateUsage]

    async def deliver_response(self, request: ChannelRequest, payload: HostedRunResult) -> DeliveryReport:
        """Resolve ``request.response_target`` and push ``payload`` to each destination.

        Returns a :class:`DeliveryReport` so the originating channel knows
        whether to render the agent reply on its own wire (``originating``
        included in or implied by the target) or just acknowledge dispatch.
        """
        return await self._host._deliver_response(request, payload)  # pyright: ignore[reportPrivateUsage]


class _FoundryIsolationASGIMiddleware:
    """Lift the two well-known Foundry isolation headers into a contextvar.

    The Foundry Hosted Agents runtime injects
    ``x-agent-{user,chat}-isolation-key`` on every inbound HTTP request.
    Storage providers that need partition-aware writes (notably
    :class:`FoundryHostedAgentHistoryProvider`) read those keys via
    :func:`get_current_isolation_keys` to avoid every channel having to
    parse Foundry-specific headers itself. We intentionally inspect
    only HTTP scopes; lifespan/websocket scopes are forwarded
    untouched. When neither header is present the contextvar stays at
    its default ``None``, so local-dev requests behave as before.
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
                warning is emitted).
        """
        self.target: SupportsAgentRun | Workflow = target
        self._is_workflow = isinstance(target, Workflow)
        self.channels = list(channels)
        self._debug = debug
        self._app: Starlette | None = None
        self._checkpoint_location: Path | CheckpointStorage | None = None
        if checkpoint_location is not None:
            if not self._is_workflow:
                logger.warning("checkpoint_location is set but target is not a Workflow; ignoring.")
            else:
                workflow: Workflow = target  # type: ignore[assignment]
                if workflow._runner_context.has_checkpointing():  # type: ignore[reportPrivateUsage]
                    raise RuntimeError(
                        "Workflow already has checkpoint storage configured "
                        "(WorkflowBuilder(checkpoint_storage=...)). The host "
                        "manages checkpoints when checkpoint_location is set; "
                        "remove one of the two configurations."
                    )
                if isinstance(checkpoint_location, (str, os.PathLike)):
                    self._checkpoint_location = Path(os.fspath(checkpoint_location))
                else:
                    # Anything else is treated as a CheckpointStorage instance.
                    # ``CheckpointStorage`` is a non-runtime-checkable Protocol,
                    # so we cannot ``isinstance``-check it directly.
                    self._checkpoint_location = checkpoint_location
        # Per-isolation_key session cache. The real spec backs this with a
        # pluggable session store; this base host keeps it in-process.
        self._sessions: dict[str, Any] = {}
        # ``isolation_key -> active session_id``. Normally identical to the
        # isolation_key, but ``reset_session`` rotates this to a fresh id so
        # the next turn starts a new ``AgentSession`` while the old history
        # remains on disk under its original session_id.
        self._session_aliases: dict[str, str] = {}
        # Per-isolation_key identity registry: which channels we've seen this
        # user on, and which native_id they used on each. Powers
        # ResponseTarget.active / .channel(name) / .channels([...]) /
        # .all_linked.
        # Shape: { isolation_key: { channel_name: ChannelIdentity } }.
        self._identities: dict[str, dict[str, ChannelIdentity]] = {}
        # (isolation_key -> last-seen channel name) for ResponseTarget.active.
        self._active: dict[str, str] = {}

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
            import asyncio
            from typing import cast as _cast

            from hypercorn.asyncio import (  # pyright: ignore[reportMissingImports]
                serve as _hypercorn_serve,  # pyright: ignore[reportUnknownVariableType]
            )
            from hypercorn.config import Config  # pyright: ignore[reportMissingImports, reportUnknownVariableType]
        except ImportError as exc:  # pragma: no cover - exercised at runtime
            raise RuntimeError(
                "AgentFrameworkHost.serve() requires hypercorn. "
                "Install with `pip install agent-framework-hosting[serve]` or `pip install hypercorn`."
            ) from exc

        config = Config()  # pyright: ignore[reportUnknownVariableType]
        config.bind = [f"{host}:{port}"]  # pyright: ignore[reportUnknownMemberType]
        config.workers = workers  # pyright: ignore[reportUnknownMemberType]
        for key, value in config_kwargs.items():
            setattr(config, key, value)  # pyright: ignore[reportUnknownArgumentType]

        # Touch ``self.app`` so the lifespan startup log fires once before
        # we hand off to hypercorn — gives a single, readable banner of
        # what the host is exposing without requiring channels to log
        # individually.
        app = self.app
        self._log_startup(host=host, port=port, workers=workers)

        # ``hypercorn.asyncio.serve`` has a complex partially-typed signature
        # (multiple ASGI/WSGI app overloads) and its ``Scope`` definition
        # diverges from Starlette's; cast both sides to ``Any`` to keep the
        # call site readable without sprinkling per-error suppressions.
        serve_callable = _cast(Any, _hypercorn_serve)
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

    def _log_startup(self, *, host: str, port: int, workers: int) -> None:
        """Emit a single human-friendly startup banner.

        Mirrors the ``AgentServerHost`` convention from
        ``azure.ai.agentserver.core``: one INFO line that captures the
        target type, every channel + its mount path, the bind address,
        whether we're running inside a Foundry Hosted Agents container,
        and the worker count. Keeps log noise low while still giving an
        operator a single grep-able anchor when triaging.
        """
        target_kind = "Workflow" if isinstance(self.target, Workflow) else type(self.target).__name__
        target_name = getattr(self.target, "name", None) or target_kind
        channels_repr = ", ".join(
            f"{ch.name}@{ch.path or '/'}"  # blank path means "mounted at root"
            for ch in self.channels
        )
        is_hosted = bool(os.environ.get("FOUNDRY_HOSTING_ENVIRONMENT"))
        logger.info(
            "AgentFrameworkHost starting: target=%s (%s) bind=%s:%d workers=%d hosted=%s channels=[%s]",
            target_name,
            target_kind,
            host,
            port,
            workers,
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
            # An empty path means "mount at the app root" — useful for single-channel hosts
            # that don't want a prefix (e.g. ResponsesChannel exposing POST /responses directly).
            if contribution.routes:
                if channel.path:
                    routes.append(Mount(channel.path, routes=list(contribution.routes)))
                else:
                    routes.extend(contribution.routes)
            on_startup.extend(contribution.on_startup)
            on_shutdown.extend(contribution.on_shutdown)

        @asynccontextmanager
        async def lifespan(_app: Starlette) -> AsyncIterator[None]:
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

        return Starlette(
            debug=self._debug,
            routes=routes,
            lifespan=lifespan,
            middleware=[Middleware(_FoundryIsolationASGIMiddleware)],
        )

    def _build_run_kwargs(self, request: ChannelRequest) -> dict[str, Any]:
        # The full spec resolves a ChannelSession into an AgentSession here,
        # honors session_mode, and consults LinkPolicy / ResponseTarget. This
        # base host keys a per-isolation_key AgentSession off the channel's
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
                    new_session = self.target.create_session(  # pyright: ignore[reportAttributeAccessIssue, reportUnknownVariableType, reportUnknownMemberType]
                        session_id=session_id
                    )
                    session = self._sessions.setdefault(isolation_key, new_session)  # pyright: ignore[reportUnknownArgumentType]

        run_kwargs: dict[str, Any] = {}
        if session is not None:
            run_kwargs["session"] = session
        if request.options:
            run_kwargs["options"] = request.options
        return run_kwargs

    def _log_incoming(self, request: ChannelRequest, *, stream: bool) -> None:
        """Emit a one-line INFO summary for every incoming target invocation.

        When ``debug=True`` is set on the host, also dump the channel-native
        settings the channel attached to the ``ChannelRequest`` — ``options``
        (the ChatOptions-shaped fields the channel parsed from its protocol
        payload, e.g. temperature/tools/tool_choice for Responses), plus
        ``attributes`` / ``metadata`` (the channel's protocol-specific bag,
        e.g. ``chat_id`` / ``callback_query_id`` for Telegram).
        """
        isolation_key = request.session.isolation_key if request.session is not None else None
        logger.info(
            "channel=%s op=%s stream=%s session=%s session_mode=%s",
            request.channel,
            request.operation,
            stream,
            isolation_key,
            request.session_mode,
        )
        logger.debug(
            "  ↳ options=%s attributes=%s metadata=%s",
            dict(request.options) if request.options else {},
            dict(request.attributes) if request.attributes else {},
            dict(request.metadata) if request.metadata else {},
        )

    def _flat_context_providers(self) -> list[Any]:
        """Flatten ``target.context_providers`` one level for duck-typed hooks.

        ``ContextProviderBase`` aggregates child providers under a
        ``providers`` attribute when wrapped (e.g. by ``ChatClientAgent``).
        We descend one level so the host catches both styles without
        forcing a particular wiring on the agent.
        """
        providers = getattr(self.target, "context_providers", None) or ()
        flat: list[Any] = []
        for entry in providers:
            children = getattr(entry, "providers", None)
            if children:
                flat.extend(children)
            else:
                flat.append(entry)
        return flat

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

        flat: list[Any] = self._flat_context_providers()

        for provider in flat:
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

    async def _invoke(self, request: ChannelRequest) -> HostedRunResult:
        self._log_incoming(request, stream=False)
        self._record_identity(request)
        if self._is_workflow:
            return await self._invoke_workflow(request)
        run_kwargs = self._build_run_kwargs(request)
        with self._bind_request_context(request):
            # ``_is_workflow`` is False here so ``self.target`` is an
            # ``Agent``-shaped target whose ``.run`` returns
            # :class:`AgentResponse`. Narrow back to keep ``result.text``
            # well-typed without conditional imports of ``Agent``.
            agent_target = cast("SupportsAgentRun", self.target)
            result = await agent_target.run(self._wrap_input(request), **run_kwargs)
        return HostedRunResult(text=result.text)

    def _invoke_stream(self, request: ChannelRequest) -> ResponseStream[AgentResponseUpdate, AgentResponse]:
        self._log_incoming(request, stream=True)
        self._record_identity(request)
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
        return _BoundResponseStream(  # type: ignore[return-value]
            self.target.run(self._wrap_input(request), stream=True, **run_kwargs),
            binder,
        )

    def _resolve_checkpoint_storage(self, request: ChannelRequest) -> CheckpointStorage | None:
        """Build (or return) the per-request checkpoint storage, or ``None``.

        Returns ``None`` when no ``checkpoint_location`` is configured or
        when the request lacks a stable session key — without a key we
        cannot scope checkpoints per conversation, and we'd rather skip
        checkpointing than pollute a single shared store.
        """
        if self._checkpoint_location is None:
            return None
        if request.session is None or not request.session.isolation_key:
            return None
        if isinstance(self._checkpoint_location, Path):
            return FileCheckpointStorage(str(self._checkpoint_location / request.session.isolation_key))
        # Caller-supplied storage — used as-is; caller owns scoping.
        return self._checkpoint_location

    async def _invoke_workflow(self, request: ChannelRequest) -> HostedRunResult:
        """Dispatch to ``Workflow.run`` and collapse outputs into a ``HostedRunResult``.

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
        """
        # Workflows do not own session state in the agent sense and do not
        # accept ``session=`` / ``options=`` kwargs. The channel's run_hook is
        # the seam for any per-run customization; nothing flows through here.
        workflow: Workflow = self.target  # type: ignore[assignment]
        storage = self._resolve_checkpoint_storage(request)
        if storage is not None:
            latest = await storage.get_latest(workflow_name=workflow.name)
            if latest is not None:
                # Restore in-memory state from the most recent checkpoint
                # before applying the new input.
                await workflow.run(checkpoint_id=latest.checkpoint_id, checkpoint_storage=storage)
            result = await workflow.run(request.input, checkpoint_storage=storage)
        else:
            result = await workflow.run(request.input)
        outputs = result.get_outputs()
        text = "\n".join(_workflow_output_to_text(o) for o in outputs) if outputs else ""
        return HostedRunResult(text=text)

    def _invoke_workflow_stream(self, request: ChannelRequest) -> ResponseStream[AgentResponseUpdate, AgentResponse]:
        """Bridge ``Workflow.run(stream=True)`` to a channel-facing ``ResponseStream``.

        Wraps the workflow's ``ResponseStream[WorkflowEvent, WorkflowRunResult]``
        in a new ``ResponseStream[AgentResponseUpdate, AgentResponse]`` so
        channels can iterate it identically to an agent stream and apply
        their ``stream_transform_hook`` callables.

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

        async def _maybe_restore() -> None:
            if storage is None:
                return
            latest = await storage.get_latest(workflow_name=workflow.name)
            if latest is None:
                return
            # Drain the restoration stream so the no-op invocation actually
            # rehydrates state before the real run starts.
            async for _ in workflow.run(
                stream=True,
                checkpoint_id=latest.checkpoint_id,
                checkpoint_storage=storage,
            ):
                pass

        async def _bridge() -> AsyncIterator[AgentResponseUpdate]:
            await _maybe_restore()
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

    def _wrap_input(self, request: ChannelRequest) -> Message | list[Message]:
        """Promote ``request.input`` to ``Message``(s) carrying channel metadata.

        Channels deliver inputs as plain text, a single ``Message``, or a list
        of ``Message`` (e.g. a Responses-API request that includes a ``system``
        instruction plus the user turn). To preserve channel provenance +
        identity + ``response_target`` on the persisted history record (and
        make it visible to context providers, evals, audits), we attach a
        ``hosting`` block under ``additional_properties``. AF's
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
        target = request.response_target
        hosting_meta["response_target"] = {
            "kind": target.kind.value,
            "targets": list(target.targets),
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

    def _record_identity(self, request: ChannelRequest) -> None:
        """Update the per-``isolation_key`` identity registry + active-channel hint.

        Called on every successful resolve. ``ResponseTarget.active``
        consumes ``self._active``; ``ResponseTarget.channel(name)`` /
        ``.channels([...])`` / ``.all_linked`` consume ``self._identities``.
        """
        if request.identity is None or request.session is None:
            return
        key = request.session.isolation_key
        if not key:
            return
        self._identities.setdefault(key, {})[request.identity.channel] = request.identity
        self._active[key] = request.identity.channel

    async def _deliver_response(self, request: ChannelRequest, payload: HostedRunResult) -> DeliveryReport:
        """Resolve ``request.response_target`` and call ``ChannelPush.push`` on each.

        Per SPEC-002 §"ResponseTarget": for any non-``originating`` target,
        the originating channel returns an acknowledgment and the actual
        agent reply lands on the destination channel(s). When a destination
        cannot be resolved (no known native id) or doesn't implement
        ``ChannelPush``, it is dropped and surfaced in
        :class:`DeliveryReport.skipped`. If every destination drops, we
        fall back to delivering on the originating channel (matching the
        spec's policy default).
        """
        target = request.response_target
        kind = target.kind

        # Fast paths for the trivial variants.
        if kind == ResponseTargetKind.ORIGINATING:
            return DeliveryReport(include_originating=True)
        if kind == ResponseTargetKind.NONE:
            # Background-only — drop the reply on the floor for now (no
            # ContinuationToken in the prototype).
            return DeliveryReport(include_originating=False)

        # Build the destination set.
        include_originating = False
        # Each entry is (channel_name, identity_override_or_None_to_lookup).
        destinations: list[tuple[str, ChannelIdentity | None]] = []
        isolation_key = request.session.isolation_key if request.session is not None else None
        known = self._identities.get(isolation_key or "", {})

        if kind == ResponseTargetKind.ACTIVE:
            active = self._active.get(isolation_key or "")
            if active is None or active == request.channel:
                # Fall back to originating when there's no other active
                # channel known (matches the "first message" case).
                return DeliveryReport(include_originating=True)
            destinations.append((active, known.get(active)))

        elif kind == ResponseTargetKind.ALL_LINKED:
            for channel_name, identity in known.items():
                if channel_name == request.channel:
                    include_originating = True
                    continue
                destinations.append((channel_name, identity))
            if not destinations and not include_originating:
                # No links recorded yet — fall back.
                return DeliveryReport(include_originating=True)

        elif kind == ResponseTargetKind.CHANNELS:
            for entry in target.targets:
                if entry == "originating":
                    include_originating = True
                    continue
                if ":" in entry:
                    channel_name, _, native_id = entry.partition(":")
                    if channel_name == request.channel:
                        # Pointing the originating channel at itself with a
                        # specific native id — treat as "include
                        # originating" since the channel will reply on its
                        # own wire to that user anyway.
                        include_originating = True
                        continue
                    destinations.append((channel_name, ChannelIdentity(channel=channel_name, native_id=native_id)))
                else:
                    if entry == request.channel:
                        include_originating = True
                        continue
                    destinations.append((entry, known.get(entry)))

        # Dispatch.
        by_name = {ch.name: ch for ch in self.channels}
        pushed: list[str] = []
        skipped: list[str] = []
        # ``(target_token, error_summary)`` for each destination whose
        # ``ChannelPush.push`` raised. Distinct from ``skipped`` so the
        # caller can tell an outage (every destination push raised) from
        # the documented "no link recorded" drop (no identity yet
        # mapped to that channel for this isolation_key).
        failed: list[tuple[str, str]] = []
        for channel_name, dest_identity in destinations:
            channel = by_name.get(channel_name)
            token = f"{channel_name}:{dest_identity.native_id}" if dest_identity is not None else channel_name
            if channel is None:
                logger.warning("deliver_response: no channel named %r (target=%s)", channel_name, token)
                skipped.append(token)
                continue
            if not isinstance(channel, ChannelPush):
                logger.warning(
                    "deliver_response: channel %r does not implement ChannelPush (target=%s)",
                    channel_name,
                    token,
                )
                skipped.append(token)
                continue
            if dest_identity is None:
                logger.warning(
                    "deliver_response: no known identity for isolation_key=%s on channel=%s",
                    isolation_key,
                    channel_name,
                )
                skipped.append(token)
                continue
            try:
                await channel.push(dest_identity, payload)
            except Exception as exc:
                logger.exception("deliver_response: push failed for target=%s", token)
                failed.append((token, f"{type(exc).__name__}: {exc}"))
                continue
            pushed.append(token)
            logger.info("deliver_response: pushed to %s (%d chars)", token, len(payload.text))

        if not pushed and not include_originating:
            # Spec policy: if every destination drops *without ever
            # raising*, deliver to originating so the user gets a
            # response. When the drop reason is a push outage (every
            # ``failed`` entry), we don't fall back — the originating
            # channel can inspect ``DeliveryReport.failed`` and decide
            # whether to surface a degraded reply itself rather than
            # double-delivering on a flaky link.
            if failed:
                logger.warning(
                    "deliver_response: every destination push raised — surfacing failures via "
                    "DeliveryReport.failed (no originating fallback)"
                )
            else:
                logger.warning("deliver_response: every destination dropped — falling back to originating")
                include_originating = True

        return DeliveryReport(
            include_originating=include_originating,
            pushed=tuple(pushed),
            skipped=tuple(skipped),
            failed=tuple(failed),
        )


__all__ = ["AgentFrameworkHost", "ChannelContext", "logger"]
