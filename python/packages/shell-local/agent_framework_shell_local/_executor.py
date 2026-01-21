# Copyright (c) Microsoft. All rights reserved.

"""Local shell executor implementation."""

import asyncio
import contextlib
import os
from typing import Any, Literal

from agent_framework import (
    DEFAULT_SHELL_MAX_OUTPUT_BYTES,
    DEFAULT_SHELL_TIMEOUT_SECONDS,
    ShellExecutor,
)


class LocalShellExecutor(ShellExecutor):
    """Local shell command executor using asyncio subprocess."""

    def __init__(
        self,
        *,
        default_encoding: str = "utf-8",
        encoding_errors: Literal["strict", "ignore", "replace", "backslashreplace", "xmlcharrefreplace"] = "replace",
    ) -> None:
        """Initialize the LocalShellExecutor.

        Keyword Args:
            default_encoding: The default encoding for decoding output.
            encoding_errors: Error handling scheme for decoding.
        """
        self._default_encoding = default_encoding
        self._encoding_errors = encoding_errors

    async def _terminate_process(self, process: asyncio.subprocess.Process) -> None:
        """Terminate process with escalation to SIGKILL on Unix."""
        if process.returncode is not None:
            return
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            process.kill()
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(process.wait(), timeout=2.0)

    def _decode_output(self, data: bytes) -> str:
        """Decode bytes to string."""
        if not data:
            return ""
        return data.decode(self._default_encoding, errors=self._encoding_errors)

    def _truncate_output(self, data: bytes, max_bytes: int) -> tuple[bytes, bool]:
        """Truncate output at valid encoding boundary."""
        if len(data) <= max_bytes:
            return data, False
        truncated = data[:max_bytes]
        # Try to find a valid boundary by removing up to 4 bytes (max UTF-8 char length)
        for i in range(min(4, len(truncated))):
            try:
                truncated[: len(truncated) - i].decode(self._default_encoding)
                return truncated[: len(truncated) - i], True
            except UnicodeDecodeError:
                continue
        return truncated, True

    async def _execute_single(
        self,
        command: str,
        *,
        working_directory: str | None = None,
        timeout_seconds: int = DEFAULT_SHELL_TIMEOUT_SECONDS,
        max_output_bytes: int = DEFAULT_SHELL_MAX_OUTPUT_BYTES,
        capture_stderr: bool = True,
    ) -> dict[str, Any]:
        """Execute a single shell command locally."""
        if working_directory is not None and not await asyncio.to_thread(os.path.isdir, working_directory):
            return {
                "stdout": "",
                "stderr": f"Working directory does not exist: {working_directory}",
                "exit_code": -1,
                "timed_out": False,
                "truncated": False,
            }

        stderr_setting = asyncio.subprocess.PIPE if capture_stderr else asyncio.subprocess.DEVNULL

        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=stderr_setting,
                cwd=working_directory,
            )
        except OSError as e:
            return {
                "stdout": "",
                "stderr": f"Failed to start process: {e}",
                "exit_code": -1,
                "timed_out": False,
                "truncated": False,
            }

        timed_out = False
        stdout_bytes = b""
        stderr_bytes = b""

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(process.communicate(), timeout=timeout_seconds)
        except asyncio.TimeoutError:
            await self._terminate_process(process)
            timed_out = True

        truncated = False
        if stdout_bytes and len(stdout_bytes) > max_output_bytes:
            stdout_bytes, truncated = self._truncate_output(stdout_bytes, max_output_bytes)
        if stderr_bytes and len(stderr_bytes) > max_output_bytes:
            stderr_bytes, stderr_truncated = self._truncate_output(stderr_bytes, max_output_bytes)
            truncated = truncated or stderr_truncated

        return {
            "stdout": self._decode_output(stdout_bytes),
            "stderr": self._decode_output(stderr_bytes) if capture_stderr else "",
            "exit_code": None if timed_out else (process.returncode if process.returncode is not None else -1),
            "timed_out": timed_out,
            "truncated": truncated,
        }

    async def execute(
        self,
        commands: list[str],
        *,
        working_directory: str | None = None,
        timeout_seconds: int = DEFAULT_SHELL_TIMEOUT_SECONDS,
        max_output_bytes: int = DEFAULT_SHELL_MAX_OUTPUT_BYTES,
        capture_stderr: bool = True,
    ) -> list[dict[str, Any]]:
        """Execute shell commands locally.

        Args:
            commands: List of commands to execute.

        Keyword Args:
            working_directory: Working directory for the commands.
            timeout_seconds: Timeout in seconds per command.
            max_output_bytes: Maximum output size in bytes per command.
            capture_stderr: Whether to capture stderr.

        Returns:
            List of output dictionaries containing the command output.
        """
        outputs: list[dict[str, Any]] = []
        for command in commands:
            result = await self._execute_single(
                command,
                working_directory=working_directory,
                timeout_seconds=timeout_seconds,
                max_output_bytes=max_output_bytes,
                capture_stderr=capture_stderr,
            )
            outputs.append(result)

        return outputs
