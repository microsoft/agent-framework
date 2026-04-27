# Copyright (c) Microsoft. All rights reserved.

"""Shell executor protocol.

A :class:`ShellExecutor` is the swappable backend for shell-tool execution.
``LocalShellTool`` runs commands directly on the host (no isolation;
approval-in-the-loop is the security boundary). ``DockerShellTool`` runs
them inside a container with resource limits, network isolation, and a
non-root user — the container itself is the security boundary, which is
why it can be used without approval gating for untrusted-input scenarios.

The protocol is intentionally minimal so callers can plug in their own
executor (e.g. a Firecracker microVM, a remote SSH host, a WASI runtime
that ships a busybox-WASM build) without forking the framework.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ._types import ShellResult


@runtime_checkable
class ShellExecutor(Protocol):
    """Async-context-manageable backend that runs shell commands."""

    async def start(self) -> None:
        """Eagerly initialise the backend (no-op if already started)."""

    async def close(self) -> None:
        """Tear down all backend resources. Idempotent."""

    async def run(self, command: str) -> ShellResult:
        """Execute ``command`` and return its result."""

    async def __aenter__(self) -> "ShellExecutor": ...

    async def __aexit__(self, *exc: object) -> None: ...
