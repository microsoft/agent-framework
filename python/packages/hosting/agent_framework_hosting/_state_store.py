# Copyright (c) Microsoft. All rights reserved.

"""Disk-backed wrapper for the host's session-alias map.

``AgentFrameworkHost.reset_session(isolation_key)`` rotates future requests for
that isolation key onto a new session id. Persisting the alias map lets that
rotation survive a host restart without introducing cross-channel identity or
delivery state into the core host.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any, TypeVar

from ._persistence import (
    acquire_state_dir_lock,
    load_diskcache,
    release_state_dir_lock,
)

logger = logging.getLogger(__name__)

_V = TypeVar("_V")
_ALIASES_PREFIX = "aliases:"


class SessionsStateStore:
    """One disk cache + lock for host-side session aliases."""

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
        """Return the underlying :mod:`diskcache` Cache."""
        return self._cache

    def close(self) -> None:
        """Close the cache and release the directory lock."""
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
    """Drop-in :class:`dict` whose mutations mirror to a diskcache prefix."""

    def __init__(
        self,
        store: SessionsStateStore,
        key_prefix: str,
        initial: Mapping[str, _V] | None = None,
    ) -> None:
        super().__init__()
        self._store = store
        self._prefix = key_prefix
        cache: Any = store.cache
        for raw_key in cache.iterkeys():
            if not isinstance(raw_key, str) or not raw_key.startswith(key_prefix):
                continue
            try:
                value: Any = cache.get(raw_key)
            except Exception:
                logger.exception("SessionsStateStore: failed to rehydrate %s; skipping", raw_key)
                continue
            logical_key = raw_key[len(key_prefix) :]
            super().__setitem__(logical_key, value)
        if initial:
            for key, value in initial.items():
                self[key] = value

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
        """Mirror ``dict.pop`` to disk."""
        value: _V = super().pop(key, *args)
        try:
            del self._store.cache[self._prefix + key]
        except KeyError:
            pass
        except Exception:  # pragma: no cover
            logger.exception("SessionsStateStore: failed to evict %s%s", self._prefix, key)
        return value

    def clear(self) -> None:
        """Mirror ``dict.clear`` to disk."""
        keys = list(self.keys())
        super().clear()
        cache = self._store.cache
        for key in keys:
            try:
                del cache[self._prefix + key]
            except KeyError:
                pass
            except Exception:  # pragma: no cover
                logger.exception("SessionsStateStore: failed to evict %s%s during clear", self._prefix, key)

    def update(  # type: ignore[override]
        self,
        other: Mapping[str, _V] | None = None,
        /,
        **kwargs: _V,
    ) -> None:
        """Mirror ``dict.update`` to disk one item at a time."""
        if other is not None:
            for key in other:
                self[key] = other[key]
        for key, value in kwargs.items():
            self[key] = value


def build_session_aliases(store: SessionsStateStore) -> dict[str, str]:
    """Return the disk-backed session-alias map for ``store``."""
    return _PersistedDict[str](store, _ALIASES_PREFIX)
