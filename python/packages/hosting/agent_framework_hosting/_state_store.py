# Copyright (c) Microsoft. All rights reserved.

"""Disk-backed wrappers for the host's in-memory state dicts.

The host keeps three in-process dictionaries that need to survive a
process restart when the operator opts in to disk persistence:

- ``_session_aliases`` (``isolation_key -> active session_id``): rotated
  by :meth:`AgentFrameworkHost.reset_session`; without persistence a
  restart silently re-uses the pre-rotation session_id and the user sees
  history they were supposed to have walked away from.
- ``_active`` (``isolation_key -> last-seen channel name``): drives
  :class:`ResponseTarget` ``.active`` fan-out; losing it on restart makes
  :class:`ResponseTarget.active` raise ``"no active channel"`` for every
  user the host has previously talked to.
- ``_identities``
  (``isolation_key -> {channel_name -> ChannelIdentity}``): the per-user
  channel registry that powers :class:`ResponseTarget` ``.channel(name)``,
  ``.channels([...])`` and ``.all_linked``; losing it on restart turns
  every linked-identity push target into a not-found.

Both wrappers are :class:`dict` subclasses so the rest of the host code
doesn't need to know whether persistence is on or off; the only
difference is that mutations are mirrored back to a
:mod:`diskcache`-backed sqlite store. Reads stay fast because the
in-memory copy is the source of truth — disk is purely a backing
store for write-through and re-hydration.

Layout under ``<state_dir>/sessions/`` (the ``sessions`` component
chosen because all three dicts share the same per-user-life cycle):

    <state_dir>/sessions/
        .lock                  # single-owner lock (advisory)
        cache.db, …            # diskcache sqlite files
        keyed by:
            "aliases:<isolation_key>"     -> str (session_id)
            "active:<isolation_key>"      -> str (channel name)
            "identities:<isolation_key>"  -> dict[channel_name, ChannelIdentity]

Pickle is what diskcache uses by default; the wrappers do not impose
their own serialisation. :class:`ChannelIdentity` is a frozen dataclass
of plain scalars and so round-trips cleanly.

Everything in this module is internal. Public consumers should use
:class:`AgentFrameworkHost(state_dir=...)` and let the host wire the
wrappers up.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any, TypeVar, cast

from ._persistence import (
    acquire_state_dir_lock,
    load_diskcache,
    release_state_dir_lock,
)

logger = logging.getLogger(__name__)


_V = TypeVar("_V")


# Key prefixes inside the shared sessions cache. Three logical maps live
# in one diskcache so they share a single sqlite handle and a single
# directory lock — opening multiple diskcaches against the same
# directory is supported but doubles file-handle pressure and the
# per-open lock acquisition cost.
_ALIASES_PREFIX = "aliases:"
_ACTIVE_PREFIX = "active:"
_IDENTITIES_PREFIX = "identities:"


class SessionsStateStore:
    """One disk cache + lock shared by every host-side persisted dict.

    The host constructs one of these per ``state_dir["sessions"]`` value
    and threads it into each :class:`_PersistedDict` it creates. Closing
    the store releases the lock and the cache handle.
    """

    def __init__(self, sessions_dir: str | os.PathLike[str]) -> None:
        self._sessions_dir: Path = Path(os.fspath(sessions_dir))
        diskcache = load_diskcache()
        self._lock_handle: Any = acquire_state_dir_lock(self._sessions_dir)
        try:
            self._cache: Any = diskcache.Cache(str(self._sessions_dir))
        except Exception:
            release_state_dir_lock(self._lock_handle)
            self._lock_handle = None
            raise

    @property
    def cache(self) -> Any:
        """Return the underlying :mod:`diskcache` Cache.

        Intended for the wrapper classes in this module only. Callers
        outside the module should go through the typed wrappers — direct
        cache access bypasses the key-prefix discipline that keeps the
        three maps from colliding.
        """
        return self._cache

    def close(self) -> None:
        """Close the cache and release the directory lock.

        Safe to call multiple times. The host invokes this from its
        lifespan shutdown hook so a second host can re-open the same
        ``state_dir`` cleanly after the first exits.
        """
        if self._cache is not None:
            try:
                self._cache.close()
            except Exception:  # pragma: no cover - close errors aren't actionable
                logger.exception("SessionsStateStore: failed to close cache cleanly")
            self._cache = None
        if self._lock_handle is not None:
            release_state_dir_lock(self._lock_handle)
            self._lock_handle = None


class _PersistedDict(dict[str, _V]):
    """Drop-in :class:`dict` whose mutations mirror to a diskcache prefix.

    Used for the host's flat ``str -> V`` dicts (``_session_aliases``
    and ``_active``). The in-memory copy is the source of truth for
    reads; writes update memory first and then mirror to disk so a
    crash between the two leaves the in-memory state correct (which is
    what subsequent reads will see anyway) and only loses the last
    not-yet-flushed value on next restart.
    """

    def __init__(
        self,
        store: SessionsStateStore,
        key_prefix: str,
        initial: Mapping[str, _V] | None = None,
    ) -> None:
        super().__init__()
        self._store = store
        self._prefix = key_prefix
        # Rehydrate from disk into memory exactly once at construction.
        # Doing this here (rather than lazily) keeps the in-memory dict
        # behaviour consistent with the non-persisted code path —
        # ``len(host._session_aliases)`` reflects all known users from
        # the moment the host is constructed.
        cache: Any = store.cache
        for raw_key in cache.iterkeys():
            if not isinstance(raw_key, str) or not raw_key.startswith(key_prefix):
                continue
            value: Any
            try:
                value = cache.get(raw_key)
            except Exception:
                logger.exception("SessionsStateStore: failed to rehydrate %s; skipping", raw_key)
                continue
            logical_key = raw_key[len(key_prefix) :]
            super().__setitem__(logical_key, value)
        if initial:
            for k, v in initial.items():
                self[k] = v

    def __setitem__(self, key: str, value: _V) -> None:
        super().__setitem__(key, value)
        try:
            self._store.cache.set(self._prefix + key, value)
        except Exception:  # pragma: no cover - cache write failures aren't actionable
            logger.exception("SessionsStateStore: failed to persist %s%s", self._prefix, key)

    def __delitem__(self, key: str) -> None:
        super().__delitem__(key)
        try:
            del self._store.cache[self._prefix + key]
        except KeyError:
            pass
        except Exception:  # pragma: no cover - cache write failures aren't actionable
            logger.exception("SessionsStateStore: failed to evict %s%s", self._prefix, key)

    def pop(self, key: str, *args: Any) -> _V:
        # ``dict.pop`` doesn't go through ``__delitem__``, so we mirror
        # the disk side here explicitly. Forward the default sentinel
        # only when present so we match ``dict.pop`` semantics exactly.
        value: _V = super().pop(key, *args)
        try:
            del self._store.cache[self._prefix + key]
        except KeyError:
            pass
        except Exception:  # pragma: no cover
            logger.exception("SessionsStateStore: failed to evict %s%s", self._prefix, key)
        return value

    def clear(self) -> None:
        keys = list(self.keys())
        super().clear()
        cache = self._store.cache
        for k in keys:
            try:
                del cache[self._prefix + k]
            except KeyError:
                pass
            except Exception:  # pragma: no cover
                logger.exception("SessionsStateStore: failed to evict %s%s during clear", self._prefix, k)

    def update(  # type: ignore[override]
        self,
        other: Mapping[str, _V] | None = None,
        /,
        **kwargs: _V,
    ) -> None:
        # Defer to __setitem__ so every entry is mirrored to disk; the
        # default ``dict.update`` writes into the underlying storage
        # directly and would skip our persistence hook.
        if other is not None:
            for k in other:
                self[k] = other[k]
        for k, v in kwargs.items():
            self[k] = v


class _PersistedNestedDict(dict[str, dict[str, _V]]):
    """Disk-backed wrapper for the per-isolation-key identity map.

    The host's ``_identities`` is a nested dict
    ``isolation_key -> {channel_name -> ChannelIdentity}``. The whole
    inner dict for a given isolation_key is small (one entry per channel
    the user has appeared on), so we persist the inner dict as a single
    cache value rather than per-channel — fewer cache hits, simpler
    schema, no need for a separate sub-prefix.

    To make mutations of the inner dict mirror to disk, ``__getitem__``
    returns a ``_NestedInnerProxy`` that mutates the parent's cache slot
    on each ``__setitem__`` / ``__delitem__``. The wrapper is purely
    additive — callers that pass a plain dict in via ``__setitem__`` get
    the same write-through behaviour for free.
    """

    def __init__(
        self,
        store: SessionsStateStore,
        key_prefix: str = _IDENTITIES_PREFIX,
    ) -> None:
        super().__init__()
        self._store = store
        self._prefix = key_prefix
        cache: Any = store.cache
        for raw_key in cache.iterkeys():
            if not isinstance(raw_key, str) or not raw_key.startswith(key_prefix):
                continue
            value: Any
            try:
                value = cache.get(raw_key)
            except Exception:
                logger.exception("SessionsStateStore: failed to rehydrate %s; skipping", raw_key)
                continue
            if not isinstance(value, dict):
                continue
            inner_value = cast(dict[str, _V], value)
            logical_key = raw_key[len(key_prefix) :]
            # Wrap so caller-side mutations on the inner dict mirror back.
            inner: _NestedInnerProxy[_V] = _NestedInnerProxy(self, logical_key, inner_value)
            super().__setitem__(logical_key, inner)

    def __setitem__(self, key: str, value: dict[str, _V]) -> None:
        # Wrap whatever the caller passes in so subsequent ``inner[ch] = ...``
        # mutations are mirrored to disk. We always wrap (even
        # ``_NestedInnerProxy`` inputs) so the proxy's ``_outer`` link
        # points at us rather than at any previous outer dict.
        wrapped = _NestedInnerProxy(self, key, dict(value))
        super().__setitem__(key, wrapped)
        self.persist_inner(key, dict(value))

    def __delitem__(self, key: str) -> None:
        super().__delitem__(key)
        try:
            del self._store.cache[self._prefix + key]
        except KeyError:
            pass
        except Exception:  # pragma: no cover
            logger.exception("SessionsStateStore: failed to evict %s%s", self._prefix, key)

    def setdefault(self, key: str, default: dict[str, _V] | None = None) -> dict[str, _V]:  # type: ignore[override]
        if key in self:
            return self[key]
        if default is None:
            default = {}
        self[key] = default
        return self[key]

    def persist_inner(self, isolation_key: str, snapshot: Mapping[str, _V]) -> None:
        """Write the full inner dict for ``isolation_key`` back to disk.

        Called from :class:`_NestedInnerProxy` on every mutation and by
        :meth:`__setitem__` when a new outer key is added. A single
        write per change keeps the schema simple — there is no
        partial-row update — and is fine for the access pattern
        (mutations on the host's hot path are rare: identity registry
        writes are once-per-channel-per-user).
        """
        try:
            self._store.cache.set(self._prefix + isolation_key, snapshot)
        except Exception:  # pragma: no cover - cache write failures aren't actionable
            logger.exception(
                "SessionsStateStore: failed to persist identities for %s%s",
                self._prefix,
                isolation_key,
            )


class _NestedInnerProxy(dict[str, _V]):
    """Inner-dict proxy that mirrors mutations back to its outer.

    Returned by :class:`_PersistedNestedDict.__getitem__` (via the
    rehydration / ``__setitem__`` wrap). When the channel-registry code
    does ``self._identities[ik][channel_name] = identity``, the
    ``__setitem__`` on this proxy fires and re-writes the whole inner
    dict to disk via the parent's ``persist_inner``. Behavioural
    identity with ``dict`` is preserved otherwise (``len``, iteration,
    ``__contains__``, …).
    """

    _outer: _PersistedNestedDict[_V]
    _key: str

    __slots__ = ("_key", "_outer")

    def __init__(
        self,
        outer: _PersistedNestedDict[_V],
        key: str,
        data: Mapping[str, _V],
    ) -> None:
        super().__init__(data)
        # ``__slots__`` on a ``dict`` subclass requires the back-door —
        # CPython is lenient, PyPy is strict.
        object.__setattr__(self, "_outer", outer)
        object.__setattr__(self, "_key", key)

    def __setitem__(self, key: str, value: _V) -> None:
        super().__setitem__(key, value)
        self._outer.persist_inner(self._key, dict(self))

    def __delitem__(self, key: str) -> None:
        super().__delitem__(key)
        self._outer.persist_inner(self._key, dict(self))

    def pop(self, key: str, *args: Any) -> _V:
        value: _V = super().pop(key, *args)
        self._outer.persist_inner(self._key, dict(self))
        return value

    def clear(self) -> None:
        super().clear()
        self._outer.persist_inner(self._key, dict(self))

    def update(  # type: ignore[override]
        self,
        other: Mapping[str, _V] | None = None,
        /,
        **kwargs: _V,
    ) -> None:
        if other is not None:
            for k in other:
                super().__setitem__(k, other[k])
        for k, v in kwargs.items():
            super().__setitem__(k, v)
        self._outer.persist_inner(self._key, dict(self))


def build_session_dicts(
    store: SessionsStateStore,
) -> tuple[
    _PersistedDict[str],
    _PersistedDict[str],
    _PersistedNestedDict[Any],
]:
    """Construct the three host-side persisted dicts against a single store.

    Returns ``(session_aliases, active, identities)`` in the order the
    host assigns them, so the call site reads
    ``self._session_aliases, self._active, self._identities = build_session_dicts(store)``.
    """
    aliases: _PersistedDict[str] = _PersistedDict(store, _ALIASES_PREFIX)
    active: _PersistedDict[str] = _PersistedDict(store, _ACTIVE_PREFIX)
    identities: _PersistedNestedDict[Any] = _PersistedNestedDict(store)
    return aliases, active, identities


# Re-export keys for tests / power users that want to inspect the cache.
__all__ = [
    "_ACTIVE_PREFIX",
    "_ALIASES_PREFIX",
    "_IDENTITIES_PREFIX",
    "SessionsStateStore",
    "_PersistedDict",
    "_PersistedNestedDict",
    "build_session_dicts",
]
