# Copyright (c) Microsoft. All rights reserved.

"""Cross-platform shell discovery for :class:`LocalShellTool`."""

from __future__ import annotations

import ntpath
import os
import shutil
import sys
from collections.abc import Sequence

from ._types import ShellExecutionError

_ENV_OVERRIDE = "AGENT_FRAMEWORK_SHELL"


def _is_fully_qualified(path: str) -> bool:
    """Return whether ``path`` names a fixed location that does not depend on the current directory."""
    drive, rest = ntpath.splitdrive(path)
    if drive.replace("/", "\\").startswith("\\\\"):
        # A UNC or device root such as \\server\share is complete without a trailing separator.
        return True
    return bool(drive) and rest[:1] in ("\\", "/")


def find_executable(name: str) -> str | None:
    """Find a bare executable name in the fully qualified entries of ``PATH``.

    The search follows Windows naming rules and never uses the current directory. Windows starts a
    bare name from the current directory of the host process before it reads ``PATH``, and
    :func:`shutil.which` puts that directory first too, so a file in that directory could replace the
    intended executable. Empty, relative, drive-relative, and drive-less rooted ``PATH`` entries
    depend on the current directory, so they are skipped.

    Args:
        name: A bare file name. ``.exe`` is added when it has no extension, as Windows does.

    Returns:
        The absolute path of the first match, or ``None`` when no fully qualified ``PATH`` entry holds
        the file. A match shows only that the file exists there, not who owns it or whether it can be
        trusted.
    """
    candidate = name if ntpath.splitext(name)[1] else f"{name}.exe"
    # PATH entries are sometimes quoted; Windows tools differ in whether they strip the quotes.
    for raw_entry in os.environ.get("PATH", "").split(ntpath.pathsep):
        entry = raw_entry.strip().strip('"')
        if not _is_fully_qualified(entry):
            continue
        path = ntpath.join(entry, candidate)
        if os.path.isfile(path):
            return path
    return None


def resolve_executable(name: str) -> str:
    """Return ``name`` in a form that can be launched without searching the current directory.

    On Windows a bare name is replaced by the path that :func:`find_executable` returns. Every other
    value is returned unchanged: names with a directory or a drive are an explicit choice of the caller,
    and other platforms do not search the current directory for bare names.

    Args:
        name: The executable name or path that the caller configured.

    Raises:
        FileNotFoundError: On Windows, when a bare name is not found in the fully qualified ``PATH``
            entries. The bare name is never used as a fallback.
    """
    if sys.platform != "win32" or ntpath.dirname(name) or ntpath.splitdrive(name)[0]:
        return name
    found = find_executable(name)
    if found is None:
        raise FileNotFoundError(
            f"Executable {name!r} was not found in the fully qualified entries of PATH. "
            "The current directory and relative PATH entries are not searched."
        )
    return found


def _qualify_shell(parts: list[str]) -> list[str]:
    """Resolve the executable of an explicit shell override."""
    try:
        return [resolve_executable(parts[0]), *parts[1:]]
    except FileNotFoundError as exc:
        raise ShellExecutionError(str(exc)) from exc


def resolve_shell(shell: str | Sequence[str] | None, *, interactive: bool) -> list[str]:
    """Resolve the shell invocation argv.

    Priority:

    1. Explicit ``shell`` argument (string is split via shlex rules; sequence
       is used verbatim).
    2. ``AGENT_FRAMEWORK_SHELL`` environment variable.
    3. Platform default.

    On Windows, a bare shell name (the default or an override) is resolved from the fully
    qualified entries of ``PATH``; the current directory is never searched. Names that contain
    a directory or a drive are used as given.

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
        parts = _qualify_shell(parts)
        return parts if interactive else _ensure_command_flag(parts)

    env_override = os.environ.get(_ENV_OVERRIDE)
    if env_override:
        import shlex

        parts = shlex.split(env_override)
        if parts:
            parts = _qualify_shell(parts)
            return parts if interactive else _ensure_command_flag(parts)

    if sys.platform == "win32":
        binary = find_executable("pwsh") or find_executable("powershell")
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
