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

import os
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Generic, Literal, Protocol, TypedDict, TypeVar, runtime_checkable

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
    IDENTITIES = "identities"
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
    - ``ResponseTarget.identity(ChannelIdentity)`` /
      ``.identities([ChannelIdentity, ...])`` — push to one or more
      **fully-specified identities**. Preferred over the ``"channel:native_id"``
      string variant when the destination needs ``identity.attributes``
      preserved (Teams conversation/thread metadata, Slack channel+thread,
      Bot Framework service-url, etc.).
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
        identities: tuple[ChannelIdentity, ...] = (),
        *,
        echo_input: bool = False,
    ) -> None:
        self.kind = kind
        self.targets = targets
        # Stored under a non-clashing name so the ``identities``
        # *classmethod* (the public builder) can coexist with the
        # value accessor (the ``identities`` property below). At
        # runtime instance attributes shadow class attributes anyway,
        # but type checkers see the classmethod and reject reassignment.
        self._target_identities: tuple[ChannelIdentity, ...] = tuple(identities)
        # When True, the host first pushes the originating user message
        # to every non-originating destination (so end-user apps observing
        # those channels can keep their UI in sync) before pushing the
        # agent response. Defaults to False — opt-in only, because not
        # every channel knows how to render ``role="user"`` content
        # gracefully on its own surface.
        self.echo_input = echo_input

    @property
    def target_identities(self) -> tuple[ChannelIdentity, ...]:
        """Destination identities for ``kind == IDENTITIES`` targets.

        Public name distinct from the :meth:`identities` classmethod
        builder. Empty for non-``IDENTITIES`` kinds.
        """
        return self._target_identities

    # -- builders ---------------------------------------------------------- #

    @classmethod
    def channel(cls, name: str, *, echo_input: bool = False) -> ResponseTarget:
        """Target a single named destination channel."""
        return cls(kind=ResponseTargetKind.CHANNELS, targets=(name,), echo_input=echo_input)

    @classmethod
    def channels(cls, names: Sequence[str], *, echo_input: bool = False) -> ResponseTarget:
        """Target an explicit list of destination channels."""
        return cls(kind=ResponseTargetKind.CHANNELS, targets=tuple(names), echo_input=echo_input)

    @classmethod
    def identity(cls, identity: ChannelIdentity, *, echo_input: bool = False) -> ResponseTarget:
        """Target a single fully-specified :class:`ChannelIdentity`.

        Preferred over the ``"channel:native_id"`` string token in
        :meth:`channels` when ``identity.attributes`` carries metadata the
        destination channel needs (Teams conversation/thread ids and
        service-url, Slack channel + thread, Bot Framework activity-locator
        fields, etc.). The host pushes to the named identity verbatim
        without consulting its own identity registry.
        """
        return cls(kind=ResponseTargetKind.IDENTITIES, identities=(identity,), echo_input=echo_input)

    @classmethod
    def identities(cls, identities: Sequence[ChannelIdentity], *, echo_input: bool = False) -> ResponseTarget:
        """Target an explicit list of fully-specified :class:`ChannelIdentity` objects.

        See :meth:`identity` for the single-destination variant.
        """
        return cls(kind=ResponseTargetKind.IDENTITIES, identities=tuple(identities), echo_input=echo_input)

    # -- value semantics --------------------------------------------------- #
    # ``ResponseTarget`` is treated as immutable, so two instances with the
    # same ``kind`` + ``targets`` + ``identities`` + ``echo_input`` are
    # interchangeable. Tests and channel parsers compare instances with
    # ``==`` and use them as dict keys.

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ResponseTarget):
            return NotImplemented
        return (
            self.kind is other.kind
            and self.targets == other.targets
            and _identities_equal(self._target_identities, other._target_identities)
            and self.echo_input == other.echo_input
        )

    def __hash__(self) -> int:
        # ``ChannelIdentity`` is not itself hashable (mutable attributes
        # mapping); fold the identifying triple so two ``identities``
        # tuples with the same channel/native_id/attributes content hash
        # the same.
        identities_key = tuple(
            (i.channel, i.native_id, tuple(sorted(i.attributes.items()))) for i in self._target_identities
        )
        return hash((self.kind, self.targets, identities_key, self.echo_input))

    def __repr__(self) -> str:
        suffix = ", echo_input=True" if self.echo_input else ""
        if self.kind is ResponseTargetKind.CHANNELS:
            return f"ResponseTarget.channels({list(self.targets)!r}{suffix})"
        if self.kind is ResponseTargetKind.IDENTITIES:
            return f"ResponseTarget.identities({list(self._target_identities)!r}{suffix})"
        return f"ResponseTarget.{self.kind.value}{suffix}"


