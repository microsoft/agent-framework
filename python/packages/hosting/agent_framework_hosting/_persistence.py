# Copyright (c) Microsoft. All rights reserved.

"""Shared persistence primitives for the hosting package.

The hosting core ships with an opt-in disk-persistence layer for the
in-process task runner and the host's session-related state. The
on-disk format is provided by the ``diskcache`` package (a small,
pure-Python, sqlite-backed dependency installed via the ``[disk]``
optional extra).

This module centralises:

- :func:`load_diskcache` — lazy import that raises a helpful error when
  the optional extra is missing.
- :func:`acquire_state_dir_lock` — single-owner file lock that fails
  fast when a second process points at the same directory.
- :func:`normalize_state_dir` — turn the host-level ``state_dir``
  parameter (``str`` / ``PathLike`` / :class:`HostStatePaths` /
  ``Mapping``) into a normalised ``dict[component_name -> Path | None]``.

Everything in this module is internal — public callers should go
through :class:`AgentFrameworkHost` or
:class:`InProcessTaskRunner` directly.
"""

from __future__ import annotations

import contextlib
import os
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ._types import HostStatePaths

# Known component keys recognised by the host's ``state_dir`` normaliser.
# Adding a new component is a non-breaking change: extend this tuple and
# add the matching key to :class:`HostStatePaths` in ``_types.py``.
_KNOWN_COMPONENTS: tuple[str, ...] = ("runner", "sessions", "checkpoints", "links")


def load_diskcache() -> Any:
    """Lazy-import :mod:`diskcache` with a helpful error when missing.

    The ``diskcache`` package is an optional dependency installed via
    the ``agent-framework-hosting[disk]`` extra. Users that never set
    ``state_dir`` never trigger the import. This wrapper produces a
    single, consistent error message when the import is needed but the
    extra was not installed.
    """
    try:
        import diskcache  # type: ignore[import-untyped]
    except ImportError as exc:  # pragma: no cover - exercised via tests by monkeypatching
        raise ImportError(
            "agent-framework-hosting was asked to persist state to disk "
            "(state_dir is set) but the optional `diskcache` dependency "
            "is not installed. Install the disk extra: "
            "`pip install 'agent-framework-hosting[disk]'`."
        ) from exc
    return diskcache


def acquire_state_dir_lock(component_dir: Path) -> Any:
    """Acquire an exclusive single-owner lock on a component's state dir.

    Two processes pointing at the same state directory would both scan
    pending records on startup and could execute the same task twice;
    we therefore enforce single-owner semantics with an OS-level
    advisory lock. The lock file lives at ``<component_dir>/.lock`` and
    is held for the lifetime of the returned file handle. Closing the
    handle (or process exit) releases it.

    On Unix this uses :func:`fcntl.flock`. On Windows it uses
    :func:`msvcrt.locking`. The lock is *advisory* — the OS will not
    enforce it against processes that ignore it, but no
    well-behaved component of this package will.

    Raises ``RuntimeError`` if another process already holds the lock.
    """
    component_dir.mkdir(parents=True, exist_ok=True)
    lock_path = component_dir / ".lock"
    # Open in append mode so we don't truncate an existing lock file
    # (some monitoring tools may inspect it).
    fh = open(lock_path, "a+", encoding="utf-8")  # noqa: SIM115 - kept open for lifetime
    try:
        if sys.platform == "win32":
            import msvcrt

            try:
                msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                fh.close()
                raise RuntimeError(
                    f"Another process already holds the hosting state lock at {lock_path}. "
                    "Two hosts (or two runners) pointing at the same state directory would "
                    "double-execute scheduled tasks; point each host at its own state_dir."
                ) from exc
        else:
            import fcntl

            try:
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                fh.close()
                raise RuntimeError(
                    f"Another process already holds the hosting state lock at {lock_path}. "
                    "Two hosts (or two runners) pointing at the same state directory would "
                    "double-execute scheduled tasks; point each host at its own state_dir."
                ) from exc
    except RuntimeError:
        raise
    except Exception:
        fh.close()
        raise
    return fh


def release_state_dir_lock(handle: Any) -> None:
    """Release a lock previously acquired by :func:`acquire_state_dir_lock`.

    Closing the file handle is sufficient to drop the lock on both
    platforms, but we make the intent explicit so the caller doesn't
    have to know which mechanism (``fcntl`` vs ``msvcrt``) is in use.
    """
    if handle is None:
        return
    with contextlib.suppress(Exception):  # close errors are not actionable
        handle.close()


def normalize_state_dir(
    state_dir: str | os.PathLike[str] | HostStatePaths | Mapping[str, str | os.PathLike[str]] | None,
) -> dict[str, Path | None]:
    """Resolve the host-level ``state_dir`` parameter into a per-component map.

    Accepts any of:

    - ``None`` → all components return ``None`` (fully in-memory; today's behavior).
    - ``str`` / :class:`os.PathLike` → all components share a parent
      directory and get an auto-allocated subfolder (``runner/``,
      ``sessions/``, ``checkpoints/``, ``links/``).
    - :class:`HostStatePaths` typed dict / plain ``Mapping`` → per-key
      override. Components missing from the mapping fall back to ``None``
      (in-memory only). Unknown keys raise ``ValueError`` to surface
      typos early.

    Returns a ``dict[component_name -> Path | None]`` covering every
    component in :data:`_KNOWN_COMPONENTS`.
    """
    result: dict[str, Path | None] = {name: None for name in _KNOWN_COMPONENTS}
    if state_dir is None:
        return result

    # Strings and PathLikes use the default subfolder layout.
    if isinstance(state_dir, (str, os.PathLike)):
        root = Path(os.fspath(state_dir))
        for name in _KNOWN_COMPONENTS:
            result[name] = root / name
        return result

    # Mappings (incl. TypedDict at runtime) get per-component overrides.
    if isinstance(state_dir, Mapping):
        unknown = [k for k in state_dir if k not in _KNOWN_COMPONENTS]
        if unknown:
            raise ValueError(
                f"state_dir mapping contains unknown component key(s): {unknown!r}. "
                f"Known components are: {list(_KNOWN_COMPONENTS)!r}. "
                "If you are trying to use a future component, upgrade "
                "agent-framework-hosting to a version that supports it."
            )
        for name in _KNOWN_COMPONENTS:
            raw_value: Any = state_dir.get(name)
            if raw_value is None:
                result[name] = None
                continue
            if isinstance(raw_value, (str, os.PathLike)):
                result[name] = Path(os.fspath(raw_value))
            else:
                raise TypeError(f"state_dir[{name!r}] must be a str or PathLike — got {type(raw_value).__name__}")
        return result

    raise TypeError(
        f"state_dir must be a str, PathLike, HostStatePaths mapping, or None — got {type(state_dir).__name__}"
    )


__all__ = [
    "_KNOWN_COMPONENTS",
    "acquire_state_dir_lock",
    "load_diskcache",
    "normalize_state_dir",
    "release_state_dir_lock",
]
