# Copyright (c) Microsoft. All rights reserved.

"""Persistent shell session.

A :class:`ShellSession` launches a long-lived shell subprocess and executes
commands one at a time by writing them to stdin followed by a **sentinel
probe** that reports the exit status. Reading stdout until the sentinel
appears gives us a reliable command boundary without relying on job control
or PTYs — which matters for cross-OS support (bash, sh, pwsh).

Design inspiration:
- Anthropic ``bash_20250124``: persistent session semantics.
- Claude Code Bash tool: sentinel-based boundary.
- LangChain ``BashProcess`` (experimental): pexpect persistent mode.

Implementation notes (hard-won):

* ``pwsh -NoProfile -NoLogo -NonInteractive -Command -`` waits for a complete
  parse before executing. Multi-line ``try`` blocks therefore stall with
  stdin open. We sidestep that by base64-encoding the user command and
  invoking it with ``Invoke-Expression`` on a single line.
* ``Write-Output`` routes through the PowerShell pipeline formatter which
  may drop trailing newlines when stdout is redirected. The sentinel is
  emitted via ``[Console]::WriteLine`` + explicit ``[Console]::Out.Flush()``.
* ``$LASTEXITCODE`` only tracks external-process exits. We derive the rc in
  PowerShell from ``$?`` and caught exceptions as well.
* stdout and stderr are consumed by **persistent reader tasks** that run for
  the lifetime of the session. Each ``run()`` calculates buffer offsets
  before writing the command and scans forward from there. This avoids the
  ``read() called while another coroutine is already waiting`` errors that
  arise from per-call ``wait_for(stream.read())`` loops, and prevents late
  stderr from being attributed to the next command.
"""

from __future__ import annotations

import asyncio
import base64
import os
import secrets
import signal
import sys
import time
from collections.abc import Mapping, Sequence

from ._killtree import kill_process_tree
from ._resolve import is_powershell
from ._types import ShellResult

_READ_CHUNK = 64 * 1024
_SHUTDOWN_GRACE = 2.0
# Extra grace window after the sentinel arrives to let late stderr drain.
_STDERR_QUIESCENCE = 0.05


