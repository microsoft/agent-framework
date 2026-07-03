# Copyright (c) Microsoft. All rights reserved.

"""Shared execution state for app-owned hosting routes.

Two independent state holders, one per target kind, since agents and
workflows keep different continuation state:

- ``AgentState`` pairs an agent target with a ``SessionStore``
  (``session_id -> AgentSession``).
- ``WorkflowState`` pairs a workflow target with a ``CheckpointStore``
  (``session_id -> CheckpointStorage``).

Both stores are plain storage: they only get/set/delete what they are given.
Neither one knows how to create a new value for a ``session_id`` it hasn't
seen before -- that is the corresponding state object's job (see
``AgentState.get_or_create_session`` / ``WorkflowState.get_or_create_checkpoint_storage``),
since only the state object has both the store and the resolved target.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Mapping
from typing import Any, Generic, Protocol, TypedDict, TypeVar, cast, runtime_checkable

from agent_framework import (
    AgentRunInputs,
    AgentSession,
    ChatOptions,
    CheckpointStorage,
    InMemoryCheckpointStorage,
    SupportsAgentRun,
    Workflow,
)


class SessionStore:
    """Plain in-memory ``session_id -> AgentSession`` lookup.

    This store only stores and retrieves; it does not create sessions. Use
    :meth:`AgentState.get_or_create_session` for that -- it resolves the
    agent target and calls ``target.create_session(...)`` the first time a
    given ``session_id`` is seen, then stores the result here.

    No eviction: every id ever stored stays resolvable for the life of the
    process. That is intentional -- protocols such as OpenAI Responses'
    ``previous_response_id`` are designed to let a caller continue from *any*
    earlier point in a conversation, not just the latest turn, so every id
    that has been handed out needs to stay independently resolvable. If you
    back a ``SessionStore``-shaped store with real storage (Redis, a
    database, ...), you are responsible for that store's own TTL/eviction
    policy; this in-memory reference implementation does not model that
    concern.
    """

    def __init__(self) -> None:
        """Create an empty session store."""
        self._sessions: dict[str, AgentSession] = {}

    async def get(self, session_id: str) -> AgentSession | None:
        """Return the stored session for ``session_id``, or ``None`` if absent.

        Args:
            session_id: Opaque app-selected session id.

        Raises:
            ValueError: If ``session_id`` is empty.
        """
        if not session_id:
            raise ValueError("session_id must be a non-empty string")
        return self._sessions.get(session_id)

    async def set(self, session_id: str, session: AgentSession) -> None:
        """Store ``session`` under ``session_id``, replacing any existing entry.

        Args:
            session_id: Opaque app-selected session id.
            session: The session to store.

        Raises:
            ValueError: If ``session_id`` is empty.
        """
        if not session_id:
            raise ValueError("session_id must be a non-empty string")
        self._sessions[session_id] = session

    async def delete(self, session_id: str) -> None:
        """Forget the stored session for ``session_id``, if any.

        Args:
            session_id: Opaque app-selected session id.

        Raises:
            ValueError: If ``session_id`` is empty.
        """
        if not session_id:
            raise ValueError("session_id must be a non-empty string")
        self._sessions.pop(session_id, None)


class CheckpointStore:
    """Plain in-memory ``session_id -> CheckpointStorage`` lookup.

    Maps an app-selected session id to a :class:`CheckpointStorage` scoped to
    that conversation. This store only stores and retrieves; it does not
    decide which checkpoint within that storage to resume from. Use
    :meth:`WorkflowState.get_or_create_checkpoint_storage` to create a fresh
    ``CheckpointStorage`` the first time a given ``session_id`` is seen.

    Resuming a prior run is a separate, run-time decision the route makes:
    call ``storage.get_latest(workflow_name=...)`` yourself and pass its
    ``checkpoint_id`` into ``workflow.run(checkpoint_id=..., checkpoint_storage=storage)``.

    No eviction, for the same reason as :class:`SessionStore` -- see that
    class's docstring.
    """

    def __init__(self) -> None:
        """Create an empty checkpoint store."""
        self._storages: dict[str, CheckpointStorage] = {}

    async def get(self, session_id: str) -> CheckpointStorage | None:
        """Return the stored checkpoint storage for ``session_id``, or ``None`` if absent.

        Args:
            session_id: Opaque app-selected session id.

        Raises:
            ValueError: If ``session_id`` is empty.
        """
        if not session_id:
            raise ValueError("session_id must be a non-empty string")
        return self._storages.get(session_id)

    async def set(self, session_id: str, storage: CheckpointStorage) -> None:
        """Store ``storage`` under ``session_id``, replacing any existing entry.

        Args:
            session_id: Opaque app-selected session id.
            storage: The checkpoint storage to store.

        Raises:
            ValueError: If ``session_id`` is empty.
        """
        if not session_id:
            raise ValueError("session_id must be a non-empty string")
        self._storages[session_id] = storage

    async def delete(self, session_id: str) -> None:
        """Forget the stored checkpoint storage for ``session_id``, if any.

        Args:
            session_id: Opaque app-selected session id.

        Raises:
            ValueError: If ``session_id`` is empty.
        """
        if not session_id:
            raise ValueError("session_id must be a non-empty string")
        self._storages.pop(session_id, None)


AgentT = TypeVar("AgentT", bound=SupportsAgentRun)
WorkflowT = TypeVar("WorkflowT", bound=Workflow)


@runtime_checkable
class SupportsBuild(Protocol):
    """A builder that produces a ``Workflow`` via a zero-argument ``build()``.

    Matches ``agent_framework.WorkflowBuilder`` and the orchestration
    builders in ``agent_framework_orchestrations`` (``ConcurrentBuilder``,
    ``GroupChatBuilder``, ``HandoffBuilder``, ``MagenticBuilder``,
    ``SequentialBuilder``) structurally, without ``agent-framework-hosting``
    depending on either package.
    """

    def build(self) -> Workflow: ...


class AgentRunArgs(TypedDict):
    """Arguments prepared for ``Agent.run``."""

    messages: AgentRunInputs
    options: ChatOptions[Any]
    stream: bool


class WorkflowRunArgs(TypedDict):
    """Arguments prepared for ``Workflow.run``."""

    message: Any | None
    responses: Mapping[str, Any] | None
    stream: bool


class AgentState(Generic[AgentT]):
    """Shared execution state for app-owned agent hosting routes.

    Holds the Agent Framework agent target and a :class:`SessionStore` that
    route code may share. Does not own routes, middleware, protocol
    dispatch, or native SDK calls -- web frameworks keep those concerns.
    """

    def __init__(
        self,
        target: AgentT | Awaitable[AgentT] | Callable[[], AgentT | Awaitable[AgentT]],
        *,
        session_store: SessionStore | None = None,
        cache_target: bool = True,
    ) -> None:
        """Create shared state for ``target``.

        Args:
            target: Agent target used by route code. May be a target
                instance, a synchronous factory, an asynchronous factory, or
                an awaitable target.

        Keyword Args:
            session_store: Existing store to use. Defaults to a fresh
                in-memory :class:`SessionStore`.
            cache_target: Whether to cache a resolved callable/awaitable
                target. Defaults to ``True`` so expensive target setup
                happens once.

        Raises:
            ValueError: If ``cache_target=False`` is used with a one-shot
                awaitable target.
        """
        if not cache_target and inspect.isawaitable(target):
            raise ValueError("cache_target=False requires a target instance or callable target factory")
        self._target_source = target
        self._cache_target = cache_target
        self._cached_target: AgentT | None = None
        if not callable(target) and not inspect.isawaitable(target):
            self._cached_target = target
        self._session_store: SessionStore = session_store if session_store is not None else SessionStore()

    async def get_target(self) -> AgentT:
        """Return the resolved target.

        Returns:
            The target instance. Callable and awaitable targets are resolved
            first and cached by default.
        """
        if self._cache_target and self._cached_target is not None:
            return self._cached_target

        target = self._target_source() if callable(self._target_source) else self._target_source
        if inspect.isawaitable(target):
            target = await target
        if self._cache_target:
            self._cached_target = target
        return target

    @property
    def target(self) -> AgentT:
        """Return a synchronously available target.

        Raises:
            RuntimeError: If the target is a callable or awaitable that has not
                been resolved with :meth:`get_target`.
        """
        if self._cached_target is not None:
            return self._cached_target
        if not callable(self._target_source) and not inspect.isawaitable(self._target_source):
            return self._target_source
        raise RuntimeError("target is resolved asynchronously; use `await state.get_target()`")

    @property
    def session_store(self) -> SessionStore:
        """Return the session store for this state."""
        return self._session_store

    async def get_or_create_session(self, session_id: str) -> AgentSession:
        """Return the session for ``session_id``, creating and storing one if missing.

        Args:
            session_id: Opaque app-selected session id.

        Returns:
            The stored or newly created ``AgentSession``.
        """
        session = await self._session_store.get(session_id)
        if session is None:
            target = await self.get_target()
            session = target.create_session(session_id=session_id)
            await self._session_store.set(session_id, session)
        return session

    async def set_session(self, session_id: str, session: AgentSession) -> None:
        """Store ``session`` under ``session_id`` in this state's session store.

        Args:
            session_id: Opaque app-selected session id.
            session: Session to store.
        """
        await self._session_store.set(session_id, session)


class WorkflowState(Generic[WorkflowT]):
    """Shared execution state for app-owned workflow hosting routes.

    Holds the Agent Framework workflow target and a :class:`CheckpointStore`
    that route code may share. Does not own routes, middleware, protocol
    dispatch, or native SDK calls -- web frameworks keep those concerns.
    """

    def __init__(
        self,
        target: WorkflowT | SupportsBuild | Awaitable[WorkflowT] | Callable[[], WorkflowT | Awaitable[WorkflowT]],
        *,
        checkpoint_store: CheckpointStore | None = None,
        cache_target: bool = True,
    ) -> None:
        """Create shared state for ``target``.

        Args:
            target: Workflow target used by route code. May be a target
                instance, a ``WorkflowBuilder``-shaped builder (see
                :class:`SupportsBuild`; the state calls ``build()`` for you),
                a synchronous factory, an asynchronous factory, or an
                awaitable target.

        Keyword Args:
            checkpoint_store: Existing store to use. Defaults to a fresh
                in-memory :class:`CheckpointStore`.
            cache_target: Whether to cache a resolved callable/awaitable/built
                target. Defaults to ``True`` so expensive target setup
                happens once.

        Raises:
            ValueError: If ``cache_target=False`` is used with a one-shot
                awaitable target.
        """
        if isinstance(target, SupportsBuild):
            # WorkflowBuilder (and the orchestration builders) are not
            # themselves callable or awaitable, so normalize to the bound
            # `build` method -- the resolution logic below already knows how
            # to treat a zero-arg factory. `build()` is typed to return the
            # `Workflow` base class rather than this instance's narrower
            # `WorkflowT`, but it is the same object the caller asked for.
            target = cast("Callable[[], WorkflowT]", target.build)
        if not cache_target and inspect.isawaitable(target):
            raise ValueError("cache_target=False requires a target instance or callable target factory")
        self._target_source = target
        self._cache_target = cache_target
        self._cached_target: WorkflowT | None = None
        if not callable(target) and not inspect.isawaitable(target):
            self._cached_target = target
        self._checkpoint_store: CheckpointStore = (
            checkpoint_store if checkpoint_store is not None else CheckpointStore()
        )

    async def get_target(self) -> WorkflowT:
        """Return the resolved target.

        Returns:
            The target instance. Callable and awaitable targets are resolved
            first and cached by default.
        """
        if self._cache_target and self._cached_target is not None:
            return self._cached_target

        target = self._target_source() if callable(self._target_source) else self._target_source
        if inspect.isawaitable(target):
            target = await target
        if self._cache_target:
            self._cached_target = target
        return target

    @property
    def target(self) -> WorkflowT:
        """Return a synchronously available target.

        Raises:
            RuntimeError: If the target is a callable or awaitable that has not
                been resolved with :meth:`get_target`.
        """
        if self._cached_target is not None:
            return self._cached_target
        if not callable(self._target_source) and not inspect.isawaitable(self._target_source):
            return self._target_source
        raise RuntimeError("target is resolved asynchronously; use `await state.get_target()`")

    @property
    def checkpoint_store(self) -> CheckpointStore:
        """Return the checkpoint store for this state."""
        return self._checkpoint_store

    async def get_or_create_checkpoint_storage(self, session_id: str) -> CheckpointStorage:
        """Return the checkpoint storage for ``session_id``, creating and storing one if missing.

        Unlike an agent, a ``Workflow`` has no ``create_session``-style
        factory method, so "creating" one for a new ``session_id`` means
        allocating a fresh, empty :class:`InMemoryCheckpointStorage` -- there
        is nothing to restore yet. Pass the returned storage into
        ``workflow.run(checkpoint_storage=...)``. To resume a prior run for
        this ``session_id`` instead of starting fresh, call
        ``storage.get_latest(workflow_name=...)`` yourself first and pass its
        ``checkpoint_id`` into ``workflow.run(checkpoint_id=..., checkpoint_storage=...)``.

        Args:
            session_id: Opaque app-selected session id.

        Returns:
            The stored or newly created ``CheckpointStorage``.
        """
        storage = await self._checkpoint_store.get(session_id)
        if storage is None:
            storage = InMemoryCheckpointStorage()
            await self._checkpoint_store.set(session_id, storage)
        return storage

    async def set_checkpoint_storage(self, session_id: str, storage: CheckpointStorage) -> None:
        """Store ``storage`` under ``session_id`` in this state's checkpoint store.

        Args:
            session_id: Opaque app-selected session id.
            storage: Checkpoint storage to store.
        """
        await self._checkpoint_store.set(session_id, storage)
