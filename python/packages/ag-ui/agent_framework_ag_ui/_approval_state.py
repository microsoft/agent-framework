# Copyright (c) Microsoft. All rights reserved.

"""Server-side AG-UI approval state storage."""

from __future__ import annotations

import copy
from threading import RLock
from typing import Any

from ._approval_lifecycle import ApprovalCapacityError, ApprovalExecutionOwner, ApprovalLifecycle

ApprovalScope = str
"""Application-defined scope for server-side AG-UI Approval State."""

DEFAULT_MAX_APPROVAL_STATES = 10_000
DEFAULT_PENDING_RETENTION_SECONDS = 86_400
DEFAULT_INDETERMINATE_RETENTION_SECONDS = 604_800
DEFAULT_TERMINAL_RETENTION_SECONDS = 900
_APPROVAL_SCOPE_INPUT_KEY = "__ag_ui_approval_scope"
_APPROVAL_THREAD_SEPARATOR = "\x1f"


def approval_state_thread_id(*, scope: object | None, thread_id: str) -> str:
    """Return the storage thread key for Approval State.

    ``None`` is the only unscoped value. A provided scope must be a non-empty
    string so accidental empty or malformed scopes cannot collapse into the
    unscoped namespace.
    """
    if scope is None:
        return thread_id
    if not isinstance(scope, str) or not scope:
        raise ValueError("scope must be a non-empty string when provided.")
    return f"{scope}{_APPROVAL_THREAD_SEPARATOR}{thread_id}"


class InMemoryAGUIApprovalStateStore:
    """Bounded process-local server-side store for AG-UI Approval State.

    State is local to one process and is not durable across restarts or replicas.
    Active and indeterminate occurrences are protected from eviction. Terminal
    outcomes guarantee duplicate-execution protection for the configured
    retention interval.
    """

    def __init__(
        self,
        *,
        max_entries: int = DEFAULT_MAX_APPROVAL_STATES,
        pending_retention_seconds: float = DEFAULT_PENDING_RETENTION_SECONDS,
        indeterminate_retention_seconds: float = DEFAULT_INDETERMINATE_RETENTION_SECONDS,
        terminal_retention_seconds: float = DEFAULT_TERMINAL_RETENTION_SECONDS,
    ) -> None:
        """Initialize the process-local Approval State store.

        Keyword Args:
            max_entries: Maximum approval occurrences or middleware state entries to retain.
            pending_retention_seconds: Maximum time to retain abandoned pending approval authority.
            indeterminate_retention_seconds: Safety window for uncertain execution records before reclamation.
            terminal_retention_seconds: Process-local duplicate-execution protection window.

        Raises:
            ValueError: If ``max_entries`` is less than 1.
        """
        if max_entries < 1:
            raise ValueError("max_entries must be greater than 0.")
        self.max_entries = max_entries
        self._lock = RLock()
        self._tool_approval_states: dict[str, dict[str, Any]] = {}
        self.lifecycle = ApprovalLifecycle(
            max_entries=max_entries,
            pending_retention_seconds=pending_retention_seconds,
            indeterminate_retention_seconds=indeterminate_retention_seconds,
            terminal_retention_seconds=terminal_retention_seconds,
        )

    def register(
        self,
        *,
        thread_ids: list[str],
        name: str,
        arguments: str,
        request_id: str,
        interrupt_id: str,
        owner: ApprovalExecutionOwner,
        scope: ApprovalScope | None = None,
        already_approved_requests: list[dict[str, Any]] | None = None,
        server_label: str | None = None,
    ) -> None:
        """Register one occurrence with its pending transition owner."""
        unique_thread_ids = list(dict.fromkeys(thread_ids))
        self.lifecycle.register(
            owner=owner,
            scope=scope,
            thread_ids=unique_thread_ids,
            interrupt_id=interrupt_id,
            call_id=interrupt_id,
            name=name,
            arguments=arguments,
            aliases=[request_id],
            already_approved_requests=already_approved_requests,
            server_label=server_label,
        )

    def set_tool_approval_state(self, thread_id: str, state: dict[str, Any]) -> None:
        """Store approval middleware state without evicting another active thread."""
        with self._lock:
            if thread_id not in self._tool_approval_states and len(self._tool_approval_states) >= self.max_entries:
                raise ApprovalCapacityError("Approval state capacity is exhausted by protected occurrences.")
            self._tool_approval_states[thread_id] = copy.deepcopy(state)

    def get_tool_approval_state(self, thread_id: str) -> dict[str, Any] | None:
        """Return an isolated copy of server-owned middleware approval state."""
        with self._lock:
            state = self._tool_approval_states.get(thread_id)
            return copy.deepcopy(state) if state is not None else None

    def delete_tool_approval_state(self, thread_id: str) -> None:
        """Delete server-owned middleware approval state for one scoped thread."""
        with self._lock:
            self._tool_approval_states.pop(thread_id, None)

    def has_tool_approval_state(self, thread_id: str) -> bool:
        """Return whether middleware approval state exists for one scoped thread."""
        with self._lock:
            return thread_id in self._tool_approval_states
