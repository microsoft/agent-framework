# Copyright (c) Microsoft. All rights reserved.

"""Cross-platform shell discovery for :class:`LocalShellTool`."""

from __future__ import annotations

import os
import shutil
import sys
from collections.abc import Sequence

from ._types import ShellExecutionError

_ENV_OVERRIDE = "AGENT_FRAMEWORK_SHELL"


def resolve_shell(shell: str | Sequence[str] | None, *, interactive: bool) -> list[str]:
    """Resolve the shell invocation argv.

    Priority:

    1. Explicit ``shell`` argument (string is split via shlex rules; sequence
       is used verbatim).
    2. ``AGENT_FRAMEWORK_SHELL`` environment variable.
    3. Platform default.

    When ``interactive=False`` (stateless mode), the returned argv is
    guaranteed to end with a ``-c`` (POSIX) or ``-Command`` (PowerShell)
    flag so the caller can append a command string verbatim. Overrides
    that already include the flag are left as-is.

    Args:
        shell: Optional override supplied by the caller.
        interactive: When ``True`` (persistent mode), the returned argv is
            suitable for a long-lived session that reads commands from
            ``stdin``. When ``False`` (stateless mode), the caller will
            append a command string to this argv (so the argv must end
            with ``-c`` / ``-Command``).
    """
    if shell is not None:
        if isinstance(shell, str):
            import shlex

            parts = shlex.split(shell)
            if not parts:
                raise ShellExecutionError("shell override must not be empty")
        else:
            parts = list(shell)
            if not parts:
                raise ShellExecutionError("shell override must not be empty")
        return parts if interactive else _ensure_command_flag(parts)

    env_override = os.environ.get(_ENV_OVERRIDE)
    if env_override:
        import shlex

        parts = shlex.split(env_override)
        if parts:
            return parts if interactive else _ensure_command_flag(parts)

    if sys.platform == "win32":
        binary = shutil.which("pwsh") or shutil.which("powershell")
        if binary is None:
            raise ShellExecutionError(
                f"Neither 'pwsh' nor 'powershell' was found on PATH. Install PowerShell 7+ or set {_ENV_OVERRIDE}."
            )
        if interactive:
            # Interactive persistent session reads from stdin via '-'.
            return [binary, "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", "-"]
        return [binary, "-NoLogo", "-NoProfile", "-NonInteractive", "-Command"]

    for candidate in ("/bin/bash", "/usr/bin/bash", "/bin/sh", "/usr/bin/sh"):
        if os.path.exists(candidate):
            if interactive:
                return [candidate, "--noprofile", "--norc"] if candidate.endswith("bash") else [candidate]
            return [candidate, "-c"]
    # Last-ditch fallback: let PATH resolve 'sh'.
    sh = shutil.which("sh")
    if sh is None:
        raise ShellExecutionError(f"No POSIX shell found on PATH. Set {_ENV_OVERRIDE} to override.")
    return [sh] if interactive else [sh, "-c"]


def is_powershell(argv: Sequence[str]) -> bool:
    """Return True when ``argv[0]`` appears to be PowerShell."""
    if not argv:
        return False
    name = os.path.basename(argv[0]).lower()
    return name in {"pwsh", "pwsh.exe", "powershell", "powershell.exe"}


def _ensure_command_flag(argv: list[str]) -> list[str]:
    """Append the right ``-c`` / ``-Command`` flag for stateless argv.

    The caller (``run_stateless``) appends the user's command string
    verbatim to this argv. If a user-supplied override omits the
    ``-c`` / ``-Command`` flag, the command would be misinterpreted
    (POSIX shells treat the next positional arg as a script file
    path). This helper normalises overrides so they execute correctly
    in stateless mode.
    """
    if not argv:
        return argv
    last = argv[-1].lower()
    if is_powershell(argv):
        if last in {"-command", "-c"}:
            return argv
        return [*argv, "-Command"]
    if last == "-c":
        return argv
    return [*argv, "-c"]