class ShellSession:
    """A long-lived shell subprocess that executes commands via sentinels.

    The session is thread-unsafe by design but async-safe: concurrent calls
    to :meth:`run` are serialised with an internal :class:`asyncio.Lock`.
    """

    def __init__(
        self,
        argv: Sequence[str],
        *,
        workdir: str | None = None,
        env: Mapping[str, str] | None = None,
        max_output_bytes: int = 64 * 1024,
    ) -> None:
        self._argv = list(argv)
        self._workdir = workdir
        self._env = dict(env) if env is not None else None
        self._max_output_bytes = max_output_bytes
        self._proc: asyncio.subprocess.Process | None = None
        # Serialises per-command execution.
        self._run_lock = asyncio.Lock()
        # Serialises start/close so concurrent first-callers don't spawn
        # multiple subprocesses.
        self._lifecycle_lock = asyncio.Lock()
        self._sentinel_tag = secrets.token_hex(8)
        self._is_pwsh = is_powershell(argv)

        # Persistent reader state. The reader tasks append into these
        # buffers; _run_locked scans forward from a per-call offset.
        self._stdout_buf = bytearray()
        self._stderr_buf = bytearray()
        self._stdout_event = asyncio.Event()
        self._stdout_reader: asyncio.Task[None] | None = None
        self._stderr_reader: asyncio.Task[None] | None = None
        self._stdout_closed = False

    # ------------------------------------------------------------------ lifecycle

    async def start(self) -> None:
        """Spawn the shell if it isn't already running."""
        async with self._lifecycle_lock:
            if self._proc is not None and self._proc.returncode is None:
                return
            popen_kwargs: dict[str, object] = {}
            if sys.platform == "win32":
                import subprocess  # noqa: S404

                popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
            else:
                popen_kwargs["start_new_session"] = True

            self._proc = await asyncio.create_subprocess_exec(
                *self._argv,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self._workdir,
                env=self._env,
                **popen_kwargs,  # type: ignore[arg-type]
            )

            # Reset buffer state in case this is a restart after close().
            self._stdout_buf.clear()
            self._stderr_buf.clear()
            self._stdout_event = asyncio.Event()
            self._stdout_closed = False

            assert self._proc.stdout is not None and self._proc.stderr is not None
            self._stdout_reader = asyncio.create_task(
                self._reader(self._proc.stdout, self._stdout_buf, is_stdout=True)
            )
            self._stderr_reader = asyncio.create_task(
                self._reader(self._proc.stderr, self._stderr_buf, is_stdout=False)
            )

            # Best-effort: make PowerShell emit UTF-8 and fail loudly on errors.
            if self._is_pwsh:
                await self._write_raw(
                    "$OutputEncoding = [Console]::OutputEncoding = "
                    "[System.Text.UTF8Encoding]::new($false);"
                    "$ErrorActionPreference = 'Stop'\n"
                )

    async def close(self) -> None:
        """Terminate the shell cleanly, falling back to SIGKILL."""
        async with self._lifecycle_lock:
            proc = self._proc
            self._proc = None
            if proc is None or proc.returncode is not None:
                await self._cancel_readers()
                return
            try:
                if proc.stdin is not None and not proc.stdin.is_closing():
                    try:
                        proc.stdin.write(b"exit\n")
                        await proc.stdin.drain()
                        proc.stdin.close()
                    except (ConnectionResetError, BrokenPipeError):
                        pass
                try:
                    await asyncio.wait_for(proc.wait(), timeout=_SHUTDOWN_GRACE)
                except asyncio.TimeoutError:
                    await kill_process_tree(proc, grace=_SHUTDOWN_GRACE)
            except Exception:
                pass
            finally:
                await self._cancel_readers()

    async def _cancel_readers(self) -> None:
        for t in (self._stdout_reader, self._stderr_reader):
            if t is not None and not t.done():
                t.cancel()
                try:
                    await t
                except (asyncio.CancelledError, Exception):
                    pass
        self._stdout_reader = None
        self._stderr_reader = None

    async def __aenter__(self) -> "ShellSession":
        await self.start()
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.close()

    # ------------------------------------------------------------------ execution

    async def run(
        self,
        command: str,
        *,
        timeout: float | None,
    ) -> ShellResult:
        """Run ``command`` in the live session and return its result."""
        await self.start()
        async with self._run_lock:
            return await self._run_locked(command, timeout=timeout)

    async def _run_locked(self, command: str, *, timeout: float | None) -> ShellResult:
        assert self._proc is not None and self._proc.stdin is not None

        sentinel = f"__AF_END_{self._sentinel_tag}_{secrets.token_hex(4)}__"
        script = self._build_script(command, sentinel)
        # Snapshot current buffer positions so we only attribute output
        # produced *after* the command is submitted.
        stdout_offset = len(self._stdout_buf)
        stderr_offset = len(self._stderr_buf)
        self._stdout_event.clear()

        started = time.monotonic()
        try:
            self._proc.stdin.write(script.encode("utf-8"))
            await self._proc.stdin.drain()
        except (ConnectionResetError, BrokenPipeError) as exc:
            raise RuntimeError("persistent shell session is no longer alive") from exc

        needle = sentinel.encode("utf-8")
        timed_out = False
        hard_cap = self._max_output_bytes * 4

        async def _wait_for_sentinel() -> tuple[int, int]:
            """Return (sentinel_start_index, exit_code) once seen."""
            while True:
                idx = self._stdout_buf.find(needle, stdout_offset)
                if idx != -1:
                    # Parse trailing ``_<digits>``.
                    tail_start = idx + len(needle)
                    # Wait briefly for the rc digits + newline to arrive.
                    deadline = time.monotonic() + 1.0
                    while time.monotonic() < deadline:
                        after = bytes(self._stdout_buf[tail_start:])
                        nl = after.find(b"\n")
                        if nl != -1:
                            break
                        if self._stdout_closed:
                            break
                        self._stdout_event.clear()
                        try:
                            await asyncio.wait_for(
                                self._stdout_event.wait(), timeout=0.1
                            )
                        except asyncio.TimeoutError:
                            pass
                    after = bytes(self._stdout_buf[tail_start:])
                    rc = _parse_rc(after)
                    return idx, rc
                if self._stdout_closed:
                    raise RuntimeError(
                        "shell closed stdout before emitting sentinel"
                    )
                if len(self._stdout_buf) - stdout_offset > hard_cap:
                    raise _SentinelOverflow
                self._stdout_event.clear()
                try:
                    await asyncio.wait_for(self._stdout_event.wait(), timeout=0.5)
                except asyncio.TimeoutError:
                    # Keep spinning; timeout is enforced at the wait_for below.
                    pass

        sentinel_idx: int
        exit_code: int
        try:
            sentinel_idx, exit_code = await asyncio.wait_for(
                _wait_for_sentinel(), timeout=timeout
            )
        except asyncio.TimeoutError:
            timed_out = True
            await self._interrupt_current_command()
            try:
                sentinel_idx, exit_code = await asyncio.wait_for(
                    _wait_for_sentinel(), timeout=_SHUTDOWN_GRACE
                )
            except (asyncio.TimeoutError, RuntimeError, _SentinelOverflow):
                # Session is unrecoverable; tear it down so the next call
                # gets a fresh subprocess.
                await self.close()
                duration_ms = int((time.monotonic() - started) * 1000)
                stdout_text = bytes(
                    self._stdout_buf[stdout_offset:]
                ).decode("utf-8", errors="replace")
                stderr_text = bytes(
                    self._stderr_buf[stderr_offset:]
                ).decode("utf-8", errors="replace")
                stdout_str, so_trunc = _truncate(stdout_text, self._max_output_bytes)
                stderr_str, se_trunc = _truncate(stderr_text, self._max_output_bytes)
                return ShellResult(
                    stdout=stdout_str,
                    stderr=stderr_str,
                    exit_code=124,
                    duration_ms=duration_ms,
                    truncated=so_trunc or se_trunc,
                    timed_out=True,
                )
        except _SentinelOverflow:
            # Runaway output; recover by interrupting and restarting.
            await self._interrupt_current_command()
            await self.close()
            duration_ms = int((time.monotonic() - started) * 1000)
            stdout_text = bytes(
                self._stdout_buf[stdout_offset : stdout_offset + hard_cap]
            ).decode("utf-8", errors="replace")
            stderr_text = bytes(self._stderr_buf[stderr_offset:]).decode(
                "utf-8", errors="replace"
            )
            stdout_str, _ = _truncate(stdout_text, self._max_output_bytes)
            stderr_str, _ = _truncate(stderr_text, self._max_output_bytes)
            return ShellResult(
                stdout=stdout_str,
                stderr=stderr_str,
                exit_code=-1,
                duration_ms=duration_ms,
                truncated=True,
                timed_out=False,
            )

        # Let stderr quiesce briefly — late writes from the completing
        # command otherwise leak into the *next* run().
        await asyncio.sleep(_STDERR_QUIESCENCE)

        duration_ms = int((time.monotonic() - started) * 1000)
        stdout_raw = bytes(self._stdout_buf[stdout_offset:sentinel_idx])
        stderr_raw = bytes(self._stderr_buf[stderr_offset:])

        stdout_text = stdout_raw.decode("utf-8", errors="replace").rstrip("\r\n")
        stderr_text = stderr_raw.decode("utf-8", errors="replace")

        stdout_str, stdout_truncated = _truncate(stdout_text, self._max_output_bytes)
        stderr_str, stderr_truncated = _truncate(stderr_text, self._max_output_bytes)

        return ShellResult(
            stdout=stdout_str,
            stderr=stderr_str,
            exit_code=exit_code,
            duration_ms=duration_ms,
            truncated=stdout_truncated or stderr_truncated,
            timed_out=timed_out,
        )

    # ------------------------------------------------------------------ helpers

    def _build_script(self, command: str, sentinel: str) -> str:
        if self._is_pwsh:
            # See module docstring for why we base64-encode and use
            # Invoke-Expression. $ErrorActionPreference is set to 'Stop' at
            # session start, so the catch block fires on cmdlet errors as
            # well as parse failures surfaced by Invoke-Expression itself.
            encoded = base64.b64encode(command.encode("utf-8")).decode("ascii")
            return (
                "& {"
                " $__af_rc = 0;"
                " try {"
                f"   $__af_cmd = [System.Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{encoded}'));"
                "   Invoke-Expression $__af_cmd;"
                "   if ($LASTEXITCODE -ne $null) { $__af_rc = $LASTEXITCODE }"
                "   elseif (-not $?) { $__af_rc = 1 }"
                " } catch {"
                "   [Console]::Error.WriteLine($_.ToString());"
                "   $__af_rc = 1"
                " } finally {"
                f"   [Console]::WriteLine('{sentinel}_' + $__af_rc);"
                "   [Console]::Out.Flush()"
                " }"
                " }\n"
            )
        # POSIX shell. Run the user command in a group so we can capture
        # its exit status, then print the sentinel on a line of its own.
        # We briefly disable ``errexit`` around our trailer so a prior
        # ``set -e`` in the user command can't skip the sentinel print.
        return (
            "{ "
            f"{command}\n"
            "}; __af_rc=$?; set +e; "
            f"printf '\\n{sentinel}_%s\\n' \"$__af_rc\"\n"
        )

    async def _write_raw(self, text: str) -> None:
        if self._proc is None or self._proc.stdin is None:
            return
        self._proc.stdin.write(text.encode("utf-8"))
        await self._proc.stdin.drain()

    async def _reader(
        self,
        stream: asyncio.StreamReader,
        buf: bytearray,
        *,
        is_stdout: bool,
    ) -> None:
        """Persistent reader task: drains ``stream`` into ``buf`` until EOF."""
        try:
            while True:
                chunk = await stream.read(_READ_CHUNK)
                if not chunk:
                    if is_stdout:
                        self._stdout_closed = True
                        self._stdout_event.set()
                    return
                buf.extend(chunk)
                if is_stdout:
                    self._stdout_event.set()
        except asyncio.CancelledError:
            raise
        except Exception:
            if is_stdout:
                self._stdout_closed = True
                self._stdout_event.set()

    async def _interrupt_current_command(self) -> None:
        if self._proc is None or self._proc.returncode is not None:
            return
        try:
            if sys.platform == "win32":
                self._proc.send_signal(signal.CTRL_BREAK_EVENT)  # type: ignore[attr-defined]
            else:
                os.killpg(os.getpgid(self._proc.pid), signal.SIGINT)
        except (ProcessLookupError, PermissionError, OSError):
            pass


async def _kill_tree(proc: asyncio.subprocess.Process) -> None:
    """Deprecated: use :func:`kill_process_tree` from ``_killtree``."""
    await kill_process_tree(proc, grace=_SHUTDOWN_GRACE)


def _parse_rc(after: bytes) -> int:
    """Parse ``_<digits>`` trailing the sentinel. Returns -1 on failure."""
    if not after.startswith(b"_"):
        return -1
    digits = bytearray()
    for b in after[1:]:
        if b == ord("\n") or b == ord("\r"):
            break
        if 48 <= b <= 57 or b == ord("-"):
            digits.append(b)
        else:
            break
    if not digits:
        return -1
    try:
        return int(digits.decode("ascii"))
    except ValueError:
        return -1


def _truncate(data: str, cap: int) -> tuple[str, bool]:
    if len(data) <= cap:
        return data, False
    head = data[: cap // 2]
    tail = data[-cap // 2 :]
    return f"{head}\n[... truncated {len(data) - cap} chars ...]\n{tail}", True


class _SentinelOverflow(RuntimeError):
    """Internal signal that the sentinel was never seen within the soft cap."""
