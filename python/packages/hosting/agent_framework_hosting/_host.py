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

import asyncio
import logging
import os
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping, Sequence
from contextlib import AbstractContextManager, ExitStack, asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, cast

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

from ._authorization import (
    Allowed,
    AllowlistDecision,
    AuthorizationContext,
    AuthorizationOutcome,
    ChannelConfigurationError,
    Denied,
    IdentityAllowlist,
)
from ._isolation import (
    ISOLATION_HEADER_CHAT,
    ISOLATION_HEADER_USER,
    IsolationKeys,
    reset_current_isolation_keys,
    set_current_isolation_keys,
)
from ._persistence import normalize_state_dir
from ._runner import InProcessTaskRunner
from ._state_store import SessionsStateStore, build_session_dicts
from ._types import (
    Channel,
    ChannelIdentity,
    ChannelPush,
    ChannelPushCodec,
    ChannelRequest,
    ChannelResponseContext,
    ChannelResponseHook,
    DurableTaskPayloadMode,
    DurableTaskRunner,
    HostedRunResult,
    HostStatePaths,
    PushPayloadNotSerializable,
    ResponseTargetKind,
    apply_response_hook,
)

if TYPE_CHECKING:
    from agent_framework._workflows._workflow import WorkflowRunResult

logger = logging.getLogger("agent_framework.hosting")


# Environment markers that auto-detect ``runtime_mode="ephemeral"``. Order
# matters only for telemetry — the first match wins and is logged at
# startup. Adding a new marker is a non-breaking change; consumers can
# always override via the ``runtime_mode`` constructor parameter.
_EPHEMERAL_RUNTIME_MARKERS: tuple[str, ...] = (
    "FOUNDRY_HOSTING_ENVIRONMENT",
    "AZURE_FUNCTIONS_ENVIRONMENT",
    "AWS_LAMBDA_FUNCTION_NAME",
)


RuntimeMode = Literal["long_running", "ephemeral"]


def _detect_runtime_mode(env: Mapping[str, str] | None = None) -> tuple[RuntimeMode, str | None]:
    """Inspect deployment markers and return ``(mode, matched_marker_or_None)``.

    Pure / side-effect-free so the host can call it once at construction
    and tests can pass a synthetic env. ``env`` defaults to
    :data:`os.environ`. Returns ``"long_running"`` when nothing matches —
    that's the sensible default for local dev and always-on container
    deployments.
    """
    source = env if env is not None else os.environ
    for marker in _EPHEMERAL_RUNTIME_MARKERS:
        if source.get(marker):
            return ("ephemeral", marker)
    return ("long_running", None)


# Internal name the host uses when registering the push handler on the
# durable task runner. Exposed as a module constant so adapter packages
# (and the future background-run wiring under req #14) can use the same
# name for cross-runner observability.
HOSTING_PUSH_TASK_NAME = "hosting.push"


def _flatten_allowlists(allowlist: IdentityAllowlist) -> tuple[IdentityAllowlist, ...]:
    """Walk an allowlist tree to expose nested :class:`IdentityAllowlist` instances.

    Used by :meth:`AgentFrameworkHost._validate_channel_authorization`
    to inspect every leaf so type-checks like
    ``NativeIdAllowlist(channel=<unknown>)`` can be detected even
    when buried inside :class:`AnyOfAllowlists` / :class:`AllOfAllowlists`.
    """
    children = getattr(allowlist, "_children", None)
    if children:
        flat: list[IdentityAllowlist] = [allowlist]
        for child in children:
            flat.extend(_flatten_allowlists(child))
        return tuple(flat)
    return (allowlist,)


