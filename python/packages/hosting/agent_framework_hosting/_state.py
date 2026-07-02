# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Mapping
from typing import Any, Generic, TypedDict, TypeVar

from agent_framework import AgentRunInputs, AgentSession, ChatOptions, SupportsAgentRun, Workflow


class SessionStore:
    """In-memory session lookup for non-persisted servers.

    The store maps application-selected session ids to ``AgentSession``
    instances. The id is an opaque partition key; callers are responsible for
    deciding whether it came from a trusted request field, platform context, or
    other route-local state.
    """

    def __init__(self, agent: SupportsAgentRun) -> None:
        """Create a session store for ``agent``.

        Args:
            agent: The agent that creates sessions when a session id is first
                observed.
        """
        self.agent = agent
        self._sessions: dict[str, AgentSession] = {}

    async def get(self, session_id: str) -> AgentSession:
        """Return the session for ``session_id``, creating it when needed.

        Args:
            session_id: Opaque app-selected session id.

        Returns:
            The cached or newly created ``AgentSession``.

        Raises:
            ValueError: If ``session_id`` is empty.
        """
        if not session_id:
            raise ValueError("session_id must be a non-empty string")
        if session_id not in self._sessions:
            self._sessions[session_id] = self.agent.create_session(session_id=session_id)
        return self._sessions[session_id]

    async def reset(self, session_id: str) -> None:
        """Forget the current session for ``session_id``.

        Args:
            session_id: Opaque app-selected session id.

        Raises:
            ValueError: If ``session_id`` is empty.
        """
        if not session_id:
            raise ValueError("session_id must be a non-empty string")
        self._sessions.pop(session_id, None)


TargetT = TypeVar("TargetT", SupportsAgentRun, Workflow)
SessionStoreFactory = Callable[[SupportsAgentRun], SessionStore]


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


class AgentFrameworkState(Generic[TargetT]):
    """Shared execution state for app-owned hosting routes.

    ``AgentFrameworkState`` intentionally does not own routes, middleware,
    protocol dispatch, or native SDK calls. Web frameworks keep those concerns;
    this object holds the Agent Framework target and optional session store that
    route code may share.
    """

    def __init__(
        self,
        target: TargetT | Awaitable[TargetT] | Callable[[], TargetT | Awaitable[TargetT]],
        *,
        session_store: SessionStore | type[SessionStore] | SessionStoreFactory | None = None,
        cache_target: bool = True,
    ) -> None:
        """Create shared state for ``target``.

        Args:
            target: Agent or workflow target used by route code. May be a
                target instance, a synchronous factory, an asynchronous factory,
                or an awaitable target.

        Keyword Args:
            session_store: Existing store, store class, or factory. When omitted
                and ``target`` is an agent, an in-memory ``SessionStore`` is
                created. Workflow targets do not get a default session store.
            cache_target: Whether to cache a resolved callable/awaitable target.
                Defaults to ``True`` so expensive target setup happens once.

        Raises:
            ValueError: If ``cache_target=False`` is used with a one-shot
                awaitable target.
            TypeError: If a session store class/factory is supplied for a
                workflow target.
        """
        if not cache_target and inspect.isawaitable(target):
            raise ValueError("cache_target=False requires a target instance or callable target factory")
        self._target_source = target
        self._cache_target = cache_target
        self._cached_target: TargetT | None = None
        self._session_store_source = session_store
        self._cached_session_store = session_store if isinstance(session_store, SessionStore) else None
        if not callable(target) and not inspect.isawaitable(target):
            self._cached_target = target
            if self._cached_session_store is None and isinstance(target, SupportsAgentRun):
                self._cached_session_store = self._init_session_store(target, session_store)
            elif session_store is not None and not isinstance(target, SupportsAgentRun):
                raise TypeError("session_store requires an agent target that supports create_session")

    async def get_target(self) -> TargetT:
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

    async def get_session_store(self) -> SessionStore:
        """Return the session store for the current target.

        Returns:
            The configured or lazily created ``SessionStore``.

        Raises:
            TypeError: If the resolved target is not an agent target.
        """
        if self._cached_session_store is not None:
            return self._cached_session_store

        target = await self.get_target()
        store = self._init_session_store(target, self._session_store_source)
        if self._cache_target:
            self._cached_session_store = store
        return store

    async def get_session(self, session_id: str) -> AgentSession:
        """Return the session for ``session_id`` from the current store.

        Args:
            session_id: Opaque app-selected session id.

        Returns:
            The cached or newly created ``AgentSession``.
        """
        store = await self.get_session_store()
        return await store.get(session_id)

    async def reset_session(self, session_id: str) -> None:
        """Forget the current session for ``session_id``.

        Args:
            session_id: Opaque app-selected session id.
        """
        store = await self.get_session_store()
        await store.reset(session_id)

    @property
    def target(self) -> TargetT:
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
    def session_store(self) -> SessionStore | None:
        """Return a synchronously available session store, if one is cached."""
        return self._cached_session_store

    def _init_session_store(
        self,
        target: TargetT,
        session_store: SessionStore | type[SessionStore] | SessionStoreFactory | None,
    ) -> SessionStore:
        if isinstance(session_store, SessionStore):
            return session_store

        if not isinstance(target, SupportsAgentRun):
            raise TypeError("session_store requires an agent target that supports create_session")

        if session_store is None:
            return SessionStore(target)

        return session_store(target)
