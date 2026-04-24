# Copyright (c) Microsoft. All rights reserved.

"""Policy model for :class:`LocalShellTool`.

``ShellPolicy`` is evaluated *before* approval and *before* execution. It lets
callers define allow/deny rules and a final custom callback, mirroring the
layered-defense pattern used by competitor frameworks (LangChain's
``BashProcess``, AutoGen's ``LocalCommandLineCodeExecutor``, Claude Code's
bash tool).
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


# Default denylist. Matches a conservative set of destructive commands seen in
# real-world prompt-injection corpora and competitor tool docs. The patterns
# are anchored loosely so that obviously equivalent variants (extra spaces,
# leading ``sudo``) are still rejected.
DEFAULT_DENYLIST: tuple[str, ...] = (
    # Recursive / force deletes at dangerous roots
    r"\brm\s+(?:-[a-zA-Z]*[rf][a-zA-Z]*\s+)+(?:/|~|\*)",
    r"\brmdir\s+/s",
    r"\bdel\s+/[fs]",
    # Filesystem wipes
    r"\bmkfs\b",
    r"\bdd\s+if=[^\s]+\s+of=/dev/",
    r">\s*/dev/sd[a-z]",
    r"\bformat\s+[a-zA-Z]:",
    # Power / init control
    r"\bshutdown\b",
    r"\breboot\b",
    r"\bhalt\b",
    r"\bpoweroff\b",
    r"\binit\s+[06]\b",
    # Fork bomb
    r":\(\)\s*\{\s*:\|:&\s*\}\s*;\s*:",
    # Curl / wget piped straight to a shell
    r"\b(?:curl|wget)\s+[^\n|;]*\|\s*(?:sh|bash|zsh|pwsh|powershell)\b",
    # Windows registry deletes
    r"\breg\s+delete\b",
    # Chowning / chmodding the world
    r"\bchmod\s+-R\s+777\s+/",
    r"\bchown\s+-R\s+[^\s]+\s+/",
)


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
    """

    denylist: Sequence[PatternLike] = field(default_factory=lambda: list(DEFAULT_DENYLIST))
    allowlist: Sequence[PatternLike] | None = None
    custom: Callable[[ShellRequest], ShellDecision | None] | None = None

    def __post_init__(self) -> None:
        self._denies = _compile_patterns(self.denylist)
        self._allows = _compile_patterns(self.allowlist) if self.allowlist is not None else None

    def evaluate(self, request: ShellRequest) -> ShellDecision:
        """Return an allow/deny decision for ``request``."""
        command = request.command.strip()
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
