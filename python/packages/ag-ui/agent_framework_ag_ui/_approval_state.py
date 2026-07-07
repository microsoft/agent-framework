# Copyright (c) Microsoft. All rights reserved.

"""Server-side AG-UI approval state storage."""

from __future__ import annotations

from collections import OrderedDict
from typing import Any

ApprovalScope = str
"""Application-defined scope for server-side AG-UI Approval State."""

DEFAULT_MAX_APPROVAL_STATES = 10_000
_APPROVAL_SCOPE_INPUT_KEY = "__ag_ui_approval_scope"
_APPROVAL_THREAD_SEPARATOR = "\x1f"


def approval_state_thread_id(*, scope: ApprovalScope | None, thread_id: str) -> str:
    """Return the storage thread key for Approval State."""
    if not scope:
        return thread_id
    return f"{scope}{_APPROVAL_THREAD_SEPARATOR}{thread_id}"


class InMemoryAGUIApprovalStateStore:
    """Bounded process-local server-side store for AG-UI Approval State.

    The default store keeps only pending approval entries. It does not store
    general ``AgentSession.state`` or AG-UI Thread Snapshots.
    """

    def __init__(self, *, max_entries: int = DEFAULT_MAX_APPROVAL_STATES) -> None:
        """Initialize the process-local Approval State store.

        Keyword Args:
            max_entries: Maximum pending approval entries to retain.

        Raises:
            ValueError: If ``max_entries`` is less than 1.
        """
        if max_entries < 1:
            raise ValueError("max_entries must be greater than 0.")
        self.max_entries = max_entries
        self.pending_approvals: OrderedDict[tuple[str, str], Any] = OrderedDict()
        self.tool_approval_states: OrderedDict[str, dict[str, Any]] = OrderedDict()

    def evict_oldest(self) -> None:
        """Evict oldest pending approval entries until the store is within bounds."""
        while len(self.pending_approvals) > self.max_entries:
            self.pending_approvals.popitem(last=False)
        while len(self.tool_approval_states) > self.max_entries:
            self.tool_approval_states.popitem(last=False)
