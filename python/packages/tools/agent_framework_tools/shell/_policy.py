# Copyright (c) Microsoft. All rights reserved.

r"""Policy model for :class:`LocalShellTool` and :class:`DockerShellTool`.

``ShellPolicy`` is evaluated *before* approval and *before* execution. It
lets callers define allow/deny rules and an optional final custom callback.

.. warning::
   **Not a security boundary; not even a security feature.** ``ShellPolicy``
   is a UX pre-filter: it gives operators a way to surface a friendly error
   for site-specific patterns (e.g. "we don't run ``ssh`` from this agent",
   "block our prod hostname") before approval and before execution. It is
   **not** a defense against a malicious model or prompt-injected input.
   Regex matching on the command spelling cannot see what the shell will
   actually execute after expansion. Trivial bypasses include backslash
   insertion (``r''m -rf /``), variable expansion (``${RM:=rm} -rf /``),
   interpreter escape hatches (``python -c "import os; os.system('rm -rf /')"``),
   base64 / hex / printf smuggling (``eval $(printf '\\x72\\x6d -rf /')``),
   command substitution (``$(base64 -d <<<...)``), envvar splicing
   (``$(A=r B=m; echo $A$B) -rf /``), and absolute paths
   (``/usr/bin/rm`` matches ``\\brm\\b`` only when the pattern is loose).

   **No default patterns.** ``ShellPolicy()`` constructs an empty deny-list.
   The framework deliberately ships no built-in patterns so it does not
   give a false impression of safety. Survey of competing agent frameworks
   (LangChain, AutoGen, OpenAI Agents SDK, Claude Code, Goose, Continue.dev,
   OpenHands, Open Interpreter, Aider, smolagents, LangGraph) found that
   none use regex matching as a primary security control; AutoGen v2
   explicitly removed their built-in deny-list.

   The actual security boundary is **(a) approval-in-the-loop** (default
   ``approval_mode="always_require"``) and **(b) operator trust / sandbox
   tier**. For untrusted input use ``DockerShellTool`` or
   ``HyperlightCodeActProvider`` (microVM); pair either with approval gating.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Literal, Union

PatternLike = Union[str, re.Pattern[str]]


@dataclass(frozen=True)
class ShellRequest:
    """A single command awaiting a policy decision."""

    command: str
    workdir: str | None = None


@dataclass(frozen=True)
class ShellDecision:
    """Result of a policy evaluation."""

    decision: Literal["allow", "deny"]
    reason: str = ""


def _compile_patterns(patterns: Sequence[PatternLike]) -> tuple[re.Pattern[str], ...]:
    compiled: list[re.Pattern[str]] = []
    for pat in patterns:
        compiled.append(pat if isinstance(pat, re.Pattern) else re.compile(pat, re.IGNORECASE))
    return tuple(compiled)


@dataclass
class ShellPolicy:
    """Layered allow/deny policy for shell commands.

    Evaluation order (first hit wins):

    1. ``denylist`` — if any pattern matches, the command is **denied**.
    2. ``allowlist`` — if set and no pattern matches, the command is
       **denied**. When ``allowlist`` is ``None`` the allow rule is skipped.
    3. ``custom`` — user-supplied callback gets the final say and may return
       a :class:`ShellDecision` to override allow/deny outcomes.
    4. Otherwise the command is **allowed**.

    All regex patterns are compiled case-insensitively.

    Defaults are empty: ``ShellPolicy()`` allows every non-empty command.
    Supply ``denylist`` and/or ``allowlist`` explicitly to enable filtering.
    See the module docstring for why the framework does not ship default
    deny patterns.
    """

    denylist: Sequence[PatternLike] = field(default_factory=tuple)
    allowlist: Sequence[PatternLike] | None = None
    custom: Callable[[ShellRequest], ShellDecision | None] | None = None

    def __post_init__(self) -> None:
        self._denies = _compile_patterns(self.denylist)
        self._allows = _compile_patterns(self.allowlist) if self.allowlist is not None else None

    def evaluate(self, request: ShellRequest) -> ShellDecision:
        """Return an allow/deny decision for ``request``.

        Empty/whitespace-only commands are denied (there is nothing to
        run). With default settings (no denylist, no allowlist) every
        non-empty command is allowed.
        """
        command = request.command.strip()
        if not command:
            return ShellDecision("deny", "command is empty")
        for pat in self._denies:
            if pat.search(command):
                return ShellDecision("deny", f"matches denylist pattern: {pat.pattern}")
        if self._allows is not None and not any(pat.search(command) for pat in self._allows):
            return ShellDecision("deny", "command does not match allowlist")
        if self.custom is not None:
            override = self.custom(request)
            if override is not None:
                return override
        return ShellDecision("allow")

    def evaluate_command(self, command: str) -> ShellDecision:
        """Convenience: evaluate a bare command with no workdir context."""
        return self.evaluate(ShellRequest(command=command))
