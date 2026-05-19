# Copyright (c) Microsoft. All rights reserved.

# ``ChannelRequest`` is the only intentional dataclass here (callers use
# ``dataclasses.replace`` on it in run hooks). The other types are plain
# Python classes by preference, so the "could be a dataclass" lint is muted
# at the file level.
# ruff: noqa: B903

"""Channel-neutral request envelope and channel protocol types.

These types form the boundary between the host and individual channels.
A channel parses its native payload, builds a :class:`ChannelRequest`, and
hands it to :class:`ChannelContext.run` (or ``run_stream``) on the host.
The host normalizes the request into a single agent invocation and either
returns the result to the originating channel or fans out via
:class:`ResponseTarget` to other channels that implement
:class:`ChannelPush`.

See ``docs/specs/002-python-hosting-channels.md`` for the full design.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Generic, Protocol, TypeVar, runtime_checkable

from agent_framework import (
    AgentResponse,
    AgentResponseUpdate,
    AgentRunInputs,
    ResponseStream,
    SupportsAgentRun,
    Workflow,
)
from starlette.routing import BaseRoute

if TYPE_CHECKING:
    from ._host import ChannelContext


# --------------------------------------------------------------------------- #
# Channel-neutral request envelope
# --------------------------------------------------------------------------- #


class ChannelSession:
    """Channel-supplied session hint.

    The host turns this into an ``AgentSession`` keyed by ``isolation_key`` so
    every distinct end user gets their own context-provider state (e.g. one
    ``FileHistoryProvider`` JSONL file per user).
    """

    def __init__(self, isolation_key: str | None = None) -> None:
        self.isolation_key = isolation_key


class ChannelIdentity:
    """Channel-native identity the host sees on each request.

    Consumed by the host's identity registry. The host uses it for two things:

    1. Recording the active channel for an ``isolation_key`` so
       ``ResponseTarget.active`` resolves correctly.
    2. Telling :class:`ChannelPush` ``push`` recipients **where** in their
       native namespace to deliver — Telegram uses ``native_id`` as the
       chat id, Teams as the conversation/AAD id, etc.
    """

    def __init__(
        self,
        channel: str,
        native_id: str,
        attributes: Mapping[str, Any] | None = None,
    ) -> None:
        self.channel = channel
        self.native_id = native_id
        self.attributes: Mapping[str, Any] = attributes if attributes is not None else dict()


class ResponseTargetKind(str, Enum):
    """Discriminator for :class:`ResponseTarget` variants."""

    ORIGINATING = "originating"
    ACTIVE = "active"
    CHANNELS = "channels"
    ALL_LINKED = "all_linked"
    NONE = "none"


class ResponseTarget:
    """Per-request directive controlling **where** the host delivers the agent reply.

    Independent of ``session_mode``. Construct via the classmethod helpers or
    use the module-level singletons rather than touching ``kind`` directly.
    Variants:

    - ``ResponseTarget.originating`` (default) — synchronous response on the
      originating channel only.
    - ``ResponseTarget.active`` — push to the channel most recently observed
      for the resolved ``isolation_key``.
    - ``ResponseTarget.channel("teams")`` / ``.channels([...])`` — push to
      one or more named destinations. Each entry is either a bare channel
      name (host resolves the native id from its identity registry) or a
      ``"channel:native_id"`` token (used verbatim). The pseudo-name
      ``"originating"`` includes the originating channel in the fan-out.
    - ``ResponseTarget.all_linked`` — push to every channel where the
      resolved ``isolation_key`` has been observed.
    - ``ResponseTarget.none`` — background-only; in the prototype this just
      suppresses the originating reply (no ``ContinuationToken`` yet).

    Instances are intended to be treated as immutable; the singletons are
    shared across the process.
    """

    def __init__(
        self,
        kind: ResponseTargetKind = ResponseTargetKind.ORIGINATING,
        targets: tuple[str, ...] = (),
        *,
        echo_input: bool = False,
    ) -> None:
        self.kind = kind
        self.targets = targets
        # When True, the host first pushes the originating user message
        # to every non-originating destination (so end-user apps observing
        # those channels can keep their UI in sync) before pushing the
        # agent response. Defaults to False — opt-in only, because not
        # every channel knows how to render ``role="user"`` content
        # gracefully on its own surface.
        self.echo_input = echo_input

    # -- builders ---------------------------------------------------------- #

    @classmethod
    def channel(cls, name: str, *, echo_input: bool = False) -> ResponseTarget:
        """Target a single named destination channel."""
        return cls(kind=ResponseTargetKind.CHANNELS, targets=(name,), echo_input=echo_input)

    @classmethod
    def channels(cls, names: Sequence[str], *, echo_input: bool = False) -> ResponseTarget:
        """Target an explicit list of destination channels."""
        return cls(kind=ResponseTargetKind.CHANNELS, targets=tuple(names), echo_input=echo_input)

    # -- value semantics --------------------------------------------------- #
    # ``ResponseTarget`` is treated as immutable, so two instances with the
    # same ``kind`` + ``targets`` + ``echo_input`` are interchangeable.
    # Tests and channel parsers compare instances with ``==`` and use them
    # as dict keys.

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ResponseTarget):
            return NotImplemented
        return self.kind is other.kind and self.targets == other.targets and self.echo_input == other.echo_input

    def __hash__(self) -> int:
        return hash((self.kind, self.targets, self.echo_input))

    def __repr__(self) -> str:
        suffix = ", echo_input=True" if self.echo_input else ""
        if self.kind is ResponseTargetKind.CHANNELS:
            return f"ResponseTarget.channels({list(self.targets)!r}{suffix})"
        return f"ResponseTarget.{self.kind.value}{suffix}"


# Module-level singletons so callers can write ``ResponseTarget.originating``
# (matching the spec's classmethod-style notation) without juggling Python's
# no-zero-arg-classmethod-property limitation.
ResponseTarget.originating = ResponseTarget(kind=ResponseTargetKind.ORIGINATING)  # type: ignore[attr-defined]
ResponseTarget.active = ResponseTarget(kind=ResponseTargetKind.ACTIVE)  # type: ignore[attr-defined]
ResponseTarget.all_linked = ResponseTarget(kind=ResponseTargetKind.ALL_LINKED)  # type: ignore[attr-defined]
ResponseTarget.none = ResponseTarget(kind=ResponseTargetKind.NONE)  # type: ignore[attr-defined]


@dataclass
class ChannelRequest:
    """Uniform invocation envelope every channel produces from its native payload.

    Kept as a dataclass so app authors can use ``dataclasses.replace(...)`` in
    run hooks to produce a modified envelope without re-listing every field.
    """

    channel: str
    operation: str  # e.g. "message.create", "command.invoke"
    input: AgentRunInputs
    session: ChannelSession | None = None
    options: Mapping[str, Any] | None = None
    session_mode: str = "auto"  # "auto" | "required" | "disabled"
    metadata: Mapping[str, Any] = field(default_factory=lambda: {})
    attributes: Mapping[str, Any] = field(default_factory=lambda: {})
    stream: bool = False
    identity: ChannelIdentity | None = None
    response_target: ResponseTarget = field(default_factory=lambda: ResponseTarget.originating)  # type: ignore[attr-defined]


class ChannelCommand:
    """A discoverable command a channel exposes to its users (e.g. ``/reset``)."""

    def __init__(
        self,
        name: str,
        description: str,
        handle: Callable[[ChannelCommandContext], Awaitable[None]],
    ) -> None:
        self.name = name
        self.description = description
        self.handle = handle


class ChannelCommandContext:
    """Context passed to a :class:`ChannelCommand` handler."""

    def __init__(
        self,
        request: ChannelRequest,
        reply: Callable[[str], Awaitable[None]],
    ) -> None:
        self.request = request
        self.reply = reply


_EMPTY_ROUTES: tuple[BaseRoute, ...] = ()
_EMPTY_COMMANDS: tuple[ChannelCommand, ...] = ()
_EMPTY_LIFECYCLE: tuple[Callable[[], Awaitable[None]], ...] = ()


class ChannelContribution:
    """Routes, commands, and lifecycle hooks a channel contributes to the host."""

    def __init__(
        self,
        routes: Sequence[BaseRoute] = _EMPTY_ROUTES,
        commands: Sequence[ChannelCommand] = _EMPTY_COMMANDS,
        on_startup: Sequence[Callable[[], Awaitable[None]]] = _EMPTY_LIFECYCLE,
        on_shutdown: Sequence[Callable[[], Awaitable[None]]] = _EMPTY_LIFECYCLE,
    ) -> None:
        self.routes = routes
        self.commands = commands
        self.on_startup = on_startup
        self.on_shutdown = on_shutdown


class _Unset:
    """Sentinel for ``HostedRunResult.replace`` overrides.

    Distinguishes "caller did not pass this kwarg" from "caller passed
    ``None`` explicitly" — needed because ``session`` is ``None`` in
    many envelopes and we want the no-arg call to preserve it.
    """


_UNSET = _Unset()


TResult = TypeVar("TResult")


class HostedRunResult(Generic[TResult]):
    r"""Channel-neutral envelope around the target's full-fidelity result.

    Carries the underlying execution payload **unchanged** so channels
    (and developer-supplied ``response_hook``\\s) can read everything the
    target produced — full multi-modal contents, structured ``value``,
    ``usage_details``, ``response_id``, workflow per-executor outputs,
    final ``WorkflowRunState``, etc.

    ``result`` is generic in ``TResult`` so callers retain static typing:

    * Agent targets always produce
      ``HostedRunResult[AgentResponse]`` — channels read
      ``result.messages``, ``result.value``, ``result.usage_details``, …
      directly.
    * Workflow targets produce ``HostedRunResult[WorkflowRunResult]``
      today (``Workflow`` is not itself generic, so the static narrowing
      is only as tight as ``Workflow.run``'s return). Channels iterate
      ``result.get_outputs()`` and inspect ``result.get_final_state()``
      to render workflow-specific UX. When a host author drives the
      workflow themselves and knows the final-output type, they may
      narrow to ``HostedRunResult[MyOutput]`` in their own
      ``response_hook`` signatures.
    * The echo-input phase synthesises an ``HostedRunResult[AgentResponse]``
      wrapping the originating user turn so the same per-destination
      delivery machinery applies.

    The optional ``session`` slot carries the resolved
    :class:`~agent_framework.AgentSession` the host bound to this
    invocation (``None`` for workflow targets, which do not own session
    state in the agent sense). Channels that want to surface session
    metadata (e.g. echo the resolved isolation key into a response
    header) read it here.

    Treat instances as immutable: the host clones per-destination before
    invoking a per-channel ``response_hook`` so one channel's transform
    cannot perturb the payload another destination observes.
    """

    def __init__(
        self,
        result: TResult,
        *,
        session: Any | None = None,
    ) -> None:
        self.result = result
        self.session = session

    def replace(
        self,
        *,
        result: TResult | _Unset = _UNSET,
        session: Any | _Unset | None = _UNSET,
    ) -> HostedRunResult[TResult]:
        """Return a shallow copy with the supplied fields overridden.

        Used by the host's delivery layer to clone the envelope before
        applying a per-destination ``response_hook``, so one channel's
        transform cannot mutate the payload another destination sees.
        The clone is shallow — channels that need to mutate
        ``result.messages`` (or any other nested mutable container) are
        responsible for deep-cloning that container themselves.
        """
        new: HostedRunResult[TResult] = HostedRunResult.__new__(HostedRunResult)  # pyright: ignore[reportUnknownVariableType]
        new.result = self.result if isinstance(result, _Unset) else result
        new.session = self.session if isinstance(session, _Unset) else session
        return new


class DeliveryReport:
    """What :meth:`ChannelContext.deliver_response` did with a payload.

    The originating channel uses ``include_originating`` to decide whether
    to render the agent reply on its own wire (``True`` — default for the
    ``originating`` target, or when ``"originating"`` is one of the listed
    destinations) or to return only an acknowledgement (``False`` — when
    the target lists only out-of-band destinations).

    ``skipped`` and ``failed`` are intentionally distinct so callers can
    tell a structural drop (no link recorded for the destination
    channel — ``skipped``) from a transport / runtime failure
    (``ChannelPush.push`` raised — ``failed``). A non-empty ``failed``
    indicates an outage / outage-like condition (Telegram, Teams,
    expired credentials, rate limits) and is the right signal for a
    caller that wants to surface a degraded reply to the originating
    user instead of treating the request as fully delivered.

    When ``ResponseTarget.echo_input`` is set the host first pushes the
    user message to each non-originating destination *before* the agent
    response. ``echoed`` records the destinations that received the echo
    successfully; ``echo_failed`` mirrors ``failed`` for the echo phase
    so callers can tell "echo succeeded, response failed" from "both
    succeeded" or "echo failed, response succeeded". The agent-response
    push is still attempted even when the echo push raised — channels
    that drop echoes are expected to keep accepting the response push.
    """

    def __init__(
        self,
        include_originating: bool,
        pushed: tuple[str, ...] = (),
        skipped: tuple[str, ...] = (),
        failed: tuple[tuple[str, str], ...] = (),
        echoed: tuple[str, ...] = (),
        echo_failed: tuple[tuple[str, str], ...] = (),
    ) -> None:
        self.include_originating = include_originating
        self.pushed = pushed  # destination tokens delivered to (e.g. "telegram:123")
        self.skipped = (
            skipped  # destinations dropped without a push attempt (no identity / no ChannelPush / unknown channel)
        )
        # destinations whose ``ChannelPush.push`` raised — each entry is
        # ``(target_token, error_summary)`` so callers can distinguish
        # the "all destinations down" outage case from the documented
        # "no link recorded" drop case (which lands in ``skipped``).
        self.failed = failed
        # When ``ResponseTarget.echo_input`` is set the host also pushes
        # the originating user message to each non-originating
        # destination *before* the agent response. We track the
        # successful echoes separately from ``pushed`` so callers can
        # distinguish "input echo + response both succeeded" from
        # "response pushed twice"; ``echo_failed`` mirrors ``failed``
        # for the echo phase.
        self.echoed = echoed
        self.echo_failed = echo_failed


# A transform hook runs over each AgentResponseUpdate as the channel consumes
# the stream. It can return a replacement update, ``None`` to drop the update,
# or be async. Channels apply it during iteration so that channel-specific
# concerns (e.g. masking, redaction, formatting for the wire) live close to
# the channel rather than on the agent.
ChannelStreamTransformHook = Callable[
    [AgentResponseUpdate],
    "AgentResponseUpdate | Awaitable[AgentResponseUpdate | None] | None",
]


# --------------------------------------------------------------------------- #
# Channel run hook
# --------------------------------------------------------------------------- #


# Run hooks accept the channel-built ``ChannelRequest`` and return a
# (possibly modified) replacement. Channels invoke the hook with both the
# request and the channel-side context as keyword arguments — the call
# convention is ``await hook(request, target=..., protocol_request=...)``.
#
# The ergonomic minimum for a hook implementation is therefore a function
# accepting ``request`` positionally plus ``**kwargs`` and returning a
# (possibly mutated) :class:`ChannelRequest`. Hooks that need the agent
# target or the raw channel-native payload pull them off the keyword
# arguments by name (``target`` / ``protocol_request``).
#
# ``protocol_request`` is the raw, channel-native payload the channel
# parsed (the JSON body for Responses, the Telegram ``Update`` dict, the
# Bot Framework ``Activity`` for Teams). Use it when the hook needs a
# field the channel did not lift onto ``ChannelRequest`` (e.g. OpenAI's
# ``safety_identifier``, Teams' ``from.aadObjectId``, …).
ChannelRunHook = Callable[..., "Awaitable[ChannelRequest] | ChannelRequest"]


async def apply_run_hook(
    hook: ChannelRunHook,
    request: ChannelRequest,
    *,
    target: SupportsAgentRun | Workflow,
    protocol_request: Any | None,
) -> ChannelRequest:
    """Channel-side helper to invoke a :data:`ChannelRunHook` with the standard kwargs.

    Channels call this rather than calling the hook directly so the
    invocation convention (``request`` positional, ``target`` /
    ``protocol_request`` keyword) is enforced in one place.
    """
    result = hook(request, target=target, protocol_request=protocol_request)
    if isinstance(result, Awaitable):
        return await result
    return result


# --------------------------------------------------------------------------- #
# Channel response hook
# --------------------------------------------------------------------------- #


class ChannelResponseContext:
    """Per-destination context handed to a :data:`ChannelResponseHook`.

    Response hooks run on the *output* side of the host pipeline, after
    the agent / workflow has produced a :class:`HostedRunResult` but
    before the destination channel serialises it to its wire format.
    Hooks may need to make decisions based on *where* the payload is
    headed — e.g. flatten multi-modal output to text for a text-only
    destination, or pick which content variant to deliver to a card-
    capable channel. The context captures that information without
    forcing hooks to parse stringly destination tokens.
    """

    def __init__(
        self,
        request: ChannelRequest,
        channel_name: str,
        destination_identity: ChannelIdentity | None,
        originating: bool,
        is_echo: bool = False,
    ) -> None:
        self.request = request
        self.channel_name = channel_name
        # ``None`` when the originating channel is rendering its own reply
        # (no push identity needed for "respond on the wire you came in
        # on") or when the destination is named without a known native id.
        self.destination_identity = destination_identity
        # True when this hook invocation is for the originating channel's
        # synchronous reply. False for non-originating push targets.
        self.originating = originating
        # True when the payload being shaped is the user-message echo
        # rather than the agent response (only happens when
        # ``ResponseTarget.echo_input`` is set).
        self.is_echo = is_echo


# Response hooks accept the :class:`HostedRunResult` the host has assembled
# and return a (possibly modified) replacement. Channels invoke the hook
# with both the payload and the per-destination
# :class:`ChannelResponseContext` as keyword arguments — the call
# convention is ``await hook(result, context=...)``.
#
# The ergonomic minimum for a hook implementation is a function accepting
# ``result`` positionally plus ``**kwargs`` and returning a (possibly
# rewritten) :class:`HostedRunResult`. Hooks that need to branch on the
# destination read it off the ``context`` keyword argument.
#
# ``HostedRunResult`` is generic in the underlying ``result`` type; the
# hook callable signature stays ``Any``-typed so a single
# ``response_hook`` attribute on a channel can serve both agent
# (``HostedRunResult[AgentResponse]``) and workflow
# (``HostedRunResult[WorkflowRunResult]``) payloads — channels narrow
# at hook entry if they need static checking.
ChannelResponseHook = Callable[..., "Awaitable[HostedRunResult[Any]] | HostedRunResult[Any]"]


async def apply_response_hook(
    hook: ChannelResponseHook,
    result: HostedRunResult[Any],
    *,
    context: ChannelResponseContext,
) -> HostedRunResult[Any]:
    """Channel-side helper to invoke a :data:`ChannelResponseHook` with the standard kwargs.

    Channels (and the host's delivery layer) call this rather than calling
    the hook directly so the invocation convention (``result`` positional,
    ``context`` keyword) is enforced in one place.
    """
    out = hook(result, context=context)
    if isinstance(out, Awaitable):
        return await out
    return out


# --------------------------------------------------------------------------- #
# Channel protocols
# --------------------------------------------------------------------------- #


@runtime_checkable
class Channel(Protocol):
    """A pluggable adapter that exposes one transport on the host.

    Channels publish their routes, commands, and lifecycle callbacks via
    :meth:`contribute`. The host mounts them under the channel's ``path``
    (or at the app root when ``path == ""``) and gives the channel a
    :class:`ChannelContext` so it can call back into the host to invoke
    the agent target and deliver responses.
    """

    name: str
    path: str  # default mount path (e.g. "/responses"); use "" to mount routes at the app root

    def contribute(self, context: ChannelContext) -> ChannelContribution: ...


@runtime_checkable
class ChannelPush(Protocol):
    """Optional capability: a channel that can deliver outbound messages without a prior request.

    Per SPEC-002 (req #13), channels that can do proactive delivery
    (Telegram bot proactive message, Teams proactive bot message,
    webhook callbacks, SSE broadcasts) implement ``push`` on top of the
    base :class:`Channel` protocol. Channels without push can only be
    addressed as the ``originating`` :class:`ResponseTarget`.
    """

    name: str

    async def push(self, identity: ChannelIdentity, payload: HostedRunResult[Any]) -> None: ...


__all__ = [
    "AgentResponse",
    "AgentResponseUpdate",
    "Channel",
    "ChannelCommand",
    "ChannelCommandContext",
    "ChannelContribution",
    "ChannelIdentity",
    "ChannelPush",
    "ChannelRequest",
    "ChannelResponseContext",
    "ChannelResponseHook",
    "ChannelRunHook",
    "ChannelSession",
    "ChannelStreamTransformHook",
    "DeliveryReport",
    "HostedRunResult",
    "ResponseStream",
    "ResponseTarget",
    "ResponseTargetKind",
    "apply_response_hook",
    "apply_run_hook",
]
