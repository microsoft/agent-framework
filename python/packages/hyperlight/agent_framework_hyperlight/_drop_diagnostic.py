# Copyright (c) Microsoft. All rights reserved.
"""Diagnostic instrumentation for the recurring unsendable WasmSandbox Drop bug.

When the env var ``HYPERLIGHT_TRACE_DROPS=1`` is set, this module installs a process-wide
``sys.unraisablehook`` that detects PyO3 unsendable Drop errors and dumps:

* The thread that triggered the Drop (name + ident).
* The full per-thread Python stack at that moment.
* The list of currently tracked sandbox/snapshot owner threads.

This is intended ONLY for live diagnosis in a deployed container. It has no behavioural
effect when the env var is not set.
"""

from __future__ import annotations

import logging
import os
import sys
import threading
import traceback
from contextlib import suppress
from typing import Any

_LOGGER = logging.getLogger("agent_framework_hyperlight.drop_diagnostic")

_ENABLED = os.environ.get("HYPERLIGHT_TRACE_DROPS", "").strip() == "1"
_state: dict[str, Any] = {"installed": False, "original_hook": None}
_LOCK = threading.RLock()
# obj_id -> (owner_thread_id, owner_thread_name, label)
_TRACKED: dict[int, tuple[int, str, str]] = {}


def is_enabled() -> bool:
    return _ENABLED


def install() -> None:
    """Install the diagnostic ``sys.unraisablehook`` once per process.

    Safe to call repeatedly. No-op when ``HYPERLIGHT_TRACE_DROPS`` is not set to ``1``.
    """
    if _state["installed"] or not _ENABLED:
        return
    _state["installed"] = True
    _state["original_hook"] = sys.unraisablehook
    sys.unraisablehook = _hook  # type: ignore[assignment]
    _LOGGER.warning(
        "HYPERLIGHT_TRACE_DROPS=1: installed unraisablehook to capture cross-thread WasmSandbox Drop diagnostics."
    )


def track(obj: object, label: str) -> None:
    """Record a sandbox/snapshot's owner thread for later diagnostic output."""
    if not _ENABLED:
        return
    owner_id = threading.get_ident()
    owner_name = threading.current_thread().name
    with _LOCK:
        _TRACKED[id(obj)] = (owner_id, owner_name, label)
    _LOGGER.info(
        "[drop-diag] tracking %s (id=%s) created on thread %s (id=%s)",
        label,
        id(obj),
        owner_name,
        owner_id,
    )


def untrack(obj: object) -> None:
    if not _ENABLED:
        return
    with _LOCK:
        _TRACKED.pop(id(obj), None)


def _dump_thread_stacks() -> str:
    buf: list[str] = []
    current_frames = sys._current_frames()  # type: ignore[attr-defined]  # diagnostic only
    for tid, frame in current_frames.items():
        thread_name = "?"
        for thread in threading.enumerate():
            if thread.ident == tid:
                thread_name = thread.name
                break
        buf.append(f"--- Thread {thread_name!r} (id={tid}) ---")
        buf.extend(traceback.format_stack(frame))
    return "\n".join(buf)


def _hook(unraisable: Any, /) -> None:
    try:
        exc_value = getattr(unraisable, "exc_value", None)
        exc_msg = str(exc_value) if exc_value is not None else ""
        if "unsendable" in exc_msg.lower() or "WasmSandbox" in exc_msg or "PySnapshot" in exc_msg:
            with _LOCK:
                tracked_snapshot = list(_TRACKED.values())
            current_thread = threading.current_thread()
            _LOGGER.error(
                "[drop-diag] CROSS-THREAD UNSENDABLE DROP DETECTED on thread %s (id=%s).\n"
                "Exception: %s\n"
                "Tracked sandboxes/snapshots (owner_id, owner_name, label):\n  %s\n"
                "Per-thread stacks at time of Drop:\n%s",
                current_thread.name,
                threading.get_ident(),
                exc_msg,
                "\n  ".join(repr(t) for t in tracked_snapshot) or "<none>",
                _dump_thread_stacks(),
            )
    except Exception as exc:  # never raise from an unraisablehook
        _LOGGER.exception("[drop-diag] hook itself failed: %s", exc)
    finally:
        original_hook = _state.get("original_hook")
        if original_hook is not None:
            with suppress(Exception):
                original_hook(unraisable)
