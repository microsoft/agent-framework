# Copyright (c) Microsoft. All rights reserved.

"""Server-owned lifecycle for AG-UI approval-gated tool calls."""

from __future__ import annotations

import logging
from asyncio import CancelledError
from collections.abc import Awaitable, Callable, Iterator
from contextlib import ExitStack
from dataclasses import dataclass, field
from enum import Enum
from functools import wraps
from threading import RLock
from time import monotonic
from typing import Any, TypeVar
from uuid import uuid4

from agent_framework import Content

logger = logging.getLogger(__name__)
_ReturnT = TypeVar("_ReturnT")


def _serialized_registration(method: Callable[..., _ReturnT]) -> Callable[..., _ReturnT]:
    @wraps(method)
    def wrapper(self: ApprovalLifecycle, *args: Any, **kwargs: Any) -> _ReturnT:
        with self._index_lock:
            return method(self, *args, **kwargs)

    return wrapper


def _serialized_by_batch(method: Callable[..., _ReturnT]) -> Callable[..., _ReturnT]:
    @wraps(method)
    def wrapper(self: ApprovalLifecycle, *args: Any, **kwargs: Any) -> _ReturnT:
        thread_id = kwargs.get("thread_id")
        if not isinstance(thread_id, str):
            raise TypeError("Serialized approval transitions require a thread_id.")
        decisions = kwargs.get("decisions")
        decision_interrupt_ids = (
            [decision.interrupt_id for decision in decisions]
            if isinstance(decisions, list) and all(isinstance(decision, ResumeDecision) for decision in decisions)
            else []
        )
        cancellation_interrupt_ids = kwargs.get("cancelled_interrupt_ids", kwargs.get("interrupt_ids", []))
        interrupt_ids = [*decision_interrupt_ids, *cancellation_interrupt_ids]
        if not isinstance(interrupt_ids, list) or not all(
            isinstance(interrupt_id, str) for interrupt_id in interrupt_ids
        ):
            raise TypeError("Serialized approval transitions require interrupt identities.")
        locks = self._locks_for_batch(thread_id=thread_id, interrupt_ids=interrupt_ids)
        with ExitStack() as stack:
            for lock in locks:
                stack.enter_context(lock)
            try:
                return method(self, *args, **kwargs)
            except (KeyError, ValueError) as exc:
                self._emit_event("authority_failure", failure_type=type(exc).__name__)
                raise

    return wrapper


def _serialized_by_occurrence(method: Callable[..., _ReturnT]) -> Callable[..., _ReturnT]:
    @wraps(method)
    def wrapper(self: ApprovalLifecycle, *args: Any, **kwargs: Any) -> _ReturnT:
        intent = args[0] if args else kwargs.get("intent")
        if not isinstance(intent, AuthorizedExecution):
            raise TypeError("Serialized approval transitions require an authorized execution.")
        with self._lock_for_identity(intent.identity):
            return method(self, *args, **kwargs)

    return wrapper


class ApprovalIndeterminateError(ValueError):
    """An approval may have executed but has no retained terminal outcome."""


class ApprovalCapacityError(RuntimeError):
    """Approval state capacity is exhausted by protected occurrences."""


class ApprovalClaimConflictError(ValueError):
    """Approval authority cannot be claimed in its current state."""


class ApprovalSettlementConflictError(ValueError):
    """An approval outcome cannot settle in its current state."""


class ApprovalStatus(str, Enum):
    """Lifecycle state of one server-owned approval occurrence."""

    PENDING = "pending"
    CLAIMED = "claimed"
    EXECUTING = "executing"
    SETTLED = "settled"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    INDETERMINATE = "indeterminate"

    @property
    def is_terminal(self) -> bool:
        """Whether this state has ended its approval authority."""
        return self in {
            ApprovalStatus.SETTLED,
            ApprovalStatus.REJECTED,
            ApprovalStatus.CANCELLED,
            ApprovalStatus.EXPIRED,
            ApprovalStatus.INDETERMINATE,
        }

    @property
    def is_purgeable(self) -> bool:
        """Whether this terminal state may expire after the retention window."""
        return self.is_terminal and self is not ApprovalStatus.INDETERMINATE


class ApprovalExecutionOwner(str, Enum):
    """Runtime owner authorized to continue an approved occurrence."""

    LOCAL = "local"
    HOSTED = "hosted"
    DEFERRED = "deferred"
    UNAVAILABLE = "unavailable"


class ClaimRecoveryPolicy(str, Enum):
    """Proof required to release authority before execution begins."""

    SAFE_TO_RETRY = "safe_to_retry"


@dataclass(frozen=True)
class ApprovalOccurrenceIdentity:
    """Identity of one occurrence within a scoped server-owned thread."""

    thread_id: str
    occurrence_id: str
    interrupt_id: str
    call_id: str


@dataclass(frozen=True)
class ApprovalSnapshotReconciliation:
    """Semantic lifecycle result used to retire or retain one snapshot control."""

    interrupt_id: str
    identity: ApprovalOccurrenceIdentity | None
    status: ApprovalStatus | None
    retire_interrupt: bool

    @property
    def is_missing(self) -> bool:
        """Whether no lifecycle occurrence exists for the snapshot interrupt."""
        return self.status is None