def _identities_equal(left: tuple[ChannelIdentity, ...], right: tuple[ChannelIdentity, ...]) -> bool:
    """Structural-equality helper for ``ResponseTarget.identities`` comparisons.

    ``ChannelIdentity`` is a plain class without ``__eq__``, so ``tuple`` /
    ``list`` comparisons fall back to identity equality which is too strict
    for value-typed ``ResponseTarget`` callers (two equivalent identity
    tuples produced independently would otherwise compare unequal).
    """
    if len(left) != len(right):
        return False
    for a, b in zip(left, right, strict=True):
        if a.channel != b.channel or a.native_id != b.native_id:
            return False
        if dict(a.attributes) != dict(b.attributes):
            return False
    return True


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


class DurableTaskPayloadMode(str, Enum):
    """How a :class:`DurableTaskRunner` consumes scheduled-task payloads.

    Used by the host's startup validator to pair a runner's persistence
    expectations with the channels' push-codec capabilities. Adapter packages
    pick the right value for their backing store.

    * ``OBJECT`` — the runner accepts live Python objects in the payload.
      No serialization is required; the host's
      :class:`InProcessTaskRunner` is the canonical example. Suitable for
      ``runtime_mode="long_running"`` deployments where the runner shares
      address space with the producer.
    * ``JSON`` — the runner persists the payload (database, durable queue,
      Foundry scheduled-task store, …) and replays it after a process
      restart. Payloads MUST be JSON-serializable, which constrains what
      the host can put on the wire. The host validates at construction
      that every push-capable channel exposes a
      :class:`ChannelPushCodec` (so :class:`HostedRunResult` payloads can
      be reduced to a JSON envelope before scheduling).
    """

    OBJECT = "object"
    JSON = "json"


# A push-codec implementation reduces the ``(result, request, identity)``
# triple a destination channel will receive into a JSON-safe envelope that
# a durable :class:`DurableTaskRunner` can persist, and reconstructs the
# rendering inputs on the consumer side. The host *invokes* the codec
# during scheduling; the destination channel implements it (the channel
# knows what shape of payload it can render).
#
# Channels with no push codec are usable only with object-mode runners
# (the default :class:`InProcessTaskRunner`) — the host validates this at
# construction so the mismatch surfaces eagerly rather than on first push.
class ChannelPushCodec(Protocol):
    """Optional capability: serialise the push envelope for a durable task runner.

    Implementations live on the destination channel (alongside ``push``)
    as a duck-typed ``push_codec`` attribute. The host's
    :meth:`_deliver_response` invokes :meth:`encode` once per scheduled
    push (in JSON-mode runner deployments) to produce a JSON-safe
    envelope for the runner; the handler calls :meth:`decode`
    immediately before invoking :meth:`ChannelPush.push`. Object-mode
    runners (the default in-process runner) bypass the codec entirely
    and pass live references through verbatim.

    Encoded envelopes MUST be JSON-serialisable
    (``dict``/``list``/``str``/``int``/``float``/``bool``/``None``).
    Channels that cannot satisfy this for some inputs (e.g. arbitrary
    workflow result objects without a stable schema) SHOULD raise a
    typed :class:`PushPayloadNotSerializable` from :meth:`encode`
    rather than return a best-effort representation; the host surfaces
    that as a schedule-time error and the destination is treated as
    skipped (other destinations still get their chance).
    """

    async def encode(
        self,
        *,
        result: HostedRunResult[Any],
        request: ChannelRequest,
        identity: ChannelIdentity,
        echo_result: HostedRunResult[Any] | None,
    ) -> Mapping[str, Any]:
        """Project the in-memory push triple into a JSON-safe envelope."""
        ...

    async def decode(
        self,
        envelope: Mapping[str, Any],
    ) -> tuple[HostedRunResult[Any], ChannelRequest, ChannelIdentity, HostedRunResult[Any] | None]:
        """Reconstruct ``(result, request, identity, echo_result)`` from an envelope."""
        ...


class PushPayloadNotSerializable(RuntimeError):
    """Raised by a :class:`ChannelPushCodec` when the payload cannot be serialised.

    Channels raise this from :meth:`ChannelPushCodec.encode` when the
    inbound :class:`HostedRunResult` carries content the codec has no
    JSON projection for (e.g. an arbitrary workflow result with no
    declared schema). The host surfaces the error eagerly at schedule
    time rather than letting the runner discover it after persisting
    a half-formed envelope.
    """


