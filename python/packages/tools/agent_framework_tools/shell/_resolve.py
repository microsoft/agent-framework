# Copyright (c) Microsoft. All rights reserved.

"""Cross-platform shell discovery for :class:`LocalShellTool`."""

from __future__ import annotations

import ntpath
import os
import posixpath
import shlex
import sys
from collections.abc import Mapping, Sequence

from ._types import ShellExecutionError

_ENV_OVERRIDE = "AGENT_FRAMEWORK_SHELL"
_NO_CURRENT_DIRECTORY_SEARCH = "NoDefaultCurrentDirectoryInExePath"


def _is_fully_qualified(path: str) -> bool:
    """Return whether the Windows ``path`` names a fixed location that does not depend on the current directory."""
    drive, rest = ntpath.splitdrive(path)
    if drive.replace("/", "\\").startswith("\\\\"):
        # A UNC or device root such as \\server\share is complete without a trailing separator.
        return True
    return bool(drive) and rest[:1] in ("\\", "/")


def _split_shell_string(value: str) -> list[str]:
    """Split a shell override string into argv.

    On Windows, path separators are kept as written and a path that contains spaces must be wrapped in
    double quotes, which are then removed. Elsewhere POSIX shell rules apply.
    """
    if sys.platform == "win32":
        return [
            part[1:-1] if len(part) >= 2 and part[0] == part[-1] == '"' else part
            for part in shlex.split(value, posix=False)
        ]
    return shlex.split(value)


def find_executable(name: str) -> str | None:
    """Find a bare executable name in the fully qualified entries of ``PATH``.

    The current directory is never searched. Empty and relative ``PATH`` entries (and, on Windows,
    drive-relative and drive-less rooted entries) depend on the current directory, so they are
    skipped. :func:`shutil.which` does not skip them, and on Windows it puts the current directory
    first, so a file planted there could replace the intended executable.

    Args:
        name: A bare file name. On Windows only ``.exe`` files are found; ``.exe`` is added when the
            name has no extension.

    Returns:
        The absolute path of the first match, or ``None`` when no fully qualified ``PATH`` entry holds
        the file. A match shows only that the file exists there, not who owns it or whether it can be
        trusted.
    """
    if sys.platform == "win32":
        extension = ntpath.splitext(name)[1]
        if extension and extension.lower() != ".exe":
            return None
        candidate = name if extension else f"{name}.exe"
        # PATH entries are sometimes quoted; Windows tools differ in whether they strip the quotes.
        for raw_entry in os.environ.get("PATH", "").split(ntpath.pathsep):
            entry = raw_entry.strip().strip('"')
            if not _is_fully_qualified(entry):
                continue
            path = ntpath.join(entry, candidate)
            if os.path.isfile(path):
                return path
        return None

    for entry in os.environ.get("PATH", "").split(posixpath.pathsep):
        if not posixpath.isabs(entry):
            continue
        path = posixpath.join(entry, name)
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    return None


def require_full_path(value: str, *, source: str) -> str:
    """Return ``value`` if it is a full path to an executable, otherwise raise.

    Short names and relative paths are rejected because they can be resolved from the current
    directory. On Windows the path must also end in a file extension such as ``.exe``. The file is
    not checked for existence; a missing file fails when it is launched.

    Args:
        value: The executable path that the caller configured.
        source: Where the value came from, used in the error message.

    Raises:
        ValueError: When ``value`` is not a full path (or, on Windows, has no file extension).
    """
    if sys.platform == "win32":
        if not _is_fully_qualified(value) or not ntpath.splitext(value)[1]:
            raise ValueError(
                f"{source} must be a full path to the executable including its extension, "
                rf"for example 'C:\Program Files\PowerShell\7\pwsh.exe'; got {value!r}."
            )
        return value
    if not posixpath.isabs(value):
        raise ValueError(f"{source} must be a full path to the executable, for example '/usr/bin/zsh'; got {value!r}.")
    return value


def restrict_executable_search(env: Mapping[str, str]) -> dict[str, str]:
    """Return a copy of ``env`` whose ``PATH`` only searches fully qualified directories.

    Empty and relative ``PATH`` entries are removed so commands run by the shell are never looked up
    in the current directory. On Windows the ``PATH`` key is matched without regard to case, and
    ``NoDefaultCurrentDirectoryInExePath`` is set so ``cmd.exe`` does not search the current
    directory first.

    Raises:
        ValueError: On Linux and macOS, when ``PATH`` is missing or has no fully qualified entry left.
            POSIX shells search the current directory when ``PATH`` is empty, and ``bash`` falls back
            to a built-in search path that can include it when ``PATH`` is missing.
    """
    result = dict(env)
    if sys.platform == "win32":
        for key in [key for key in result if key.upper() == "PATH"]:
            entries = result[key].split(ntpath.pathsep)
            result[key] = ntpath.pathsep.join(e for e in entries if _is_fully_qualified(e.strip().strip('"')))
        result[_NO_CURRENT_DIRECTORY_SEARCH] = "1"
        return result

    kept = [e for e in result.get("PATH", "").split(posixpath.pathsep) if posixpath.isabs(e)]
    if not kept:
        raise ValueError(
            "The shell's PATH must contain at least one full directory path, such as '/usr/bin'. "
            "Empty and relative PATH entries are removed, and an empty or missing PATH would search "
            "the current directory. Set PATH in env (required when clean_env=True)."
        )
    result["PATH"] = posixpath.pathsep.join(kept)
    return result


def _qualify_shell(parts: list[str], *, source: str) -> list[str]:
    """Check that the executable of an explicit shell override is a full path."""
    try:
        return [require_full_path(parts[0], source=source), *parts[1:]]
    except ValueError as exc:
        raise ShellExecutionError(str(exc)) from exc


def resolve_shell(shell: str | Sequence[str] | None, *, interactive: bool) -> list[str]:
    """Resolve the shell invocation argv.

    Priority:

    1. Explicit ``shell`` argument (a string is split into arguments; on
       Windows a path with spaces must be in double quotes; a sequence is
       used verbatim).
    2. ``AGENT_FRAMEWORK_SHELL`` environment variable.
    3. Platform default.

    An override (``shell`` or ``AGENT_FRAMEWORK_SHELL``) must name the shell by its full path; on
    Windows it must also include the file extension. Short names and relative paths are rejected
    because they could be resolved from the current directory. The Windows default (``pwsh.exe``,
    then ``powershell.exe``) and the last POSIX fallback (``sh``) are looked up only in the fully
    qualified entries of ``PATH``.

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
            parts = _split_shell_string(shell)
            if not parts:
                raise ShellExecutionError("shell override must not be empty")
        else:
            parts = list(shell)
            if not parts:
                raise ShellExecutionError("shell override must not be empty")
        parts = _qualify_shell(parts, source="shell")
        return parts if interactive else _ensure_command_flag(parts)

    env_override = os.environ.get(_ENV_OVERRIDE)
    if env_override:
        parts = _split_shell_string(env_override)
        if parts:
            parts = _qualify_shell(parts, source=_ENV_OVERRIDE)
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
    # Last-ditch fallback: look up 'sh' in the fully qualified PATH entries.
    sh = find_executable("sh")
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