@dataclass(frozen=True)
class ResumeDecision:
    """Canonical client decision presented to the approval lifecycle."""

    interrupt_id: str
    accepted: bool
    arguments: str | None
    name: str | None = None
    original_arguments: str | None = None


@dataclass
class ApprovalOccurrence:
    """Server-owned state for one approval-gated call occurrence."""

    identity: ApprovalOccurrenceIdentity
    thread_ids: tuple[str, ...]
    name: str
    arguments: str
    owner: ApprovalExecutionOwner
    scope: str | None = None
    aliases: tuple[str, ...] = ()
    response_id: str | None = None
    already_approved_requests: tuple[dict[str, Any], ...] = ()
    server_label: str | None = None
    idempotency_key: str | None = None
    status: ApprovalStatus = ApprovalStatus.PENDING
    pending_since: float = 0
    replayable_results: list[ReplayableToolResult] = field(default_factory=list)
    decision: ResumeDecision | None = None
    outcome: ApprovalOutcome | None = None
    terminal_at: float | None = None


@dataclass(frozen=True)
class AuthorizedExecution:
    """Authority for one Pending Tool Transition Owner to continue a call."""

    identity: ApprovalOccurrenceIdentity
    name: str
    arguments: str
    owner: ApprovalExecutionOwner
    idempotency_key: str | None = None


@dataclass(frozen=True)
class ReplayableToolResult:
    """A settled tool result retained under its original call identity."""

    content: Content


@dataclass(frozen=True)
class ApprovalOutcome:
    """Terminal outcome retained for one approval occurrence."""

    identity: ApprovalOccurrenceIdentity
    replayable_results: tuple[ReplayableToolResult, ...]
    result_group: tuple[Content, ...]
    snapshot_reconciliation: ApprovalSnapshotReconciliation


@dataclass(frozen=True)
class ApprovalBatchDecision:
    """Validated batch result containing new authority and retained outcomes."""

    authorized_executions: tuple[AuthorizedExecution, ...]
    retained_outcomes: tuple[ApprovalOutcome, ...] = ()
    snapshot_reconciliations: tuple[ApprovalSnapshotReconciliation, ...] = ()

    def __iter__(self) -> Iterator[AuthorizedExecution]:
        """Iterate newly authorized executions for compatibility with existing callers."""
        return iter(self.authorized_executions)