class PushPayloadNotPicklable(RuntimeError):
    """Raised when a disk-persistent runner cannot pickle a scheduled task payload.

    The in-process runner falls back to pickle when ``state_dir`` is set
    so a long-running host can resume in-flight pushes across restarts.
    Most :class:`HostedRunResult` payloads (frozen dataclasses wrapping
    :class:`AgentResponse` or workflow output) pickle without issue, but
    a user-supplied workflow result or response hook may embed an
    unpickleable object (live network client, ``asyncio.Lock``, generator).
    The runner raises this at schedule time so the misconfig is loud
    rather than silently downgrading to no-persistence.
    """


class HostStatePaths(TypedDict, total=False):
    """Per-component disk paths for host-managed state.

    Pass an instance of this typed dict to
    :class:`~agent_framework_hosting._host.AgentFrameworkHost`'s
    ``state_dir`` parameter when you want to place individual components
    on different volumes — for example, a fast local SSD for the runner
    task queue and a network-attached durable volume for session state
    that needs to survive container moves.

    All keys are optional (``total=False``): unset components fall back
    to in-memory storage. Pass a single ``str``/``PathLike`` to
    ``state_dir`` instead to get the default subfolder layout
    (``state_dir/runner/``, ``state_dir/sessions/``).

    Future components (links, continuations, ledger) will be added as
    additional keys in subsequent releases.
    """

    runner: str | os.PathLike[str]
    """Where :class:`~agent_framework_hosting._runner.InProcessTaskRunner`
    persists its pending-task queue and bounded terminal-status cache.
    Required for in-flight push retries to survive process restarts."""

    sessions: str | os.PathLike[str]
    """Where the host persists session aliases (from
    :meth:`AgentFrameworkHost.reset_session`), the per-isolation-key
    identity registry, and the last-active-channel map. Required for
    ``ResponseTarget.active``/``.channel``/``.all_linked`` to find
    destinations after a restart, and for ``reset_session`` rotations
    to survive a restart."""


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
    r"""Optional capability: a channel that can deliver outbound messages without a prior request.

    Per SPEC-002 (req #13), channels that can do proactive delivery
    (Telegram bot proactive message, Teams proactive bot message,
    webhook callbacks, SSE broadcasts) implement ``push`` on top of the
    base :class:`Channel` protocol. Channels without push can only be
    addressed as the ``originating`` :class:`ResponseTarget`.

    Distinguishing user echoes from agent replies
    ---------------------------------------------
    When the originating :class:`ResponseTarget` opts in to
    ``echo_input=True``, the host pushes the user's input message to
    each non-originating destination **before** the agent reply. Both
    pushes go through the same ``push(identity, payload)`` entry point;
    the channel distinguishes them by inspecting the role on the
    payload's underlying :class:`~agent_framework.Message`\\(s):

    * ``payload.result.messages[i].role == "user"`` → the echo phase
      (originating user's turn mirrored onto this destination so the
      channel's UX can stay coherent with the user's actual prompt).
      Channels that cannot impersonate the user (most chat bots can
      only send AS the bot) typically render echoes as a quoted /
      prefixed block, drop them, or skip them via a
      ``response_hook`` — see below.
    * ``payload.result.messages[i].role == "assistant"`` → the agent's
      reply.

    Channels that want to branch on phase WITHOUT inspecting roles can
    instead expose a ``response_hook`` attribute on the channel
    instance: the host calls the hook with a
    :class:`ChannelResponseContext` whose ``is_echo`` flag carries the
    same phase information explicitly, and the hook returns a
    (possibly rewritten) :class:`HostedRunResult` that the host then
    hands to ``push``. The hook seam is duck-typed and intentionally
    NOT part of this Protocol so adding hook support to an existing
    channel never breaks its public contract.
    """

    name: str

    async def push(self, identity: ChannelIdentity, payload: HostedRunResult[Any]) -> None: ...


# --------------------------------------------------------------------------- #
# Durable task runner — pluggable seam for non-originating push fan-out and
# (in v1 fast-follow) background runs. See spec §"Durable task runner".
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class RetryPolicy:
    """Retry contract a :class:`DurableTaskRunner` honours per scheduled task.

    Defaults are deliberately conservative — five attempts on a 1s/2x/60s
    exponential backoff — so a transient channel outage (Telegram returning
    502, Activity Protocol token refresh) is rerouted to retry without the
    operator wiring anything. Adapter backends (TaskHub, Foundry durable
    tasks) MAY translate this into their native retry primitive; the
    in-process runner implements it directly via ``asyncio.sleep``.
    """

    max_attempts: int = 5
    initial_backoff_seconds: float = 1.0
    backoff_multiplier: float = 2.0
    max_backoff_seconds: float = 60.0


