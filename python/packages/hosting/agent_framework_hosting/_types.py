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
The channel owns rendering the result back onto its originating protocol.
"""

from __future__ import annotations

import os
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Generic, Protocol, TypedDict, TypeVar, runtime_checkable

from agent_framework import (
    AgentResponseUpdate,
    AgentRunInputs,
)
from starlette.routing import BaseRoute

if TYPE_CHECKING:
    from ._host import ChannelContext


class ChannelSession:
    """Channel-supplied session hint.

    The host turns this into an ``AgentSession`` keyed by ``isolation_key`` so
    every distinct end user gets their own context-provider state (e.g. one
    ``FileHistoryProvider`` JSONL file per user).
    """

    def __init__(self, isolation_key: str | None = None) -> None:
        self.isolation_key = isolation_key


class ChannelIdentity:
    """Channel-native identity metadata observed on a request.

    The simplified hosting core records this only on the persisted input
    message's ``additional_properties["hosting"]`` block and forwards it
    through run/response hooks. Cross-channel linking and recipient lookup are
    follow-up concerns, not part of the v1 host contract.
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


@dataclass
class ChannelRequest:
    """Uniform invocation envelope every channel produces from its native payload.

    Kept as a dataclass so app authors can use ``dataclasses.replace(...)`` in
    run hooks to produce a modified envelope without re-listing every field.
    """

    channel: str
    operation: str
    input: AgentRunInputs
    session: ChannelSession | None = None
    options: Mapping[str, Any] | None = None
    session_mode: str = "auto"
    metadata: Mapping[str, Any] = field(default_factory=lambda: {})
    attributes: Mapping[str, Any] = field(default_factory=lambda: {})
    stream: bool = False
    identity: ChannelIdentity | None = None


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
    """Channel-neutral envelope around the target's full-fidelity result.

    The host does not flatten or pre-shape the target output. Channels and
    response hooks read the underlying result type directly and serialize the
    subset their wire format can carry.
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
        """Return a shallow copy with the supplied fields overridden."""
        new: HostedRunResult[TResult] = HostedRunResult.__new__(HostedRunResult)  # pyright: ignore[reportUnknownVariableType]
        new.result = self.result if isinstance(result, _Unset) else result
        new.session = self.session if isinstance(session, _Unset) else session
        return new


class HostStatePaths(TypedDict, total=False):
    """Per-component disk paths for host-managed state.

    Only session aliases and workflow checkpoints remain in the simplified
    host. Linking stores, active-channel maps, identity registries, and runner
    queues are follow-up concerns.
    """

    sessions: str | os.PathLike[str]
    """Where the host persists session aliases created by ``reset_session``."""

    checkpoints: str | os.PathLike[str]
    """Where the host persists workflow checkpoints for ``Workflow`` targets."""


ChannelStreamUpdateHook = Callable[
    [AgentResponseUpdate],
    "AgentResponseUpdate | Awaitable[AgentResponseUpdate | None] | None",
]


ChannelRunHook = Callable[..., "Awaitable[ChannelRequest] | ChannelRequest"]


ChannelResponseHook = Callable[..., "Awaitable[HostedRunResult[Any]] | HostedRunResult[Any]"]


@runtime_checkable
class Channel(Protocol):
    """A pluggable adapter that exposes one transport on the host."""

    name: str
    path: str

    def contribute(self, context: ChannelContext) -> ChannelContribution: ...
