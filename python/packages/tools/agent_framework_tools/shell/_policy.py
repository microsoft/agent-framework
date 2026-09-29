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

import logging
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal, Union

import regex

logger = logging.getLogger(__name__)

PatternLike = Union[str, re.Pattern[str], regex.Pattern[str]]

# Wall-clock bound on a single pattern match.
#
# Policy patterns are operator-authored, but the command they are matched against is
# model-generated and therefore attacker-influenced. An ambiguous pattern can be pushed
# into catastrophic backtracking by a crafted command, and ``evaluate`` is synchronous --
# it runs on the caller's thread with no offload -- so an unbounded match stalls the whole
# process. One second is far longer than any realistic policy match needs.
_PATTERN_MATCH_TIMEOUT_SECONDS = 1.0


class _PatternTimeout(Exception):
    """Raised when a single policy pattern match exceeds its budget."""


def _search(pattern: Any, command: str) -> bool:
    """Return whether ``pattern`` matches ``command``.

    Raises:
        _PatternTimeout: When a bounded pattern exceeds
            :data:`_PATTERN_MATCH_TIMEOUT_SECONDS`. Callers decide what a non-answer
            means for them; both call sites in :meth:`ShellPolicy.evaluate` fail closed.
    """
    if isinstance(pattern, re.Pattern):
        # An operator handed us a pre-compiled ``re`` pattern; its flags are its own and
        # ``re`` cannot be interrupted, so this one is matched unbounded.
        return pattern.search(command) is not None  # pyright: ignore[reportUnknownMemberType]
    try:
        return pattern.search(command, timeout=_PATTERN_MATCH_TIMEOUT_SECONDS) is not None
    except TimeoutError as exc:
        raise _PatternTimeout from exc


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


def _compile_patterns(patterns: Sequence[PatternLike]) -> tuple[Any, ...]:
    """Compile policy patterns, preferring the interruptible ``regex`` engine.

    A pattern given as a string is compiled with ``regex``, so the match can be bounded by
    :func:`_search`. An already-compiled pattern is kept verbatim -- re-compiling would
    silently reinterpret whichever flags the caller set. A pre-compiled :class:`regex.Pattern`
    is still bounded; a pre-compiled :class:`re.Pattern` is not, because ``re`` offers no way
    to interrupt a match.
    """
    compiled: list[Any] = []
    for pat in patterns:
        if isinstance(pat, (re.Pattern, regex.Pattern)):
            compiled.append(pat)
        else:
            # VERSION1 is selected explicitly rather than left to ``regex.DEFAULT_VERSION``,
            # which is a mutable process global: any library in the process can flip it and
            # silently change how these patterns parse.
            compiled.append(regex.compile(pat, flags=regex.IGNORECASE | regex.VERSION1))
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

    .. warning::
        Policy patterns are **developer-authored code**, not model or user input, so
        testing them is the developer's responsibility. A pattern with nested or
        ambiguous quantifiers (``(a|a)*``, ``(a+)+``) can be pushed into catastrophic
        backtracking by a crafted command, and the command *is* model-generated.

        Prefer plain ``str`` patterns: the framework compiles those on the ``regex``
        engine and bounds every match at one second, failing closed on timeout. A
        pre-compiled :class:`regex.Pattern` is bounded the same way. A pre-compiled
        :class:`re.Pattern` is honoured verbatim and is **not** bounded -- the standard
        library offers no way to interrupt a match -- so an expensive pattern supplied
        that way can stall the calling thread indefinitely.
    """

    denylist: Sequence[PatternLike] = field(default_factory=tuple)
    allowlist: Sequence[PatternLike] | None = None
    custom: Callable[[ShellRequest], ShellDecision | None] | None = None

    _denies: tuple[Any, ...] = field(init=False, repr=False, compare=False)
    _allows: tuple[Any, ...] | None = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        self._denies = _compile_patterns(self.denylist)
        self._allows = _compile_patterns(self.allowlist) if self.allowlist is not None else None

    def evaluate(self, request: ShellRequest) -> ShellDecision:
        """Return an allow/deny decision for ``request``.

        Empty/whitespace-only commands are denied (there is nothing to
        run). With default settings (no denylist, no allowlist) every
        non-empty command is allowed.

        A pattern that exceeds its match budget yields no answer, and both lists treat a
        non-answer as a denial: an unproven denylist pattern is assumed to have matched,
        and an unproven allowlist pattern is assumed not to have.
        """
        command = request.command.strip()
        if not command:
            return ShellDecision("deny", "command is empty")
        for pat in self._denies:
            try:
                hit = _search(pat, command)
            except _PatternTimeout:
                logger.warning("Denylist pattern timed out; denying command: %s", pat.pattern)
                return ShellDecision("deny", f"denylist pattern could not be evaluated in time: {pat.pattern}")
            if hit:
                return ShellDecision("deny", f"matches denylist pattern: {pat.pattern}")
        if self._allows is not None and not self._matches_allowlist(command):
            return ShellDecision("deny", "command does not match allowlist")
        if self.custom is not None:
            override = self.custom(request)
            if override is not None:
                return override
        return ShellDecision("allow")

    def _matches_allowlist(self, command: str) -> bool:
        """Return whether any allowlist pattern matches ``command``.

        A pattern that times out is skipped rather than counted as a match: the allowlist
        grants permission, so an unproven pattern must not be the thing that grants it.
        """
        assert self._allows is not None  # nosec B101 - guarded by the caller
        for pat in self._allows:
            try:
                if _search(pat, command):
                    return True
            except _PatternTimeout:
                logger.warning("Allowlist pattern timed out; not counting it as a match: %s", pat.pattern)
        return False

    def evaluate_command(self, command: str) -> ShellDecision:
        """Convenience: evaluate a bare command with no workdir context."""
        return self.evaluate(ShellRequest(command=command))
