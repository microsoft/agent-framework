# Copyright (c) Microsoft. All rights reserved.

"""Shared types for the local shell tool."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from agent_framework import Content

ShellMode = Literal["persistent", "stateless"]


@dataclass(frozen=True)
class ShellResult:
    """The outcome of a single shell command invocation.

    Attributes:
        stdout: Captured standard output, possibly truncated.
        stderr: Captured standard error, possibly truncated.
        exit_code: The exit status reported by the shell or subprocess.
        duration_ms: How long the command took, in milliseconds.
        truncated: ``True`` when stdout or stderr was truncated to fit
            ``max_output_bytes``.
        timed_out: ``True`` when the command was killed because it exceeded
            the configured timeout.
    """

    stdout: str
    stderr: str
    exit_code: int
    duration_ms: int
    truncated: bool = False
    timed_out: bool = False

    def format_for_model(self) -> str:
        """Format the result as a single text block suitable for an LLM."""
        parts: list[str] = []
        if self.stdout:
            parts.append(self.stdout)
        if self.stderr:
            parts.append(f"stderr: {self.stderr}")
        if self.truncated:
            parts.append("[output truncated]")
        if self.timed_out:
            parts.append("[command timed out]")
        parts.append(f"exit_code: {self.exit_code}")
        return "\n".join(parts)


class _ShellResultText(str):
    """Model-facing shell text that retains its structured source for normal parsing."""

    shell_result: ShellResult

    def __new__(cls, result: ShellResult) -> _ShellResultText:
        value = super().__new__(cls, result.format_for_model())
        value.shell_result = result
        return value


def _shell_result_to_text(result: ShellResult) -> str:  # pyright: ignore[reportUnusedFunction]
    return _ShellResultText(result)


def _parse_shell_result(result: Any) -> str | list[Content]:  # pyright: ignore[reportUnusedFunction]
    """Preserve structured shell fields alongside the model-facing text."""
    if not isinstance(result, _ShellResultText):
        return str(result)
    shell_result = result.shell_result
    return [
        Content.from_text(
            result,
            additional_properties={
                "stdout": shell_result.stdout,
                "stderr": shell_result.stderr,
                "exit_code": shell_result.exit_code,
                "truncated": shell_result.truncated,
                "timed_out": shell_result.timed_out,
            },
        )
    ]


class ShellExecutionError(RuntimeError):
    """Base class for shell-tool execution failures."""


class ShellTimeoutError(ShellExecutionError):
    """Raised when a command exceeds the configured timeout."""


class ShellCommandError(ShellExecutionError):
    """Raised when a command is rejected by the configured policy."""