class ApprovalLifecycle:
    """Own process-local registration, authority transitions, and settlement for approvals."""

    def __init__(
        self,
        *,
        max_entries: int = 10_000,
        pending_retention_seconds: float = 86_400,
        indeterminate_retention_seconds: float = 604_800,
        terminal_retention_seconds: float = 900,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if max_entries < 1:
            raise ValueError("max_entries must be greater than 0.")
        if pending_retention_seconds <= 0:
            raise ValueError("pending_retention_seconds must be greater than 0.")
        if indeterminate_retention_seconds <= 0:
            raise ValueError("indeterminate_retention_seconds must be greater than 0.")
        if terminal_retention_seconds <= 0:
            raise ValueError("terminal_retention_seconds must be greater than 0.")
        self._max_entries = max_entries
        self._pending_retention_seconds = pending_retention_seconds
        self._indeterminate_retention_seconds = indeterminate_retention_seconds
        self._terminal_retention_seconds = terminal_retention_seconds
        self._clock = clock
        self._index_lock = RLock()
        self._locks_by_identity: dict[ApprovalOccurrenceIdentity, RLock] = {}
        self._occurrences: dict[ApprovalOccurrenceIdentity, ApprovalOccurrence] = {}
        self._pending_by_interrupt: dict[tuple[str, str], ApprovalOccurrenceIdentity] = {}
        self._terminal_by_interrupt: dict[tuple[str, str], ApprovalOccurrenceIdentity] = {}

    def register(
        self,
        *,
        owner: ApprovalExecutionOwner,
        scope: str | None = None,
        thread_ids: list[str] | None = None,
        thread_id: str | None = None,
        interrupt_id: str,
        call_id: str,
        name: str,
        arguments: str,
        aliases: list[str] | None = None,
        response_id: str | None = None,
        already_approved_requests: list[dict[str, Any]] | None = None,
        server_label: str | None = None,
        idempotency_key: str | None = None,
    ) -> ApprovalOccurrence:
        """Register one approval occurrence with its pending transition owner."""
        if (thread_ids is None) == (thread_id is None):
            raise ValueError("Provide exactly one of thread_id or thread_ids when registering an approval.")
        resolved_thread_ids = thread_ids if thread_ids is not None else [thread_id]
        return self._register_aliases(
            thread_ids=[value for value in resolved_thread_ids if value is not None],
            interrupt_id=interrupt_id,
            call_id=call_id,
            name=name,
            arguments=arguments,
            owner=owner,
            scope=scope,
            aliases=aliases,
            response_id=response_id,
            already_approved_requests=already_approved_requests,
            server_label=server_label,
            idempotency_key=idempotency_key,
        )

    @_serialized_registration
    def _register_aliases(
        self,
        *,
        thread_ids: list[str],
        interrupt_id: str,
        call_id: str,
        name: str,
        arguments: str,
        owner: ApprovalExecutionOwner,
        scope: str | None = None,
        aliases: list[str] | None = None,
        response_id: str | None = None,
        already_approved_requests: list[dict[str, Any]] | None = None,
        server_label: str | None = None,
        idempotency_key: str | None = None,
    ) -> ApprovalOccurrence:
        self._purge_expired_terminal()
        if scope == "":
            raise ValueError("An approval scope cannot be empty.")
        if idempotency_key == "":
            raise ValueError("An execution idempotency key cannot be empty.")
        unique_thread_ids = tuple(dict.fromkeys(thread_ids))
        alias_values: list[str] = [interrupt_id, *(aliases or [])]
        occurrence_aliases = tuple(dict.fromkeys(alias_values))
        if not unique_thread_ids:
            raise ValueError("An approval occurrence requires at least one scoped thread identity.")
        existing_identities = {
            identity
            for thread_id in unique_thread_ids
            for alias in occurrence_aliases
            if (identity := self._pending_by_interrupt.get((thread_id, alias))) is not None
        }
        if len(existing_identities) > 1:
            raise ValueError("Approval aliases resolve to different pending occurrences.")
        if existing_identities:
            occurrence = self._occurrences[next(iter(existing_identities))]
            if occurrence.status is not ApprovalStatus.PENDING:
                raise ApprovalClaimConflictError(f"Approval occurrence is not pending: {occurrence.status}.")
            if (
                occurrence.identity.call_id != call_id
                or occurrence.name != name
                or occurrence.arguments != arguments
                or occurrence.owner is not owner
                or occurrence.scope != scope
                or occurrence.response_id != response_id
                or occurrence.idempotency_key != idempotency_key
                or occurrence.already_approved_requests != tuple(already_approved_requests or ())
                or occurrence.server_label != server_label
            ):
                raise ValueError("Approval alias conflicts with an existing pending occurrence.")
            occurrence.thread_ids = tuple(dict.fromkeys((*occurrence.thread_ids, *unique_thread_ids)))
            occurrence.aliases = tuple(dict.fromkeys((*occurrence.aliases, *occurrence_aliases)))
            for thread_id in occurrence.thread_ids:
                for alias in occurrence.aliases:
                    self._pending_by_interrupt[(thread_id, alias)] = occurrence.identity
            return occurrence

        if sum(occurrence.scope == scope for occurrence in self._occurrences.values()) >= self._max_entries:
            self._emit_event("capacity_failure")
            raise ApprovalCapacityError("Approval state capacity is exhausted by protected occurrences.")
        identity = ApprovalOccurrenceIdentity(
            thread_id=unique_thread_ids[0],
            occurrence_id=str(uuid4()),
            interrupt_id=interrupt_id,
            call_id=call_id,
        )
        occurrence = ApprovalOccurrence(
            identity=identity,
            thread_ids=unique_thread_ids,
            name=name,
            arguments=arguments,
            owner=owner,
            scope=scope,
            aliases=occurrence_aliases,
            response_id=response_id,
            already_approved_requests=tuple(already_approved_requests or ()),
            server_label=server_label,
            idempotency_key=idempotency_key,
            pending_since=self._clock(),
        )
        self._occurrences[identity] = occurrence
        for thread_id in unique_thread_ids:
            for alias in occurrence.aliases:
                self._pending_by_interrupt[(thread_id, alias)] = identity
        self._locks_by_identity[identity] = RLock()
        self._emit_event("registration", occurrence)
        return occurrence

    def get(self, identity: ApprovalOccurrenceIdentity) -> ApprovalOccurrence:
        """Return server-owned state for a registered occurrence."""
        with self._index_lock:
            self._purge_expired_terminal()
            return self._occurrences[identity]

    def decision_context(self, *, thread_id: str, interrupt_id: str) -> tuple[str, str]:
        """Return canonical server-owned call data needed to normalize a typed retry."""
        with self._index_lock:
            self._purge_expired_terminal()
            key = (thread_id, interrupt_id)
            identity = self._pending_by_interrupt.get(key) or self._terminal_by_interrupt[key]
            occurrence = self._occurrences[identity]
            return occurrence.name, occurrence.arguments

    def pending_occurrence(self, *, thread_id: str, interrupt_id: str) -> ApprovalOccurrence | None:
        """Return pending server-owned state for one trusted interrupt alias."""
        with self._index_lock:
            self._purge_expired_terminal()
            identity = self._pending_by_interrupt.get((thread_id, interrupt_id))
            return self._occurrences[identity] if identity is not None else None

    def occurrence_for_alias(self, *, thread_id: str, interrupt_id: str) -> ApprovalOccurrence | None:
        """Return retained server-owned state for one trusted interrupt alias."""
        with self._index_lock:
            self._purge_expired_terminal()
            key = (thread_id, interrupt_id)
            identity = self._pending_by_interrupt.get(key) or self._terminal_by_interrupt.get(key)
            return self._occurrences[identity] if identity is not None else None

    def occurrences_for_thread(self, *, thread_id: str) -> tuple[ApprovalOccurrence, ...]:
        """Return retained occurrences owned by one scoped thread."""
        with self._index_lock:
            self._purge_expired_terminal()
            return tuple(occurrence for occurrence in self._occurrences.values() if thread_id in occurrence.thread_ids)

    def pending_interrupt_ids(self, *, thread_id: str) -> set[str]:
        """Return canonical interrupt identities with pending authority for one thread."""
        with self._index_lock:
            self._purge_expired_terminal()
            return {
                occurrence.identity.interrupt_id
                for occurrence in self._occurrences.values()
                if thread_id in occurrence.thread_ids and occurrence.status is ApprovalStatus.PENDING
            }

    def reconcile_snapshot(
        self,
        *,
        thread_id: str,
        interrupt_ids: list[str],
    ) -> tuple[ApprovalSnapshotReconciliation, ...]:
        """Describe which stored approval controls remain actionable."""
        with self._index_lock:
            self._purge_expired_terminal()
            reconciliations: list[ApprovalSnapshotReconciliation] = []
            for interrupt_id in interrupt_ids:
                key = (thread_id, interrupt_id)
                identity = self._pending_by_interrupt.get(key) or self._terminal_by_interrupt.get(key)
                if identity is None:
                    reconciliations.append(
                        ApprovalSnapshotReconciliation(
                            interrupt_id=interrupt_id,
                            identity=None,
                            status=None,
                            retire_interrupt=True,
                        )
                    )
                    continue
                occurrence = self._occurrences[identity]
                reconciliations.append(self._snapshot_reconciliation(occurrence))
            return tuple(reconciliations)

    @staticmethod
    def _snapshot_reconciliation(occurrence: ApprovalOccurrence) -> ApprovalSnapshotReconciliation:
        return ApprovalSnapshotReconciliation(
            interrupt_id=occurrence.identity.interrupt_id,
            identity=occurrence.identity,
            status=occurrence.status,
            retire_interrupt=occurrence.status.is_terminal,
        )

    def claim(self, *, thread_id: str, decision: ResumeDecision) -> AuthorizedExecution:
        """Validate and reserve one accepted decision before execution."""
        if not decision.accepted:
            raise ValueError("A rejected decision cannot authorize execution.")
        batch = self.claim_batch(thread_id=thread_id, decisions=[decision])
        if not batch.authorized_executions:
            raise ValueError("A duplicate settled decision cannot authorize execution again.")
        return batch.authorized_executions[0]

    @_serialized_by_batch
    def claim_batch(
        self,
        *,
        thread_id: str,
        decisions: list[ResumeDecision],
    ) -> ApprovalBatchDecision:
        """Validate a complete decision batch before reserving accepted occurrences."""
        self._purge_expired_terminal()
        resolved: list[tuple[ResumeDecision, ApprovalOccurrence, bool]] = []
        seen_interrupt_ids: set[str] = set()
        for decision in decisions:
            if decision.interrupt_id in seen_interrupt_ids:
                raise ValueError(f"Approval batch repeats interrupt: {decision.interrupt_id}.")
            seen_interrupt_ids.add(decision.interrupt_id)
            key = (thread_id, decision.interrupt_id)
            identity = self._pending_by_interrupt.get(key)
            is_terminal = identity is None
            if identity is None:
                identity = self._terminal_by_interrupt[key]
            occurrence = self._occurrences[identity]
            if is_terminal:
                if occurrence.status is ApprovalStatus.INDETERMINATE:
                    raise ApprovalIndeterminateError(
                        "Approval execution outcome is indeterminate; automatic retry is unsafe."
                    )
                if occurrence.status is ApprovalStatus.EXPIRED:
                    raise ValueError("Approval authority has expired.")
                retained_decision = occurrence.decision
                if (
                    retained_decision is None
                    or retained_decision.accepted != decision.accepted
                    or (decision.name is not None and retained_decision.name != decision.name)
                    or (decision.arguments is not None and retained_decision.arguments != decision.arguments)
                    or (
                        decision.original_arguments is not None
                        and retained_decision.original_arguments != decision.original_arguments
                    )
                ):
                    raise ValueError("Approval decision conflicts with the retained terminal decision.")
                if occurrence.outcome is None:
                    raise ValueError(f"Approval occurrence has no replayable terminal outcome: {occurrence.status}.")
                resolved.append((decision, occurrence, True))
                continue
            if occurrence.status is not ApprovalStatus.PENDING:
                raise ApprovalClaimConflictError(f"Approval occurrence is not pending: {occurrence.status}.")
            if decision.name is not None and decision.name != occurrence.name:
                raise ValueError("Approval decision tool name does not match the registered occurrence.")
            canonical_arguments = decision.arguments
            if canonical_arguments is None:
                raise ValueError("A pending approval decision must include canonical arguments.")
            if (decision.original_arguments or canonical_arguments) != occurrence.arguments:
                raise ValueError("Approval decision arguments do not match the registered occurrence.")
            resolved.append((decision, occurrence, False))
        intents: list[AuthorizedExecution] = []
        retained_outcomes: list[ApprovalOutcome] = []
        snapshot_reconciliations: list[ApprovalSnapshotReconciliation] = []
        for decision, occurrence, is_terminal in resolved:
            if is_terminal:
                if occurrence.outcome is None:
                    raise RuntimeError("Validated terminal approval is missing its retained outcome.")
                retained_outcomes.append(occurrence.outcome)
                snapshot_reconciliations.append(occurrence.outcome.snapshot_reconciliation)
                self._emit_event("duplicate", occurrence)
                continue
            occurrence.decision = decision
            if not decision.accepted:
                if occurrence.owner is ApprovalExecutionOwner.DEFERRED:
                    occurrence.status = ApprovalStatus.CLAIMED
                    self._emit_event("claim", occurrence)
                    intents.append(
                        AuthorizedExecution(
                            identity=occurrence.identity,
                            name=occurrence.name,
                            arguments=occurrence.arguments,
                            owner=occurrence.owner,
                            idempotency_key=occurrence.idempotency_key,
                        )
                    )
                    continue
                result = Content.from_function_result(
                    call_id=occurrence.identity.call_id,
                    result="Error: Tool call invocation was rejected by user.",
                )
                occurrence.replayable_results = [ReplayableToolResult(content=result)]
                occurrence.status = ApprovalStatus.REJECTED
                self._remove_pending_aliases(occurrence)
                occurrence.outcome = ApprovalOutcome(
                    identity=occurrence.identity,
                    replayable_results=tuple(occurrence.replayable_results),
                    result_group=(result,),
                    snapshot_reconciliation=self._snapshot_reconciliation(occurrence),
                )
                snapshot_reconciliations.append(occurrence.outcome.snapshot_reconciliation)
                self._emit_event("rejection", occurrence)
                continue
            if decision.arguments is None:
                raise RuntimeError("Validated pending approval is missing canonical arguments.")
            occurrence.arguments = decision.arguments
            if occurrence.owner is ApprovalExecutionOwner.UNAVAILABLE:
                continue
            occurrence.status = ApprovalStatus.CLAIMED
            self._emit_event("claim", occurrence)
            intents.append(
                AuthorizedExecution(
                    identity=occurrence.identity,
                    name=occurrence.name,
                    arguments=occurrence.arguments,
                    owner=occurrence.owner,
                    idempotency_key=occurrence.idempotency_key,
                )
            )
        return ApprovalBatchDecision(
            authorized_executions=tuple(intents),
            retained_outcomes=tuple(retained_outcomes),
            snapshot_reconciliations=tuple(snapshot_reconciliations),
        )

    @_serialized_by_batch
    def resolve_batch(
        self,
        *,
        thread_id: str,
        decisions: list[ResumeDecision],
        cancelled_interrupt_ids: list[str],
    ) -> ApprovalBatchDecision:
        """Atomically validate and apply resolved and cancelled decisions for one resume batch."""
        self._purge_expired_terminal()
        cancelled_occurrences, retained_cancellations = self._validate_cancellations(
            thread_id=thread_id,
            interrupt_ids=cancelled_interrupt_ids,
        )
        decision_batch = self.claim_batch(thread_id=thread_id, decisions=decisions)
        cancellation_reconciliations = self._cancel_occurrences(cancelled_occurrences)
        return ApprovalBatchDecision(
            authorized_executions=decision_batch.authorized_executions,
            retained_outcomes=decision_batch.retained_outcomes,
            snapshot_reconciliations=(
                *decision_batch.snapshot_reconciliations,
                *retained_cancellations,
                *cancellation_reconciliations,
            ),
        )

    @_serialized_by_batch
    def cancel_batch(
        self,
        *,
        thread_id: str,
        interrupt_ids: list[str],
    ) -> tuple[ApprovalSnapshotReconciliation, ...]:
        """Validate and cancel selected occurrences without changing their siblings."""
        self._purge_expired_terminal()
        occurrences, reconciliations = self._validate_cancellations(
            thread_id=thread_id,
            interrupt_ids=interrupt_ids,
        )
        return (*reconciliations, *self._cancel_occurrences(occurrences))

    def _validate_cancellations(
        self,
        *,
        thread_id: str,
        interrupt_ids: list[str],
    ) -> tuple[list[ApprovalOccurrence], tuple[ApprovalSnapshotReconciliation, ...]]:
        """Validate cancellations without mutating lifecycle state."""
        occurrences: list[ApprovalOccurrence] = []
        reconciliations: list[ApprovalSnapshotReconciliation] = []
        seen_interrupt_ids: set[str] = set()
        for interrupt_id in interrupt_ids:
            if interrupt_id in seen_interrupt_ids:
                raise ValueError(f"Approval batch repeats interrupt: {interrupt_id}.")
            seen_interrupt_ids.add(interrupt_id)
            key = (thread_id, interrupt_id)
            identity = self._pending_by_interrupt.get(key)
            if identity is None:
                identity = self._terminal_by_interrupt[key]
                terminal = self._occurrences[identity]
                if terminal.status is ApprovalStatus.CANCELLED:
                    reconciliations.append(self._snapshot_reconciliation(terminal))
                    self._emit_event("duplicate", terminal)
                    continue
                raise ValueError("Approval cancellation conflicts with the retained terminal decision.")
            occurrence = self._occurrences[identity]
            if occurrence.status is not ApprovalStatus.PENDING:
                raise ValueError(f"Approval occurrence is not pending: {occurrence.status}.")
            occurrences.append(occurrence)

        return occurrences, tuple(reconciliations)

    def _cancel_occurrences(
        self,
        occurrences: list[ApprovalOccurrence],
    ) -> tuple[ApprovalSnapshotReconciliation, ...]:
        """Commit previously validated cancellations while their batch locks are held."""
        reconciliations: list[ApprovalSnapshotReconciliation] = []
        for occurrence in occurrences:
            occurrence.status = ApprovalStatus.CANCELLED
            self._remove_pending_aliases(occurrence)
            reconciliations.append(self._snapshot_reconciliation(occurrence))
            self._emit_event("cancellation", occurrence)
        return tuple(reconciliations)

    @_serialized_by_batch
    def expire_batch(
        self,
        *,
        thread_id: str,
        interrupt_ids: list[str],
    ) -> tuple[ApprovalSnapshotReconciliation, ...]:
        """Expire pending authority without permitting later execution."""
        self._purge_expired_terminal()
        occurrences: list[ApprovalOccurrence] = []
        seen_interrupt_ids: set[str] = set()
        for interrupt_id in interrupt_ids:
            if interrupt_id in seen_interrupt_ids:
                raise ValueError(f"Approval batch repeats interrupt: {interrupt_id}.")
            seen_interrupt_ids.add(interrupt_id)
            identity = self._pending_by_interrupt[(thread_id, interrupt_id)]
            occurrence = self._occurrences[identity]
            if occurrence.status is not ApprovalStatus.PENDING:
                raise ValueError(f"Approval occurrence is not pending: {occurrence.status}.")
            occurrences.append(occurrence)

        for occurrence in occurrences:
            occurrence.status = ApprovalStatus.EXPIRED
            self._remove_pending_aliases(occurrence)
            self._emit_event("expiration", occurrence)
        return tuple(self._snapshot_reconciliation(occurrence) for occurrence in occurrences)

    def _remove_pending_aliases(self, occurrence: ApprovalOccurrence) -> None:
        if occurrence.status.is_terminal:
            occurrence.terminal_at = self._clock()
        with self._index_lock:
            for thread_id in occurrence.thread_ids:
                for alias in occurrence.aliases:
                    self._pending_by_interrupt.pop((thread_id, alias), None)
                    self._terminal_by_interrupt[(thread_id, alias)] = occurrence.identity

    def _purge_expired_terminal(self) -> None:
        with self._index_lock:
            now = self._clock()
            pending_cutoff = now - self._pending_retention_seconds
            abandoned = [
                occurrence
                for occurrence in self._occurrences.values()
                if occurrence.status is ApprovalStatus.PENDING and occurrence.pending_since <= pending_cutoff
            ]
            for occurrence in abandoned:
                occurrence.status = ApprovalStatus.EXPIRED
                self._remove_pending_aliases(occurrence)
                occurrence.terminal_at = occurrence.pending_since + self._pending_retention_seconds
                self._emit_event("expiration", occurrence)
            cutoff = now - self._terminal_retention_seconds
            indeterminate_cutoff = now - self._indeterminate_retention_seconds
            expired = [
                occurrence
                for occurrence in self._occurrences.values()
                if occurrence.terminal_at is not None
                and (
                    (occurrence.status.is_purgeable and occurrence.terminal_at <= cutoff)
                    or (
                        occurrence.status is ApprovalStatus.INDETERMINATE
                        and occurrence.terminal_at <= indeterminate_cutoff
                    )
                )
            ]
            for occurrence in expired:
                self._emit_event("retention_purge", occurrence)
                self._occurrences.pop(occurrence.identity, None)
                self._locks_by_identity.pop(occurrence.identity, None)
                for thread_id in occurrence.thread_ids:
                    for alias in occurrence.aliases:
                        key = (thread_id, alias)
                        if self._terminal_by_interrupt.get(key) == occurrence.identity:
                            self._terminal_by_interrupt.pop(key, None)

    def _locks_for_batch(self, *, thread_id: str, interrupt_ids: list[str]) -> tuple[RLock, ...]:
        with self._index_lock:
            identities = {
                identity
                for interrupt_id in interrupt_ids
                if (
                    identity := self._pending_by_interrupt.get((thread_id, interrupt_id))
                    or self._terminal_by_interrupt.get((thread_id, interrupt_id))
                )
                is not None
            }
            return tuple(
                self._locks_by_identity[identity]
                for identity in sorted(identities, key=lambda item: item.occurrence_id)
            )

    def _lock_for_identity(self, identity: ApprovalOccurrenceIdentity) -> RLock:
        with self._index_lock:
            return self._locks_by_identity.setdefault(identity, RLock())

    @staticmethod
    def _emit_event(
        event: str,
        occurrence: ApprovalOccurrence | None = None,
        *,
        failure_type: str | None = None,
    ) -> None:
        extra: dict[str, str] = {"approval_event": event}
        if occurrence is not None:
            extra.update(
                approval_occurrence_id=occurrence.identity.occurrence_id,
                approval_status=occurrence.status.value,
                approval_owner=occurrence.owner.value,
            )
        if failure_type is not None:
            extra["approval_failure_type"] = failure_type
        logger.info("AG-UI approval lifecycle transition", extra=extra)

    @_serialized_by_occurrence
    def begin_execution(self, intent: AuthorizedExecution, *, owner: ApprovalExecutionOwner) -> None:
        """Mark that an external side effect may begin.

        A claimed occurrence only reserves authority. Once this transition succeeds,
        arbitrary execution cannot be assumed safe to retry without idempotency proof.
        """
        occurrence = self._occurrences[intent.identity]
        if intent.owner is not owner or occurrence.owner is not owner:
            raise ValueError(
                f"Approval occurrence belongs to the {occurrence.owner.value} transition owner, not {owner.value}."
            )
        if occurrence.status is not ApprovalStatus.CLAIMED:
            raise ApprovalClaimConflictError(f"Approval occurrence is not claimed: {occurrence.status}.")
        occurrence.status = ApprovalStatus.EXECUTING
        self._emit_event("execution_start", occurrence)

    @_serialized_by_occurrence
    def release_claim(self, intent: AuthorizedExecution, *, policy: ClaimRecoveryPolicy) -> None:
        """Release reserved authority when execution is known not to have begun."""
        occurrence = self._occurrences[intent.identity]
        if policy is not ClaimRecoveryPolicy.SAFE_TO_RETRY:
            raise ValueError("Claim recovery policy does not permit retry.")
        if occurrence.status is not ApprovalStatus.CLAIMED:
            raise ValueError(f"Approval occurrence is not claimed: {occurrence.status}.")
        occurrence.status = ApprovalStatus.PENDING
        occurrence.pending_since = self._clock()

    @_serialized_by_occurrence
    def mark_indeterminate(
        self,
        intent: AuthorizedExecution,
        *,
        owner: ApprovalExecutionOwner,
    ) -> ApprovalSnapshotReconciliation:
        """Record that execution may have begun but no result was settled."""
        occurrence = self._occurrences[intent.identity]
        if intent.owner is not owner or occurrence.owner is not owner:
            raise ValueError(
                f"Approval occurrence belongs to the {occurrence.owner.value} transition owner, not {owner.value}."
            )
        if occurrence.status is not ApprovalStatus.EXECUTING:
            raise ApprovalSettlementConflictError(f"Approval occurrence is not executing: {occurrence.status}.")
        occurrence.status = ApprovalStatus.INDETERMINATE
        self._remove_pending_aliases(occurrence)
        self._emit_event("indeterminate_recovery", occurrence)
        return self._snapshot_reconciliation(occurrence)

    @_serialized_by_occurrence
    def recover_execution(
        self,
        intent: AuthorizedExecution,
        *,
        owner: ApprovalExecutionOwner,
    ) -> AuthorizedExecution | None:
        """Recover an execution that has no settled result."""
        occurrence = self._occurrences[intent.identity]
        if intent.owner is not owner or occurrence.owner is not owner:
            raise ValueError(
                f"Approval occurrence belongs to the {occurrence.owner.value} transition owner, not {owner.value}."
            )
        if occurrence.status is not ApprovalStatus.EXECUTING:
            raise ApprovalSettlementConflictError(f"Approval occurrence is not executing: {occurrence.status}.")
        if occurrence.decision is not None and not occurrence.decision.accepted:
            occurrence.status = ApprovalStatus.PENDING
            occurrence.pending_since = self._clock()
            self._emit_event("rejection_recovery", occurrence)
            return None
        if intent.idempotency_key is not None and intent.idempotency_key == occurrence.idempotency_key:
            occurrence.status = ApprovalStatus.CLAIMED
            return intent
        self.mark_indeterminate(intent, owner=owner)
        return None

    @_serialized_by_occurrence
    def settle(self, intent: AuthorizedExecution, results: list[Content]) -> ApprovalOutcome:
        """Settle an executing occurrence with results under its original call identity."""
        occurrence = self._occurrences[intent.identity]
        if intent.owner is not ApprovalExecutionOwner.LOCAL or occurrence.owner is not ApprovalExecutionOwner.LOCAL:
            raise ValueError("Only the local transition owner can settle a local execution result.")
        if occurrence.status is not ApprovalStatus.EXECUTING:
            raise ApprovalSettlementConflictError(f"Approval occurrence is not executing: {occurrence.status}.")
        replayable_results = [
            ReplayableToolResult(content=result)
            for result in results
            if result.type == "function_result" and result.call_id == occurrence.identity.call_id
        ]
        if len(replayable_results) != 1:
            raise ValueError("A settled local approval must produce exactly one result for its original call.")
        occurrence.replayable_results = replayable_results
        occurrence.status = ApprovalStatus.SETTLED
        self._remove_pending_aliases(occurrence)
        outcome = ApprovalOutcome(
            identity=occurrence.identity,
            replayable_results=tuple(replayable_results),
            result_group=tuple(results),
            snapshot_reconciliation=self._snapshot_reconciliation(occurrence),
        )
        occurrence.outcome = outcome
        self._emit_event("settlement", occurrence)
        return outcome

    @_serialized_by_occurrence
    def settle_forwarded(
        self,
        intent: AuthorizedExecution,
        results: list[Content],
        *,
        owner: ApprovalExecutionOwner,
    ) -> ApprovalOutcome:
        """Record a forwarded owner's outcome under its original occurrence."""
        occurrence = self._occurrences[intent.identity]
        if owner not in {ApprovalExecutionOwner.HOSTED, ApprovalExecutionOwner.DEFERRED}:
            raise ValueError("Only a forwarding transition owner can record a forwarded outcome.")
        if intent.owner is not owner or occurrence.owner is not owner:
            raise ValueError(
                f"Approval occurrence belongs to the {occurrence.owner.value} transition owner, not {owner.value}."
            )
        if occurrence.status is not ApprovalStatus.EXECUTING:
            raise ApprovalSettlementConflictError(f"Approval occurrence is not executing: {occurrence.status}.")
        replayable_results = [
            ReplayableToolResult(content=result)
            for result in results
            if result.type == "function_result" and result.call_id == occurrence.identity.call_id
        ]
        forwarded_responses = [
            result
            for result in results
            if result.type == "function_approval_response"
            and isinstance(result.approved, bool)
            and result.function_call is not None
            and result.function_call.call_id == occurrence.identity.call_id
        ]
        if len(replayable_results) + len(forwarded_responses) != 1:
            raise ValueError("A hosted approval must record exactly one outcome for its original call.")
        is_rejection = len(forwarded_responses) == 1 and forwarded_responses[0].approved is False
        if is_rejection:
            rejection_result = Content.from_function_result(
                call_id=occurrence.identity.call_id,
                result="Error: Tool call invocation was rejected by user.",
            )
            replayable_results = [ReplayableToolResult(content=rejection_result)]
            result_group = (rejection_result,)
            occurrence.status = ApprovalStatus.REJECTED
        else:
            result_group = tuple(results)
            occurrence.status = ApprovalStatus.SETTLED
        occurrence.replayable_results = replayable_results
        self._remove_pending_aliases(occurrence)
        outcome = ApprovalOutcome(
            identity=occurrence.identity,
            replayable_results=tuple(replayable_results),
            result_group=result_group,
            snapshot_reconciliation=self._snapshot_reconciliation(occurrence),
        )
        occurrence.outcome = outcome
        self._emit_event("settlement", occurrence)
        return outcome

    @_serialized_by_occurrence
    def defer(self, intent: AuthorizedExecution, results: list[Content]) -> ApprovalOutcome:
        """Return an execution that yielded only follow-up requests to pending."""
        occurrence = self._occurrences[intent.identity]
        if intent.owner is not ApprovalExecutionOwner.LOCAL or occurrence.owner is not ApprovalExecutionOwner.LOCAL:
            raise ValueError("Only the local transition owner can defer a local execution.")
        if occurrence.status is not ApprovalStatus.EXECUTING:
            raise ValueError(f"Approval occurrence is not executing: {occurrence.status}.")
        occurrence.status = ApprovalStatus.PENDING
        occurrence.pending_since = self._clock()
        return ApprovalOutcome(
            identity=occurrence.identity,
            replayable_results=(),
            result_group=tuple(results),
            snapshot_reconciliation=self._snapshot_reconciliation(occurrence),
        )


class LocalPendingToolTransitionOwner:
    """Execute an authorized call through the process-local transition owner."""

    def __init__(self, executor: Callable[[], Awaitable[list[Content]]]) -> None:
        self._executor = executor

    async def execute(
        self,
        intent: AuthorizedExecution,
        *,
        lifecycle: ApprovalLifecycle,
    ) -> ApprovalOutcome:
        """Execute and settle one call after lifecycle authorization."""
        lifecycle.begin_execution(intent, owner=ApprovalExecutionOwner.LOCAL)
        try:
            results = await self._executor()
            if not any(result.type == "function_result" for result in results):
                return lifecycle.defer(intent, results)
            return lifecycle.settle(intent, results)
        except (Exception, CancelledError):
            lifecycle.recover_execution(intent, owner=ApprovalExecutionOwner.LOCAL)
            raise


class ForwardedPendingToolTransitionOwner:
    """Forward an authorized decision to a non-transport transition owner."""

    def __init__(
        self,
        forwarder: Callable[[], Awaitable[list[Content]]],
        *,
        owner: ApprovalExecutionOwner,
    ) -> None:
        self._forwarder = forwarder
        self._owner = owner

    async def forward(
        self,
        intent: AuthorizedExecution,
        *,
        lifecycle: ApprovalLifecycle,
    ) -> list[Content]:
        """Forward one hosted approval after lifecycle authorization."""
        lifecycle.begin_execution(intent, owner=self._owner)
        try:
            return await self._forwarder()
        except (Exception, CancelledError):
            lifecycle.recover_execution(intent, owner=self._owner)
            raise

    def record_outcome(
        self,
        intent: AuthorizedExecution,
        results: list[Content],
        *,
        lifecycle: ApprovalLifecycle,
    ) -> ApprovalOutcome:
        """Record the hosted owner's outcome against the authorized occurrence."""
        try:
            return lifecycle.settle_forwarded(intent, results, owner=self._owner)
        except (Exception, CancelledError):
            lifecycle.recover_execution(intent, owner=self._owner)
            raise

    async def execute(
        self,
        intent: AuthorizedExecution,
        *,
        lifecycle: ApprovalLifecycle,
    ) -> ApprovalOutcome:
        """Forward and immediately record an available hosted outcome."""
        return self.record_outcome(intent, await self.forward(intent, lifecycle=lifecycle), lifecycle=lifecycle)


class HostedPendingToolTransitionOwner(ForwardedPendingToolTransitionOwner):
    """Forward an authorized decision through the hosted transition owner."""

    def __init__(self, forwarder: Callable[[], Awaitable[list[Content]]]) -> None:
        super().__init__(forwarder, owner=ApprovalExecutionOwner.HOSTED)


class DeferredPendingToolTransitionOwner(ForwardedPendingToolTransitionOwner):
    """Forward an authorized decision to the in-run transition pipeline."""

    def __init__(self, forwarder: Callable[[], Awaitable[list[Content]]]) -> None:
        super().__init__(forwarder, owner=ApprovalExecutionOwner.DEFERRED)
