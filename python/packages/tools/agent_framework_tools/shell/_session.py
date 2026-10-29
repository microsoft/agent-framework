# Copyright (c) Microsoft. All rights reserved.

"""Persistent shell session.

A :class:`ShellSession` launches a long-lived shell subprocess and executes
commands one at a time by writing them to stdin followed by a **sentinel
probe** that reports the exit status. Reading stdout until the sentinel
appears gives a reliable command boundary without relying on job control
or PTYs, which keeps the same code path working on bash, sh, and pwsh.

**Single-owner contract.** A :class:`ShellSession` is owned by exactly one
conversation / agent session — i.e. one user. The backing shell process
carries mutable state (cwd, exported variables, history, background jobs)
that every subsequent command can observe, and the internal
``asyncio.Lock`` serializes every call onto the single stdin/stdout pipe.
There is no per-caller isolation. The enclosing shell tool must not share
a single session across users, tenants, or concurrent conversations; it
must create one session per agent session and close it when the session
ends.

Notes:
* ``pwsh -NoProfile -NoLogo -NonInteractive -Command -`` waits for a
  complete parse before executing, so multi-line ``try`` blocks stall
  with stdin open. To avoid that, the user command is base64-encoded
  and invoked with ``Invoke-Expression`` on a single line.
* ``Write-Output`` routes through the PowerShell pipeline formatter,
  which may drop trailing newlines when stdout is redirected. The
  sentinel is emitted via ``[Console]::WriteLine`` followed by an
  explicit ``[Console]::Out.Flush()``.
* ``$LASTEXITCODE`` only tracks external-process exits, so the rc is
  also derived from ``$?`` and caught exceptions.
* stdout and stderr are consumed by **persistent reader tasks** that
  run for the lifetime of the session. Each ``run()`` installs bounded
  output capture and a separate incremental completion-marker parser.
  This avoids ``read() called while another coroutine is already
  waiting`` errors from per-call ``wait_for(stream.read())`` loops and
  prevents late stderr from being attributed to the next command.
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

from ._capture import READ_CHUNK
from ._killtree import kill_process_tree
from ._resolve import is_powershell
from ._truncate import (
    _TextOutputBuffer,  # pyright: ignore[reportPrivateUsage] - shared shell capture
    _validate_output_limit,  # pyright: ignore[reportPrivateUsage] - shared limit validation
)
from ._types import ShellResult

_SHUTDOWN_GRACE = 2.0
# Extra grace window after the sentinel arrives to let late stderr drain.
_STDERR_QUIESCENCE = 0.05


class _CommandOutput:
    """Separate bounded command output from completion-marker recognition."""

    def __init__(self, sentinel: bytes, *, max_stdout_bytes: int, max_stderr_bytes: int) -> None:
        self.stdout = _TextOutputBuffer(max_stdout_bytes, strip_newlines=True)
        self.stderr = _TextOutputBuffer(max_stderr_bytes)
        self.stdout_bytes = 0
        self.exit_code: int | None = None
        self.marker_seen_at: float | None = None
        self._sentinel = sentinel
        self._pending = bytearray()

    def read_stdout(self, chunk: bytes) -> None:
        if self.exit_code is not None:
            return
        self._pending.extend(chunk)
        if self.marker_seen_at is None:
            idx = self._pending.find(self._sentinel)
            if idx == -1:
                keep = min(len(self._pending), len(self._sentinel) - 1)
                while keep and not self._pending.endswith(self._sentinel[:keep]):
                    keep -= 1
                emit = len(self._pending) - keep
                self.stdout_bytes += emit
                self.stdout.append(bytes(self._pending[:emit]))
                del self._pending[:emit]
                return
            self.stdout_bytes += idx
            self.stdout.append(bytes(self._pending[:idx]), final=True)
            del self._pending[: idx + len(self._sentinel)]
            self.marker_seen_at = time.monotonic()
        newline = self._pending.find(b"\n")
        # A shell exit status fits comfortably in 32 bytes. Never retain an
        # arbitrary suffix while waiting for the marker's newline.
        if (newline if newline != -1 else len(self._pending)) > 32:
            raise RuntimeError("shell completion marker has an oversized exit status")
        if newline != -1:
            self.exit_code = _parse_rc(bytes(self._pending[:newline]))
            self._pending.clear()

    def finish_stdout(self) -> None:
        if self.exit_code is not None:
            return
        if self.marker_seen_at is not None:
            self.exit_code = _parse_rc(bytes(self._pending))
        else:
            self.stdout.append(bytes(self._pending), final=True)
        self._pending.clear()


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
        max_stdout_bytes: int = 64 * 1024,
        max_stderr_bytes: int = 64 * 1024,
    ) -> None:
        _validate_output_limit(max_stdout_bytes, name="max_stdout_bytes")
        _validate_output_limit(max_stderr_bytes, name="max_stderr_bytes")
        self._argv = list(argv)
        self._workdir = workdir
        self._env = dict(env) if env is not None else None
        self._max_stdout_bytes = max_stdout_bytes
        self._max_stderr_bytes = max_stderr_bytes
        self._proc: asyncio.subprocess.Process | None = None
        # Serialises per-command execution onto the single stdin/stdout
        # pipe. This is an ordering primitive within one owning session;
        # it is NOT a multi-tenant isolation mechanism. ShellSession is
        # single-owner — see the module docstring. The lock just
        # guarantees concurrent calls from the one owner queue cleanly
        # instead of interleaving on the pipe.
        self._run_lock = asyncio.Lock()
        # Serialises start/close so concurrent first-callers don't spawn
        # multiple subprocesses.
        self._lifecycle_lock = asyncio.Lock()
        self._close_generation = 0
        self._sentinel_tag = secrets.token_hex(8)
        self._is_pwsh = is_powershell(argv)

        self._output: _CommandOutput | None = None
        self._reader_error: Exception | None = None
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
            # A dead shell can leave inherited pipes open in a child. Stop its
            # readers before reusing the buffers/events for a new process.
            await self._cancel_readers()
            popen_kwargs: dict[str, object] = {}
            if sys.platform == "win32":
                import subprocess  # ruff:ignore[suspicious-subprocess-import]  # nosec B404 - Win32 constants only

                popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
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

            self._output = None
            self._reader_error = None
            self._stdout_event = asyncio.Event()
            self._stdout_closed = False

            if self._proc.stdout is None or self._proc.stderr is None:
                raise RuntimeError("subprocess pipes were not created; stdout/stderr unavailable")
            self._stdout_reader = asyncio.create_task(self._reader(self._proc.stdout, is_stdout=True))
            self._stderr_reader = asyncio.create_task(self._reader(self._proc.stderr, is_stdout=False))

            # Best-effort: make PowerShell emit UTF-8 and fail loudly on errors.
            if self._is_pwsh:
                await self._write_raw(
                    "$OutputEncoding = [Console]::OutputEncoding = "
                    "[System.Text.UTF8Encoding]::new($false);"
                    "$ErrorActionPreference = 'Stop'\n"
                )

    async def close(self) -> None:
        """Terminate the shell cleanly, falling back to SIGKILL."""
        # Invalidate calls queued before or during explicit shutdown.
        self._close_generation += 1
        try:
            await self._close_process()
        finally:
            self._close_generation += 1

    async def _close_process(self) -> None:
        """Stop the process without invalidating commands queued for recovery."""
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
            except Exception:  # nosec B110 - best-effort shutdown; falls through to forced kill in finally
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

    async def __aenter__(self) -> ShellSession:
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
        close_generation = self._close_generation
        async with self._run_lock:
            if close_generation != self._close_generation:
                raise RuntimeError("ShellSession is not running; call start() first")
            await self.start()
            if close_generation != self._close_generation:
                await self._close_process()
                raise RuntimeError("ShellSession is not running; call start() first")
            return await self._run_locked(command, timeout=timeout)

    async def _run_locked(self, command: str, *, timeout: float | None) -> ShellResult:
        if self._proc is None or self._proc.stdin is None:
            raise RuntimeError("ShellSession is not running; call start() first")

        sentinel = f"__AF_END_{self._sentinel_tag}_{secrets.token_hex(4)}__"
        script = self._build_script(command, sentinel)
        output = _CommandOutput(
            sentinel.encode("utf-8"),
            max_stdout_bytes=self._max_stdout_bytes,
            max_stderr_bytes=self._max_stderr_bytes,
        )
        self._output = output
        self._stdout_event.clear()

        started = time.monotonic()
        timed_out = False
        overflow = False
        hard_cap = self._max_stdout_bytes * 4

        async def _wait_for_sentinel() -> int:
            while True:
                if self._reader_error is not None:
                    raise RuntimeError("failed to read persistent shell output") from self._reader_error
                if output.exit_code is not None:
                    return output.exit_code
                if output.marker_seen_at is not None:
                    if self._stdout_closed or time.monotonic() - output.marker_seen_at >= 1.0:
                        output.finish_stdout()
                        return output.exit_code if output.exit_code is not None else -1
                else:
                    if self._stdout_closed:
                        raise RuntimeError("shell closed stdout before emitting sentinel")
                    if output.stdout_bytes > hard_cap:
                        raise _SentinelOverflow
                self._stdout_event.clear()
                try:
                    await asyncio.wait_for(self._stdout_event.wait(), timeout=0.1)
                except asyncio.TimeoutError:
                    pass

        exit_code: int
        try:
            try:
                self._proc.stdin.write(script.encode("utf-8"))
                await self._proc.stdin.drain()
            except (ConnectionResetError, BrokenPipeError) as exc:
                raise RuntimeError("persistent shell session is no longer alive") from exc
            try:
                exit_code = await asyncio.wait_for(_wait_for_sentinel(), timeout=timeout)
            except asyncio.TimeoutError:
                timed_out = True
                await self._interrupt_current_command()
                try:
                    exit_code = await asyncio.wait_for(_wait_for_sentinel(), timeout=_SHUTDOWN_GRACE)
                except (asyncio.TimeoutError, RuntimeError, _SentinelOverflow):
                    await self._close_process()
                    exit_code = 124
                if sys.platform == "win32":
                    await self._close_process()
            except _SentinelOverflow:
                overflow = True
                await self._interrupt_current_command()
                await self._close_process()
                exit_code = -1

            await asyncio.sleep(_STDERR_QUIESCENCE)
            if self._reader_error is not None:
                raise RuntimeError("failed to read persistent shell output") from self._reader_error
            output.finish_stdout()
            output.stderr.append(b"", final=True)
            stdout_str, stdout_truncated = output.stdout.format()
            stderr_str, stderr_truncated = output.stderr.format()
            return ShellResult(
                stdout=stdout_str,
                stderr=stderr_str,
                exit_code=exit_code,
                duration_ms=int((time.monotonic() - started) * 1000),
                truncated=overflow or stdout_truncated or stderr_truncated,
                timed_out=timed_out,
            )
        except BaseException:
            await self._close_process()
            raise
        finally:
            self._output = None

    # ------------------------------------------------------------------ helpers

    def _build_script(self, command: str, sentinel: str) -> str:
        if self._is_pwsh:
            # Base64-encode the command and run it via Invoke-Expression to
            # work around pwsh's whole-script parse requirement on stdin.
            # $ErrorActionPreference is set to 'Stop' at session start so
            # the catch block fires on cmdlet errors as well as parse
            # failures surfaced by Invoke-Expression itself.
            encoded = base64.b64encode(command.encode("utf-8")).decode("ascii")
            return (
                "& {"
                " $__af_rc = 0;"
                # $LASTEXITCODE is a session-wide automatic variable that only
                # native (external) processes update, so a value left by an
                # earlier command is still there when a cmdlet-only command
                # runs. Snapshot it instead of clearing it: the variable stays
                # readable by the user's own commands, which persistent mode is
                # meant to preserve, and a value that differs afterwards can
                # only have been written by this command.
                " $__af_last = $LASTEXITCODE;"
                " try {"
                f"   $__af_cmd = [System.Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{encoded}'));"
                # Format the output inside the try. Left to the host, pwsh
                # formats a script block's output only after the block has
                # returned, so the sentinel written in finally would overtake
                # anything rendered as a table or list (Get-Location,
                # Select-Object, custom objects) and that output would be lost.
                "   Invoke-Expression $__af_cmd | Out-Default;"
                # $? has to be read on the very next statement: anything else
                # in between overwrites it.
                "   $__af_ok = $?;"
                "   if ($LASTEXITCODE -ne $__af_last) { $__af_rc = $LASTEXITCODE }"
                "   elseif (-not $__af_ok) { $__af_rc = 1 }"
                " } catch {"
                "   [Console]::Error.WriteLine($_.ToString());"
                "   $__af_rc = 1"
                " } finally {"
                f"   [Console]::WriteLine('{sentinel}_' + $__af_rc);"
                "   [Console]::Out.Flush()"
                " }"
                " }\n"
            )
        # POSIX shell. Run the user command in a brace-group so its exit
        # status is captured even if the user previously enabled ``set -e``
        # — we save and restore the prior errexit state around the trailer
        # so ``set -e`` (and other shell options) persist across commands
        # exactly as the user configured them.
        return (
            f"__af_e=$-; set +e; {{ {command}\n}}; __af_rc=$?;"
            f' case "$__af_e" in *e*) set -e;; esac;'
            f" printf '\\n{sentinel}_%s\\n' \"$__af_rc\"\n"
        )

    async def _write_raw(self, text: str) -> None:
        if self._proc is None or self._proc.stdin is None:
            return
        self._proc.stdin.write(text.encode("utf-8"))
        await self._proc.stdin.drain()

    async def _reader(
        self,
        stream: asyncio.StreamReader,
        *,
        is_stdout: bool,
    ) -> None:
        """Drain continuously, discarding output when no command owns it."""
        try:
            while True:
                chunk = await stream.read(READ_CHUNK)
                if not chunk:
                    if is_stdout:
                        self._stdout_closed = True
                        self._stdout_event.set()
                    return
                if self._output is not None:
                    if is_stdout:
                        self._output.read_stdout(chunk)
                    else:
                        self._output.stderr.append(chunk)
                if is_stdout:
                    self._stdout_event.set()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._reader_error = exc
            self._stdout_event.set()

    async def _interrupt_current_command(self) -> None:
        if self._proc is None or self._proc.returncode is not None:
            return
        try:
            if sys.platform == "win32":
                self._proc.send_signal(signal.CTRL_BREAK_EVENT)
            else:
                os.killpg(os.getpgid(self._proc.pid), signal.SIGINT)
        except (ProcessLookupError, PermissionError, OSError):
            pass


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


class _SentinelOverflow(RuntimeError):
    """Internal signal that the sentinel was never seen within the soft cap."""