@dataclass(frozen=True)
class TaskHandle:
    """Opaque, runner-issued handle for a scheduled task.

    Callers receive one of these from :meth:`DurableTaskRunner.schedule` and
    pass it back to :meth:`DurableTaskRunner.get` to poll status. ``task_id``
    is opaque — its shape is implementation-defined (UUID for the in-process
    runner, instance id for TaskHub, scheduled-task arn for Foundry). The
    ``name`` mirrors the handler name supplied to :meth:`schedule` so the
    caller does not have to track it separately.
    """

    task_id: str
    name: str


TaskStatus = Literal["scheduled", "running", "succeeded", "failed", "cancelled"]


@runtime_checkable
class DurableTaskRunner(Protocol):
    """Pluggable seam the host uses to schedule out-of-band work.

    The host registers a single internal handler — ``"hosting.push"`` — at
    startup; each non-originating push destination becomes a
    ``runner.schedule("hosting.push", payload)`` call. The handler resolves
    the destination channel, runs its ``response_hook`` (if any), and calls
    :meth:`ChannelPush.push`. Failures inside the handler are caught by the
    runner, retried per the supplied :class:`RetryPolicy`, and ultimately
    marked terminal-failed when ``max_attempts`` is exhausted.

    Two implementations ship in the framework: an in-process default
    (``InProcessTaskRunner``, asyncio + bounded retry, no cross-restart
    persistence) suitable for ``runtime_mode="long_running"`` deployments,
    plus adapter packages (``agent-framework-hosting-durabletask``, a future
    Foundry adapter) for ``runtime_mode="ephemeral"`` deployments that need
    cross-restart durability.

    Adapters MUST publish their ``payload_mode`` so the host's startup
    validator can pair runner persistence expectations with channel
    push-codec capabilities. Object-mode runners accept live Python
    references in the payload (the in-process default does this for
    speed); JSON-mode runners persist payloads across process restarts
    and therefore require every push-capable channel to expose a
    :class:`ChannelPushCodec`.
    """

    # Adapter classes set this explicitly; the host inspects it at
    # construction time. Default is conservative ("object") so a runner
    # that omits the attribute is treated as in-process-only and does
    # not silently impose a JSON requirement on channels.
    payload_mode: DurableTaskPayloadMode

    def register(
        self,
        name: str,
        handler: Callable[[Mapping[str, Any]], Awaitable[None]],
    ) -> None:
        """Register a named handler the runner will invoke when a task fires.

        Re-registering under the same name replaces the previous handler.
        Implementations SHOULD raise :class:`RuntimeError` if called after
        the runner has been started, to avoid silent reorderings of in-flight
        work; the in-process runner enforces this.
        """
        ...

    async def schedule(
        self,
        name: str,
        payload: Mapping[str, Any],
        *,
        retry_policy: RetryPolicy | None = None,
    ) -> TaskHandle:
        """Schedule a previously-registered handler invocation.

        ``name`` MUST match a name previously passed to :meth:`register`. The
        ``payload`` is forwarded verbatim to the handler; implementations
        MUST treat it as opaque (no introspection, no normalization).
        ``retry_policy`` overrides the runner's default for this task only;
        ``None`` means "use the runner-wide default".

        Returns a :class:`TaskHandle` the caller may use with :meth:`get` to
        poll status. Returning the handle MUST NOT wait for the task to run
        — scheduling is fire-and-forget from the caller's perspective.
        """
        ...

    async def get(self, handle: TaskHandle) -> TaskStatus | None:
        """Return the current status of a scheduled task.

        Returns ``None`` if the runner no longer has any record of the task
        (e.g. it was scheduled in a prior process and the runner has no
        persistent backing). Otherwise one of the :data:`TaskStatus` values.
        """
        ...


__all__ = [
    "AgentResponse",
    "AgentResponseUpdate",
    "Channel",
    "ChannelCommand",
    "ChannelCommandContext",
    "ChannelContribution",
    "ChannelIdentity",
    "ChannelPush",
    "ChannelPushCodec",
    "ChannelRequest",
    "ChannelResponseContext",
    "ChannelResponseHook",
    "ChannelRunHook",
    "ChannelSession",
    "ChannelStreamTransformHook",
    "DurableTaskPayloadMode",
    "DurableTaskRunner",
    "HostStatePaths",
    "HostedRunResult",
    "PushPayloadNotPicklable",
    "PushPayloadNotSerializable",
    "ResponseStream",
    "ResponseTarget",
    "ResponseTargetKind",
    "RetryPolicy",
    "TaskHandle",
    "TaskStatus",
    "apply_response_hook",
    "apply_run_hook",
]
