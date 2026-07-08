# Copyright (c) Microsoft. All rights reserved.

"""Shared persistence primitives for the hosting package.

The simplified hosting core keeps disk persistence only for session aliases
created by :meth:`AgentFrameworkHost.reset_session` and for workflow
checkpoint path derivation. The on-disk session-alias store uses the optional
``diskcache`` package installed via the ``[disk]`` extra.
"""

from __future__ import annotations

import contextlib
import importlib
import os
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ._types import HostStatePaths

_KNOWN_COMPONENTS: tuple[str, ...] = ("sessions", "checkpoints")


def load_diskcache() -> Any:
    """Lazy-import :mod:`diskcache` with a helpful error when missing."""
    try:
        return importlib.import_module("diskcache")
    except ImportError as exc:  # pragma: no cover - exercised via tests by monkeypatching
        raise ImportError(
            "agent-framework-hosting was asked to persist session aliases to disk "
            "(state_dir['sessions'] is set) but the optional `diskcache` dependency "
            "is not installed. Install the disk extra: "
            "`pip install 'agent-framework-hosting[disk]`."
        ) from exc


def acquire_state_dir_lock(component_dir: Path) -> Any:
    """Acquire an exclusive single-owner lock on a component's state dir.

    Raises:
        RuntimeError: If another process already holds the lock.
    """
    component_dir.mkdir(parents=True, exist_ok=True)
    lock_path = component_dir / ".lock"
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
                    "Point each host at its own state_dir."
                ) from exc
        else:
            import fcntl

            try:
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                fh.close()
                raise RuntimeError(
                    f"Another process already holds the hosting state lock at {lock_path}. "
                    "Point each host at its own state_dir."
                ) from exc
    except RuntimeError:
        raise
    except Exception:
        fh.close()
        raise
    return fh


def release_state_dir_lock(handle: Any) -> None:
    """Release a lock previously acquired by :func:`acquire_state_dir_lock`."""
    if handle is None:
        return
    with contextlib.suppress(Exception):
        handle.close()


def normalize_state_dir(
    state_dir: str | os.PathLike[str] | HostStatePaths | Mapping[str, str | os.PathLike[str]] | None,
) -> dict[str, Path | None]:
    """Resolve the host-level ``state_dir`` parameter into a per-component map.

    Accepts ``None``, a single root path, or a mapping with ``sessions`` and
    ``checkpoints`` keys. Unknown keys raise ``ValueError`` so obsolete
    ``runner`` / ``links`` configuration is rejected instead of silently
    doing nothing.
    """
    result: dict[str, Path | None] = {name: None for name in _KNOWN_COMPONENTS}
    if state_dir is None:
        return result

    if isinstance(state_dir, (str, os.PathLike)):
        root = Path(os.fspath(state_dir))
        for name in _KNOWN_COMPONENTS:
            result[name] = root / name
        return result

    if isinstance(state_dir, Mapping):
        unknown = [k for k in state_dir if k not in _KNOWN_COMPONENTS]
        if unknown:
            raise ValueError(
                f"state_dir mapping contains unknown component key(s): {unknown!r}. "
                f"Known components are: {list(_KNOWN_COMPONENTS)!r}."
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