def _checkpoint_path_for_isolation_key(root: Path, isolation_key: str) -> Path:
    r"""Return ``root / isolation_key`` after rejecting path-traversal patterns.

    Isolation keys are intentionally caller-controlled: they originate from
    inbound HTTP headers (``x-agent-{user,chat}-isolation-key`` injected by
    the Foundry runtime), from channel-supplied derivations such as
    ``telegram:<chat_id>`` / ``entra:<oid>``, or from a channel ``run_hook``
    that may read body fields. Joining such a value into a filesystem path
    without validation is CWE-22: a value such as ``../../../etc/foo`` or
    ``\\foo`` (Windows UNC) would let the resulting checkpoint directory
    escape the configured root.

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

    async def run(self, request: ChannelRequest) -> HostedRunResult[Any]:
        """Invoke the target for ``request`` and return a channel-neutral result.

        For agent targets the return type narrows to
        ``HostedRunResult[AgentResponse]``; for workflow targets to
        ``HostedRunResult[WorkflowRunResult]``. The static return is left
        as ``HostedRunResult[Any]`` because :class:`ChannelContext` is
        agnostic to which target shape the host was constructed with;
        channels narrow at the call site if they need it.
        """
        return await self._host._invoke(request)  # pyright: ignore[reportPrivateUsage]

    def run_stream(self, request: ChannelRequest) -> ResponseStream[AgentResponseUpdate, AgentResponse]:
        """Invoke the target with ``stream=True`` and return the agent's ResponseStream.

        Channels iterate the stream directly (it acts like an AsyncGenerator)
        and are responsible for delivering updates to their wire protocol.
        Apply per-channel ``transform_hook`` callables during iteration to
        rewrite or drop individual updates before they hit the wire.
        """
        return self._host._invoke_stream(request)  # pyright: ignore[reportPrivateUsage]

    async def deliver_response(
        self,
        request: ChannelRequest,
        payload: HostedRunResult[Any],
    ) -> bool:
        """Resolve ``request.response_target`` and push ``payload`` to each destination.

        Returns ``True`` when the originating channel should render the
        agent reply on its own wire (i.e. the resolved target included
        the originating channel — explicitly via
        ``ResponseTarget.originating``, implicitly via
        ``ResponseTarget.channels(["originating", ...])``, or as the
        host's "every destination dropped, fall back to originating"
        recovery path). Returns ``False`` when the reply is fanned out
        purely to non-originating destinations (or
        :data:`ResponseTarget.none` suppresses the reply entirely) — in
        which case the originating channel typically responds with a
        bare ack.

        Per-destination push outcomes (scheduled, retried, terminally
        failed) live in the durable task runner's own log; this method
        emits structured log entries for every resolution-time skip and
        every schedule-time outage so operators have a single grep
        anchor for "where did my reply go?".
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
        runtime_mode: RuntimeMode | None = None,
        durable_task_runner: DurableTaskRunner | None = None,
        allow_in_process_runner: bool = False,
        default_allowlist: IdentityAllowlist | None = None,
        identity_linker: Any = None,
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

        Keyword Args:
            runtime_mode: Hint that drives the *defaults* for runtime-shape
                dependent components (currently the durable task runner,
                and — by extension — anything that wants to know whether
                the process is expected to outlive a single request).
                ``"long_running"`` (containers, OpenClaw-style always-on
                deployments, local dev) → in-process / in-memory defaults.
                ``"ephemeral"`` (Foundry Hosted Agents, Azure Functions,
                AWS Lambda) → the host expects a durable runner to be
                supplied via ``durable_task_runner`` and logs a warning
                otherwise. ``None`` (the default) auto-detects from
                deployment environment markers (currently
                ``FOUNDRY_HOSTING_ENVIRONMENT``, ``AZURE_FUNCTIONS_ENVIRONMENT``,
                ``AWS_LAMBDA_FUNCTION_NAME``); falls back to
                ``"long_running"``.
            durable_task_runner: The runner used to dispatch
                non-originating push fan-out. Defaults to a process-local
                :class:`InProcessTaskRunner` (asyncio + bounded retry, no
                persistence) — appropriate for ``runtime_mode="long_running"``
                deployments. Ephemeral deployments should pass a durable
                adapter (e.g. ``agent-framework-hosting-durabletask``,
                or a Foundry-native adapter once available) so scheduled
                pushes survive process restarts.
            allow_in_process_runner: Opt-in escape hatch that allows
                ``runtime_mode="ephemeral"`` to be paired with the
                default in-process runner. Without this flag, the host
                refuses to start in ephemeral mode without an explicit
                ``durable_task_runner`` because the failure mode —
                non-originating pushes silently lost on process recycle —
                is the worst class of production bug (works in light
                testing, drops work under load / lifecycle events).
                Useful for local dev that wants to exercise ephemeral
                code paths without standing up a durable backend; **not**
                appropriate for production.
            default_allowlist: Host-level fallback applied to every
                channel that leaves ``allowlist="inherit"``. ``None``
                (the default) means the channel is open unless it sets
                its own ``allowlist``. Channels can opt out of the host
                default by setting ``allowlist=None`` explicitly.
            identity_linker: Reserved for the Wave-2 :class:`IdentityLinker`
                stack. Wave 1 only inspects this for the startup
                validator: channels with ``require_link=True`` or
                allowlists that declare ``requires_linked_claims=True``
                require a linker to be configured, otherwise the host
                would silently deny everyone.
            state_dir: Opt-in disk persistence for host-managed state.
                When set, the host writes the in-process task runner's
                pending queue and the session-related dicts
                (``_session_aliases``, ``_active``, ``_identities``) to
                a :mod:`diskcache`-backed store under ``state_dir`` and
                replays the runner queue on next startup. Accepts:

                * ``None`` (default) — everything stays in memory; the
                  process owns its state and loses it on exit. Matches
                  today's behaviour exactly.
                * ``str`` / :class:`os.PathLike` — the host creates
                  default subfolders ``state_dir/runner/`` and
                  ``state_dir/sessions/`` for the runner queue and the
                  session dicts respectively. Recommended for most
                  long-running-host deployments — one path, no extra
                  config, both components persist together.
                * :class:`HostStatePaths` typed dict / plain
                  ``Mapping`` — per-component overrides for callers that
                  want each component on a different volume (fast local
                  SSD for the runner, network-attached volume for
                  sessions, …). Components missing from the mapping
                  fall back to in-memory.

                Requires the optional ``diskcache`` dependency (install
                with ``pip install 'agent-framework-hosting[disk]'``).
                Each enabled component acquires an OS-level advisory
                lock on its directory; a second host pointed at the
                same paths raises :class:`RuntimeError` at construction
                so two processes do not double-execute queued tasks.
                When ``durable_task_runner`` is supplied explicitly, the
                runner sub-path is ignored — the caller owns the
                runner's persistence story.
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
        # Disk persistence — normalise the per-component map up front
        # so the runner and session-store paths are resolved before any
        # component is built. ``None`` (default) means everything stays
        # in memory.
        self._state_paths: dict[str, Path | None] = normalize_state_dir(state_dir)
        # Runtime mode + durable task runner. We resolve mode first
        # because the warning-on-ephemeral-without-runner only fires
        # when both are at their defaults.
        if runtime_mode is None:
            resolved_mode, matched_marker = _detect_runtime_mode()
            self._runtime_mode: RuntimeMode = resolved_mode
            self._runtime_mode_source: str = (
                f"auto-detected from {matched_marker}" if matched_marker is not None else "auto-detected default"
            )
        else:
            self._runtime_mode = runtime_mode
            self._runtime_mode_source = "explicit"
        if durable_task_runner is None:
            if self._runtime_mode == "ephemeral" and not allow_in_process_runner:
                raise RuntimeError(
                    "AgentFrameworkHost is running in ephemeral runtime mode "
                    f"({self._runtime_mode_source}) without a durable_task_runner. "
                    "Non-originating push deliveries would be lost on process "
                    "recycle. Pass `durable_task_runner=...` (e.g. an "
                    "agent-framework-hosting-durabletask runner) for production, "
                    "or set `allow_in_process_runner=True` to opt out of this "
                    "check (e.g. for local dev exercising ephemeral code paths)."
                )
            # When state_dir["runner"] is set, the default in-process
            # runner persists its queue to disk so a long-running host
            # can replay in-flight pushes after a crash / restart.
            self._durable_task_runner: DurableTaskRunner = InProcessTaskRunner(
                state_dir=self._state_paths.get("runner"),
            )
            self._owns_runner = True
            if self._runtime_mode == "ephemeral":
                logger.warning(
                    "AgentFrameworkHost is running in ephemeral runtime mode "
                    "with the default InProcessTaskRunner (allow_in_process_runner=True). "
                    "Non-originating push deliveries will be lost if the process is "
                    "recycled mid-flight — this configuration is intended for local dev only."
                )
        else:
            self._durable_task_runner = durable_task_runner
            self._owns_runner = False
            if self._state_paths.get("runner") is not None:
                # The caller supplied both a runner and a runner state
                # path. The path would only have applied to the default
                # in-process runner; surface the misconfig so it doesn't
                # silently become a no-op.
                logger.warning(
                    "state_dir['runner'] is set but a durable_task_runner was "
                    "supplied explicitly; the runner sub-path is ignored — "
                    "configure persistence on the runner instance directly."
                )
        # Validate the runner / push-codec pairing eagerly: a JSON-mode
        # durable runner cannot persist payloads for a push-capable
        # channel that has no codec. Failing here makes the misconfig
        # visible at process start rather than on first push.
        self._validate_runner_codec_pairing()
        # Register the internal push handler eagerly so it is available
        # whether callers invoke ``_deliver_response`` directly (e.g.
        # tests) or through the lifespan-managed ASGI app. Doing this
        # in ``__init__`` is safe because runner handler registration
        # has no I/O — it only associates a name with a callable.
        self._durable_task_runner.register(HOSTING_PUSH_TASK_NAME, self._handle_push_task)
        # Per-isolation_key session cache. The real spec backs this with a
        # pluggable session store; this base host keeps it in-process.
        # NOTE: live ``AgentSession`` objects are NOT persisted to disk
        # — the history provider rehydrates them from its own store on
        # the next turn. ``state_dir`` only persists the lightweight
        # pickle-friendly bookkeeping below.
        self._sessions: dict[str, Any] = {}
        # Open the disk-backed sessions store first when persistence is
        # on; the three persisted dicts share the same cache + lock to
        # minimise file handles and acquisition cost.
        sessions_path = self._state_paths.get("sessions")
        self._sessions_store: SessionsStateStore | None
        if sessions_path is not None:
            self._sessions_store = SessionsStateStore(sessions_path)
            # ``isolation_key -> active session_id``. Normally identical to the
            # isolation_key, but ``reset_session`` rotates this to a fresh id so
            # the next turn starts a new ``AgentSession`` while the old history
            # remains on disk under its original session_id. Persisted so a
            # rotation survives a restart.
            aliases_dict, active_dict, identities_dict = build_session_dicts(self._sessions_store)
            self._session_aliases: dict[str, str] = aliases_dict
            # (isolation_key -> last-seen channel name) for ResponseTarget.active.
            self._active: dict[str, str] = active_dict
            # Per-isolation_key identity registry: which channels we've seen this
            # user on, and which native_id they used on each. Powers
            # ResponseTarget.active / .channel(name) / .channels([...]) /
            # .all_linked.
            # Shape: { isolation_key: { channel_name: ChannelIdentity } }.
            self._identities: dict[str, dict[str, ChannelIdentity]] = identities_dict
        else:
            self._sessions_store = None
            self._session_aliases = {}
            self._active = {}
            self._identities = {}
        # Set by ``serve()`` so the lifespan startup handler doesn't
        # double-log the banner; remains ``False`` when callers mount
        # ``host.app`` under their own ASGI server.
        self._startup_logged: bool = False
        # Authorization seam (Wave 1: types + validator + native-id
        # allowlists; the full pipeline lands with the linker).
        self._default_allowlist: IdentityAllowlist | None = default_allowlist
        self._identity_linker: Any = identity_linker
        self._validate_channel_authorization()

    @property
    def app(self) -> Starlette:
        """Lazily build (and cache) the Starlette application."""
        if self._app is None:
            self._app = self._build_app()
        return self._app

    def _validate_runner_codec_pairing(self) -> None:
        """Refuse to start when a JSON-mode runner is paired with codec-less push channels.

        A JSON-mode durable runner (``payload_mode=JSON``) persists every
        scheduled task's payload so it survives process restarts. The
        host's ``hosting.push`` payload includes a
        :class:`HostedRunResult` containing the full agent / workflow
        output, which cannot be JSON-serialised without help from the
        destination channel. Push-capable channels therefore must
        declare a :class:`ChannelPushCodec` (a duck-typed
        ``push_codec`` attribute on the channel) when paired with a
        JSON-mode runner.

        Object-mode runners (the default in-process runner) accept live
        Python references and skip this check.
        """
        mode = getattr(self._durable_task_runner, "payload_mode", DurableTaskPayloadMode.OBJECT)
        if mode != DurableTaskPayloadMode.JSON:
            return
        missing: list[str] = []
        for channel in self.channels:
            if not isinstance(channel, ChannelPush):
                # Channels that don't implement push are never scheduled,
                # so a missing codec is fine.
                continue
            codec = getattr(channel, "push_codec", None)
            if codec is None:
                missing.append(channel.name)
        if missing:
            raise RuntimeError(
                "Durable task runner declares payload_mode=JSON, but the following "
                "push-capable channels have no `push_codec` attribute and cannot "
                "be serialised for persistence: "
                f"{', '.join(missing)}. Add a ChannelPushCodec to each channel "
                "or switch to an object-mode runner (e.g. InProcessTaskRunner)."
            )

    def _resolve_channel_allowlist(self, channel: Channel) -> IdentityAllowlist | None:
        """Apply the ``"inherit"`` / ``None`` / explicit semantics.

        - ``"inherit"`` (default) → host's ``default_allowlist``.
        - ``None`` → explicitly open (carve-out inside a locked host).
        - any other value → use as-is.
        """
        raw: Any = getattr(channel, "allowlist", "inherit")
        if raw == "inherit":
            return self._default_allowlist
        # ``None`` and concrete allowlists both pass through unchanged;
        # the caller (``authorize``) treats ``None`` as "open".
        return cast("IdentityAllowlist | None", raw)

    def _validate_channel_authorization(self) -> None:
        """Reject configurations that would silently deny every user.

        Runs three rules (see spec § "Configuration validation"):

        1. If a channel's resolved allowlist declares
           ``requires_linked_claims=True``, the channel must either set
           ``require_link=True`` or declare
           ``emits_verified_claims=True`` — otherwise no verified
           claims will ever reach :meth:`evaluate` and the allowlist
           would always ``ABSTAIN`` / ``DENY``.
        2. If any channel has ``require_link=True``, an
           ``identity_linker`` must be configured. Wave 1 does not
           ship a linker, so this rule fires whenever a channel
           opts into link enforcement without one. Silent
           deny-everyone is the worst possible default.
        3. ``NativeIdAllowlist(channel=<other>)`` must reference a
           channel name that exists on this host — typo-detection.
        """
        known_channels = {c.name for c in self.channels}
        for channel in self.channels:
            allowlist = self._resolve_channel_allowlist(channel)
            require_link = bool(getattr(channel, "require_link", False))
            emits_claims = bool(getattr(channel, "emits_verified_claims", False))
            # Rule #2: require_link without a linker.
            if require_link and self._identity_linker is None:
                raise ChannelConfigurationError(
                    f"Channel '{channel.name}' has require_link=True but no "
                    "identity_linker is configured on the host. Configure one or "
                    "remove require_link=True (silent deny-everyone is rejected)."
                )
            if allowlist is None:
                continue
            # Rule #1: claim-dependent allowlist needs a claim source.
            if getattr(allowlist, "requires_linked_claims", False) and not (require_link or emits_claims):
                raise ChannelConfigurationError(
                    f"Channel '{channel.name}' has an allowlist that requires "
                    "verified IdP claims (requires_linked_claims=True) but the "
                    "channel neither sets require_link=True nor emits verified "
                    "claims natively. Configure a source of verified claims for "
                    "the allowlist (silent deny-everyone is rejected)."
                )
            # Rule #3: native-id allowlists pointing at unknown channels.
            for nested in _flatten_allowlists(allowlist):
                target = getattr(nested, "channel", None)
                if target is not None and target not in known_channels:
                    raise ChannelConfigurationError(
                        f"NativeIdAllowlist on channel '{channel.name}' references "
                        f"unknown channel '{target}'. Known channels: "
                        f"{sorted(known_channels)}."
                    )

    async def authorize(
        self,
        identity: ChannelIdentity,
        *,
        require_link: bool = False,
        allowlist: IdentityAllowlist | None = None,
        verified_claims: Mapping[str, str] | None = None,
    ) -> AuthorizationOutcome:
        """Evaluate authorization for ``identity`` against ``allowlist``.

        Channels should call this **before** producing a
        :class:`ChannelRequest` so a denied identity never reaches the
        agent. The host's run path also re-checks authorization for
        defense-in-depth, but channels that surface :class:`Denied` or
        :class:`LinkRequired` themselves can render the outcome
        through their native UX (refusal message, link challenge)
        rather than a generic error.

        Wave 1 supports the **open** and **native-allowlist** profiles
        end-to-end. ``require_link=True`` is rejected at construction
        when no linker is configured. ``LinkedClaimAllowlist`` is
        exported but its :meth:`evaluate` raises
        :class:`NotImplementedError` until the linker stack lands.

        Returns:
            One of :class:`Allowed`, :class:`LinkRequired`, or
            :class:`Denied`.
        """
        claims: Mapping[str, str] = verified_claims or {}
        claim_source: Literal["linker", "channel", "none"] = "channel" if claims else "none"
        if allowlist is None:
            # Open profile (or explicitly carved-out channel).
            return Allowed(isolation_key=self._auto_issue_isolation_key(identity))
        pre_context = AuthorizationContext(
            identity=identity,
            phase="pre_link",
            isolation_key=None,
            verified_claims=claims,
            claim_source=claim_source,
        )
        decision = await allowlist.evaluate(pre_context)
        if decision is AllowlistDecision.ALLOW:
            if require_link and self._identity_linker is None:
                # Defensive: validator should have caught this.
                return Denied(
                    reason_code="link_required_without_linker",
                    user_message="Sign-in is not configured for this bot.",
                    log_details={"channel": identity.channel},
                )
            # Wave 1: with no linker we proceed without enforcing link state.
            return Allowed(isolation_key=self._auto_issue_isolation_key(identity))
        if decision is AllowlistDecision.DENY:
            return Denied(
                reason_code="allowlist_denied_pre_link",
                user_message="You don't have access to this bot.",
                log_details={
                    "channel": identity.channel,
                    "phase": "pre_link",
                },
            )
        # ABSTAIN: in Wave 1 (no linker) this is treated as the open
        # path when the allowlist does not require claims, and as a
        # deny otherwise. The full post-link pipeline lands in Wave 2.
        if getattr(allowlist, "requires_linked_claims", False):
            return Denied(
                reason_code="allowlist_requires_link",
                user_message="Please link your account to continue.",
                log_details={"channel": identity.channel, "phase": "pre_link"},
            )
        return Allowed(isolation_key=self._auto_issue_isolation_key(identity))

    def _auto_issue_isolation_key(self, identity: ChannelIdentity) -> str:
        """Auto-issue a stable isolation key for ``identity``.

        Returns the existing key when ``(channel, native_id)`` has
        already been seen, or coins ``"<channel>:<native_id>"`` on
        first contact. The full :class:`IdentityResolver` pipeline
        lands with the linker; Wave 1 uses this lightweight default.
        """
        # Look for an existing isolation_key that has already linked
        # this (channel, native_id). Linear scan is fine for the
        # in-process registry; Wave 2's IdentityResolver replaces this
        # with an indexed lookup.
        for isolation_key, by_channel in self._identities.items():
            existing = by_channel.get(identity.channel)
            if existing is not None and existing.native_id == identity.native_id:
                return isolation_key
        # First contact — coin a deterministic key.
        return f"{identity.channel}:{identity.native_id}"

    @property
    def default_allowlist(self) -> IdentityAllowlist | None:
        """Host-level fallback allowlist applied to channels with ``allowlist="inherit"``."""
        return self._default_allowlist

    @property
    def runtime_mode(self) -> RuntimeMode:
        """The resolved runtime mode for this host.

        Either ``"long_running"`` or ``"ephemeral"``. Resolved at
        construction from the ``runtime_mode`` constructor argument or
        — when unset — auto-detected from deployment environment
        markers; see :func:`_detect_runtime_mode`. Advisory: the value
        drives the *defaults* selected for runtime-shape-dependent
        components (today, the durable task runner) and is logged at
        startup for operator visibility.
        """
        return self._runtime_mode

    @property
    def durable_task_runner(self) -> DurableTaskRunner:
        """The durable task runner used to dispatch non-originating pushes.

        Defaults to a process-local :class:`InProcessTaskRunner` when no
        runner was supplied at construction. Adapter packages may
        replace this with a durable backend (e.g. Foundry-native
        scheduling, ``agent-framework-hosting-durabletask``); the host
        itself only relies on the :class:`DurableTaskRunner` Protocol
        surface so any conforming implementation is usable.
        """
        return self._durable_task_runner

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
        target type, every channel + its mount path, the bind address
        (when known), whether we're running inside a Foundry Hosted
        Agents container, and the worker count. Keeps log noise low
        while still giving an operator a single grep-able anchor when
        triaging.

        Called from both :meth:`serve` (which knows the bind triple)
        and the ASGI lifespan ``startup`` phase (which does not — the
        host may be embedded under any caller-managed ASGI server).
        Bind fields are omitted from the log line when unknown so
        operators can still spot the runtime-mode banner under
        externally-managed servers.
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
            "AgentFrameworkHost starting: target=%s (%s) bind=%s workers=%s hosted=%s "
            "runtime_mode=%s (%s) runner=%s channels=[%s]",
            target_name,
            target_kind,
            bind,
            workers if workers is not None else "<embedded>",
            is_hosted,
            self._runtime_mode,
            self._runtime_mode_source,
            type(self._durable_task_runner).__name__,
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
            # Emit the startup banner once. ``serve()`` may have already
            # logged it (it logs eagerly so the banner appears before
            # control passes to hypercorn); the lifespan still logs it
            # for callers that mount ``host.app`` directly under their
            # own ASGI server — that path otherwise wouldn't get a
            # runtime-mode banner at all.
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
            # (The hosting.push handler is registered eagerly in
            # ``__init__`` rather than here, so ``_deliver_response``
            # can be called without first entering the lifespan — e.g.
            # in tests, or by callers driving the host without an ASGI
            # server.)
            startup_errors: list[tuple[str, BaseException]] = []
            # Replay any persisted pending tasks first so re-scheduled
            # work runs alongside fresh traffic from the moment the
            # host accepts requests. Only meaningful for the host-owned
            # in-process runner with disk persistence on; caller-owned
            # runners manage their own replay lifecycle.
            if (
                self._owns_runner
                and isinstance(self._durable_task_runner, InProcessTaskRunner)
                and self._state_paths.get("runner") is not None
            ):
                try:
                    await self._durable_task_runner.resume()
                except Exception as exc:
                    logger.exception("lifespan startup: durable task runner resume failed")
                    startup_errors.append(("InProcessTaskRunner.resume", exc))
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
                # Drain the host-owned runner after channel shutdowns —
                # channels may legitimately schedule a final push while
                # tearing down (e.g. a goodbye message), and we want
                # those tasks to get a chance to complete before we
                # cancel pending work. For caller-supplied runners we
                # leave lifecycle to the caller.
                if self._owns_runner and isinstance(self._durable_task_runner, InProcessTaskRunner):
                    try:
                        await self._durable_task_runner.shutdown(timeout=5.0)
                    except Exception as exc:  # pragma: no cover - defensive
                        logger.exception("lifespan shutdown: durable task runner shutdown failed")
                        shutdown_errors.append(("InProcessTaskRunner.shutdown", exc))
                # Close the persisted sessions store after the runner so
                # any in-flight task that touches session state during
                # shutdown can still write through.
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
        """Emit a structured INFO summary for every incoming target invocation.

        When ``debug=True`` is set on the host, also dump the channel-native
        settings the channel attached to the ``ChannelRequest`` — ``options``
        (the ChatOptions-shaped fields the channel parsed from its protocol
        payload, e.g. temperature/tools/tool_choice for Responses), plus
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
        self._record_identity(request)
        if self._is_workflow:
            # Workflow targets follow a separate path; the dedicated dispatch
            # is parameterised on ``WorkflowRunResult`` so the static return
            # type of ``_invoke`` itself stays the agent-shaped envelope.
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

        async def _bridge() -> AsyncIterator[AgentResponseUpdate]:
            # Same restore step the blocking path runs (see
            # ``_restore_workflow_checkpoint``) — kept inside the bridge
            # so the in-memory state is rehydrated lazily on first
            # iteration rather than at stream-construction time.
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

    def _build_echo_payload(self, request: ChannelRequest) -> HostedRunResult[AgentResponse]:
        """Build a ``HostedRunResult`` representing the originating user message.

        Used when ``ResponseTarget.echo_input`` is set so non-originating
        destinations can mirror the user's turn before the agent reply
        arrives. The user-facing payload is synthesised as a one-message
        :class:`AgentResponse` (``role="user"``) so it flows through the
        same delivery machinery as the agent's reply — channels handle
        both via a single ``HostedRunResult[AgentResponse]`` shape. The
        hosting metadata that ``_wrap_input`` attaches for agent
        invocation is intentionally stripped: the echo is end-user-facing
        and we don't leak host-internal bookkeeping onto another
        channel's wire.
        """
        raw = request.input
        if isinstance(raw, Message):
            user_messages: list[Message] = [
                Message(role="user", contents=list(raw.contents), author_name=raw.author_name),
            ]
        elif isinstance(raw, list) and raw and all(isinstance(m, Message) for m in raw):
            user_messages = [
                Message(role="user", contents=list(m.contents), author_name=m.author_name)
                for m in raw
                if isinstance(m, Message)
            ]
        elif isinstance(raw, str):
            user_messages = [Message(role="user", contents=[Content.from_text(text=raw)])]
        elif isinstance(raw, Content):
            user_messages = [Message(role="user", contents=[raw])]
        else:
            # AgentRunInputs allows other shapes (mapping, sequence of mixed
            # str/Content); stringify as a defensive fallback.
            user_messages = [Message(role="user", contents=[Content.from_text(text=str(raw))])]
        return HostedRunResult(AgentResponse(messages=user_messages))

    async def _deliver_payload_to_channel(
        self,
        channel: ChannelPush,
        identity: ChannelIdentity,
        payload: HostedRunResult[Any],
        *,
        request: ChannelRequest,
        is_echo: bool,
    ) -> HostedRunResult[Any]:
        """Clone, run the channel's ``response_hook`` (if any), and push.

        The clone keeps fan-out free from cross-destination mutation: a
        hook that rebinds ``result`` on one destination cannot leak into
        the next push. Note that the clone is shallow — channels that
        need to mutate ``result`` itself (rather than rebind it via
        :meth:`HostedRunResult.replace`) are responsible for their own
        deep copy. Returns the (possibly hook-shaped) payload so callers
        can log post-hook diagnostics rather than the pre-hook ones.

        ``response_hook`` is duck-typed on the channel: any attribute
        named ``response_hook`` that is callable participates. The
        :class:`Channel` Protocol stays a small "name / path / contribute"
        contract; richer surfaces stay attribute-level so adding hook
        support to a new channel does not require updating the Protocol.
        """
        shaped: HostedRunResult[Any] = payload.replace()
        hook = cast(ChannelResponseHook | None, getattr(channel, "response_hook", None))
        if callable(hook):
            ctx = ChannelResponseContext(
                request=request,
                channel_name=channel.name,
                destination_identity=identity,
                originating=False,
                is_echo=is_echo,
            )
            shaped = await apply_response_hook(hook, shaped, context=ctx)
        await channel.push(identity, shaped)
        return shaped

    async def _handle_push_task(self, payload: Mapping[str, Any]) -> None:
        """Runner-side handler for ``hosting.push`` tasks.

        Unpacks a single per-destination push payload (one channel, one
        identity) and runs the echo (when present) followed by the
        response push. Echo failures are logged and swallowed — the
        user-visible failure mode is "response delivered without
        echo", *not* "no response at all". Response-push failures
        re-raise so the runner can retry per the configured
        :class:`RetryPolicy`.

        **Retry idempotency for the echo phase.** The payload includes a
        mutable ``"echo_done"`` cursor (initialised to ``False`` at
        schedule time). If a previous attempt already delivered the
        echo but the response push then failed, the runner retries the
        whole task; we observe ``echo_done == True`` and skip the
        re-echo so end users on channels without server-side
        deduplication don't see the same user-message echoed multiple
        times. This is a best-effort guarantee for the in-process
        runner — payload mutations don't survive process restarts.
        Durable adapter packages SHOULD persist the cursor as part of
        their task state (their replay machinery typically gives them
        that primitive for free).

        Payload shape depends on the configured
        :data:`DurableTaskRunner.payload_mode`:

        * Object mode (default) — live Python references:
          ``channel_name``, ``identity``, ``result``, ``echo_result``,
          ``echo_done``, ``request``.
        * JSON mode — a single ``envelope`` produced by the
          destination channel's :class:`ChannelPushCodec` plus
          ``channel_name`` and ``echo_done``. The handler invokes
          ``codec.decode(envelope)`` to recover the live references
          before pushing.
        """
        channel_name = cast(str, payload["channel_name"])
        echo_done = bool(payload.get("echo_done", False))

        by_name = {ch.name: ch for ch in self.channels}
        channel = by_name.get(channel_name)
        if channel is None or not isinstance(channel, ChannelPush):
            # Channel was validated at schedule time; if we ever land
            # here it means the host's channel list mutated mid-flight,
            # which we don't support. Log loudly and drop — re-raising
            # would just cause the runner to retry forever.
            logger.error(
                "hosting.push: channel %r is no longer a ChannelPush; dropping task",
                channel_name,
            )
            return
        push_channel = cast(ChannelPush, channel)

        # Recover the live references. Object-mode runners pass them
        # through verbatim; JSON-mode runners persisted an envelope the
        # channel's codec produced and we now ask the codec to decode
        # it back.
        envelope = payload.get("envelope")
        if envelope is not None:
            codec = cast("ChannelPushCodec | None", getattr(channel, "push_codec", None))
            if codec is None:
                logger.error(
                    "hosting.push: channel %r received a JSON envelope but has no push_codec; dropping task",
                    channel_name,
                )
                return
            result, request, identity, echo_result = await codec.decode(envelope)
        else:
            identity = cast(ChannelIdentity, payload["identity"])
            result = cast(HostedRunResult[Any], payload["result"])
            echo_result = cast("HostedRunResult[Any] | None", payload.get("echo_result"))
            request = cast(ChannelRequest, payload["request"])

        if echo_result is not None and not echo_done:
            try:
                await self._deliver_payload_to_channel(
                    push_channel,
                    identity,
                    echo_result,
                    request=request,
                    is_echo=True,
                )
            except Exception:
                logger.exception(
                    "hosting.push: echo push failed for channel=%s native_id=%s",
                    channel_name,
                    identity.native_id,
                )
            else:
                # Mutate the payload mapping so a subsequent retry of
                # this task (triggered by a failure in the response
                # phase below) skips the echo. The in-process runner
                # reuses the same mapping object across retries — see
                # ``_run_with_retry``; durable adapters persist the
                # cursor as part of their task state.
                if isinstance(payload, dict):
                    payload["echo_done"] = True
                logger.info(
                    "hosting.push: echoed user message",
                    extra={"channel": channel_name, "native_id": identity.native_id},
                )
        elif echo_result is not None and echo_done:
            logger.debug(
                "hosting.push: skipping echo on retry (already delivered)",
                extra={"channel": channel_name, "native_id": identity.native_id},
            )

        # Response phase — raise on failure so the runner retries per
        # the configured retry policy. The runner is responsible for
        # terminal-failure bookkeeping.
        await self._deliver_payload_to_channel(
            push_channel,
            identity,
            result,
            request=request,
            is_echo=False,
        )
        logger.info(
            "hosting.push: pushed agent response",
            extra={"channel": channel_name, "native_id": identity.native_id},
        )

    async def _deliver_response(self, request: ChannelRequest, payload: HostedRunResult[Any]) -> bool:
        """Resolve ``request.response_target``, annotate audit metadata, and schedule pushes.

        Returns ``True`` when the originating channel should render the
        agent reply on its own wire (the resolved target included the
        originating channel either explicitly or via the host's "every
        destination dropped, fall back to originating" recovery path).
        Returns ``False`` when the reply is fanned out purely to
        non-originating destinations (or :data:`ResponseTarget.none`
        suppresses the reply entirely).

        Per SPEC-002 §"Intended targets + durable delivery": for any
        non-``originating`` target, the originating channel returns an
        acknowledgement and the actual agent reply is dispatched
        **asynchronously** via the host's :class:`DurableTaskRunner` —
        one scheduled task per destination, with the runner owning
        retry / terminal-failure / replay semantics.

        **Immutable audit annotation.** Before scheduling, the host
        annotates each resolved assistant ``Message`` in the payload
        with the ``hosting.intended_targets`` list (and optionally
        ``hosting.skipped_targets`` for destinations dropped at
        resolution time). Persistence providers therefore observe the
        host's *intent* from a single immutable write — mutable
        per-destination delivery state is owned by the runner backend.

        When a destination cannot be resolved (no known native id), or
        the destination channel doesn't implement :class:`ChannelPush`,
        or no channel by that name is registered, it is dropped
        synchronously and logged at WARNING. When the only resolved
        destinations all drop at resolution time we fall back to
        delivering on the originating channel so the user is never left
        without a reply.

        When ``request.response_target.echo_input`` is True the echo
        payload (the originating user message) is bundled into the
        same per-destination task as the agent response — see
        :meth:`_handle_push_task`. The echo is dispatched *before* the
        response within that task; an echo failure does not abort the
        response push, and a retried task skips an already-delivered
        echo via the ``echo_done`` cursor.

        For JSON-mode runners the destination channel's
        :class:`ChannelPushCodec` is called to project the in-memory
        :class:`HostedRunResult` into a JSON-safe envelope before
        scheduling. Codec failures
        (:class:`PushPayloadNotSerializable`) abort the schedule for
        that destination (logged and treated as skipped); other
        destinations still get their chance.

        Each per-destination push (echo and response) goes through
        :meth:`_deliver_payload_to_channel`, which clones the payload
        and applies the channel's optional ``response_hook`` so
        per-channel transforms (e.g. flatten multi-modal to text for a
        text-only wire) can't leak across destinations.
        """
        target = request.response_target
        kind = target.kind

        # Fast paths for the trivial variants.
        if kind == ResponseTargetKind.ORIGINATING:
            return True
        if kind == ResponseTargetKind.NONE:
            # Background-only — drop the reply on the floor for now (no
            # ContinuationToken in the prototype).
            return False

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
                self._annotate_intended_targets(payload, intended=(), skipped=())
                return True
            destinations.append((active, known.get(active)))

        elif kind == ResponseTargetKind.ALL_LINKED:
            for channel_name, identity in known.items():
                if channel_name == request.channel:
                    include_originating = True
                    continue
                destinations.append((channel_name, identity))
            if not destinations and not include_originating:
                # No links recorded yet — fall back.
                self._annotate_intended_targets(payload, intended=(), skipped=())
                return True

        elif kind == ResponseTargetKind.IDENTITIES:
            for ident in target.target_identities:
                if ident.channel == request.channel:
                    # Pointing the originating channel at itself — fold
                    # into ``include_originating`` so the originating
                    # channel renders on its own wire rather than
                    # double-delivering via push.
                    include_originating = True
                    continue
                destinations.append((ident.channel, ident))

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

        # Schedule per-destination push tasks via the durable runner.
        by_name = {ch.name: ch for ch in self.channels}
        runner_mode = getattr(self._durable_task_runner, "payload_mode", DurableTaskPayloadMode.OBJECT)
        intended_tokens: list[str] = []
        skipped_tokens: list[str] = []
        echo_payload = self._build_echo_payload(request) if target.echo_input else None
        for channel_name, dest_identity in destinations:
            channel = by_name.get(channel_name)
            token = f"{channel_name}:{dest_identity.native_id}" if dest_identity is not None else channel_name
            if channel is None:
                logger.warning("deliver_response: no channel named %r (target=%s)", channel_name, token)
                skipped_tokens.append(token)
                continue
            if not isinstance(channel, ChannelPush):
                logger.warning(
                    "deliver_response: channel %r does not implement ChannelPush (target=%s)",
                    channel_name,
                    token,
                )
                skipped_tokens.append(token)
                continue
            if dest_identity is None:
                logger.warning(
                    "deliver_response: no known identity for isolation_key=%s on channel=%s",
                    isolation_key,
                    channel_name,
                )
                skipped_tokens.append(token)
                continue

            # Build the runner payload. Object-mode runners get live
            # references for speed; JSON-mode runners get a fully
            # encoded envelope from the channel's push codec.
            try:
                task_payload = await self._build_push_payload(
                    channel=channel,
                    channel_name=channel_name,
                    identity=dest_identity,
                    request=request,
                    result=payload,
                    echo_payload=echo_payload,
                    runner_mode=runner_mode,
                )
            except PushPayloadNotSerializable:
                logger.exception(
                    "deliver_response: channel %r push codec refused payload (target=%s); skipping",
                    channel_name,
                    token,
                )
                skipped_tokens.append(token)
                continue
            try:
                await self._durable_task_runner.schedule(HOSTING_PUSH_TASK_NAME, task_payload)
            except Exception:
                # Schedule-time failures are a host-side outage (runner
                # backend unreachable, configuration error). Log and
                # treat the destination as skipped — the originating
                # channel's fall-back-to-originating rule (below) keeps
                # the user from being left without a reply when every
                # destination dropped.
                logger.exception("deliver_response: failed to schedule push for target=%s", token)
                skipped_tokens.append(token)
                continue
            intended_tokens.append(token)
            logger.info(
                "deliver_response: scheduled push",
                extra={"target": token, "channel": channel_name},
            )

        if not intended_tokens and not include_originating:
            # Spec policy: if every destination drops at resolution time
            # (or scheduling fails universally) deliver to originating
            # so the user gets a response. The runner backend still
            # owns observability for any partial-failure case where at
            # least one destination did get scheduled.
            logger.warning("deliver_response: every destination dropped — falling back to originating")
            include_originating = True

        self._annotate_intended_targets(
            payload,
            intended=tuple(intended_tokens),
            skipped=tuple(skipped_tokens),
            include_originating=include_originating,
            originating_channel=request.channel,
        )

        return include_originating

    async def _build_push_payload(
        self,
        *,
        channel: ChannelPush,
        channel_name: str,
        identity: ChannelIdentity,
        request: ChannelRequest,
        result: HostedRunResult[Any],
        echo_payload: HostedRunResult[Any] | None,
        runner_mode: DurableTaskPayloadMode,
    ) -> dict[str, Any]:
        """Assemble the runner payload for a single push destination.

        For object-mode runners (the default in-process runner) we
        forward live references — no serialisation cost on the hot
        path. For JSON-mode runners we invoke the channel's
        :class:`ChannelPushCodec` once to produce a JSON-safe envelope
        for the whole push triple; the codec is the only entity that
        knows how to project a :class:`HostedRunResult` plus the
        channel-side request/identity context for a specific channel's
        wire format.
        """
        if runner_mode == DurableTaskPayloadMode.OBJECT:
            return {
                "channel_name": channel_name,
                "identity": identity,
                "result": result,
                "echo_result": echo_payload,
                "echo_done": False,
                "request": request,
            }
        # JSON mode — the startup validator guarantees every push-capable
        # channel has a ``push_codec``. Use ``getattr`` for the same
        # duck-typed lookup pattern the validator and decoder use.
        codec = cast("ChannelPushCodec", getattr(channel, "push_codec"))  # noqa: B009
        envelope = await codec.encode(
            result=result,
            request=request,
            identity=identity,
            echo_result=echo_payload,
        )
        return {
            "channel_name": channel_name,
            "envelope": dict(envelope),
            "echo_done": False,
        }

    def _annotate_intended_targets(
        self,
        payload: HostedRunResult[Any],
        *,
        intended: tuple[str, ...],
        skipped: tuple[str, ...],
        include_originating: bool = False,
        originating_channel: str | None = None,
    ) -> None:
        """Stamp ``additional_properties["hosting"]`` on every assistant message in the payload.

        The audit annotation is the spec's immutable record of the
        host's delivery *intent* — persistence providers see what the
        host meant to deliver from a single write, without ever
        observing mutable per-destination state (the runner owns
        that). Annotated fields:

        - ``intended_targets``: ``[<channel>[:<native_id>], …]`` for
          every non-originating destination whose push task was
          scheduled successfully.
        - ``skipped_targets``: destinations dropped at resolution time
          (unknown channel, no ``ChannelPush``, no known identity, or
          schedule-time outage). Useful for ops triage.
        - ``includes_originating``: ``True`` when the originating
          channel rendered (or will render) the reply on its own wire.

        Workflow targets producing arbitrary result objects with no
        ``messages`` field are left untouched — the annotation is a
        best-effort augmentation of conventional agent responses.
        """
        result_obj = payload.result
        messages_raw: Any = getattr(result_obj, "messages", None)
        if not isinstance(messages_raw, list):
            return
        hosting_meta: dict[str, Any] = {
            "intended_targets": list(intended),
            "includes_originating": include_originating,
        }
        if skipped:
            hosting_meta["skipped_targets"] = list(skipped)
        if include_originating and originating_channel is not None:
            hosting_meta["originating_channel"] = originating_channel
        for entry in cast("list[Any]", messages_raw):  # type: ignore[redundant-cast]
            if not isinstance(entry, Message):
                continue
            message: Message = entry
            if getattr(message, "role", None) != "assistant":
                continue
            existing = message.additional_properties or {}
            existing_hosting = existing.get("hosting") if isinstance(existing, Mapping) else None
            if isinstance(existing_hosting, Mapping):
                merged_hosting: Mapping[str, Any] = {**existing_hosting, **hosting_meta}
            else:
                merged_hosting = hosting_meta
            message.additional_properties = {**existing, "hosting": merged_hosting}


__all__ = ["AgentFrameworkHost", "ChannelContext", "logger"]
