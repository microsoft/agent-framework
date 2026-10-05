# Copyright (c) Microsoft. All rights reserved.

"""Shell command audit log for compliance and observability."""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field

__all__ = ["ShellAuditLog", "ShellCommandRecord"]


@dataclass
class ShellCommandRecord:
    """A record of a single shell command execution attempt.

    Stored in the tool's audit log for compliance and observability.
    All timestamps are UTC ISO 8601.
    """

    command: str
    """The command string as submitted."""

    policy_decision: str
    """The :class:`~agent_framework_tools.shell.ShellDecision` outcome: ``"allow"`` or ``"deny"``."""

    timestamp_utc: str = field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())
    """UTC ISO 8601 timestamp when the command was evaluated."""

    exit_code: int | None = None
    """Process exit code, set after execution. ``None`` if the command was denied or not yet run."""

    denial_reason: str = ""
    """Reason from :class:`~agent_framework_tools.shell.ShellDecision` when denied."""


class ShellAuditLog:
    """An in-memory audit log of shell command decisions and outcomes.

    Records every command evaluated by :class:`~agent_framework_tools.shell.LocalShellTool`,
    including the policy decision, execution outcome, and exit code.

    Access via ``LocalShellTool.audit_log``.

    Examples:
        .. code-block:: python

            tool = LocalShellTool()
            await tool.run("echo hello")

            for record in tool.audit_log.records:
                print(record.command, record.policy_decision, record.exit_code)
    """

    def __init__(self) -> None:
        self._records: list[ShellCommandRecord] = []

    def record(self, command: str, policy_decision: str, denial_reason: str = "") -> ShellCommandRecord:
        """Add a new record at evaluation time (before execution)."""
        rec = ShellCommandRecord(
            command=command,
            policy_decision=policy_decision,
            denial_reason=denial_reason,
        )
        self._records.append(rec)
        return rec

    @property
    def records(self) -> list[ShellCommandRecord]:
        """All recorded command attempts, in chronological order."""
        return list(self._records)

    def __len__(self) -> int:
        return len(self._records)
