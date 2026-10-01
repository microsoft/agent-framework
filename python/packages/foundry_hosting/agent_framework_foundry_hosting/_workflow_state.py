# Copyright (c) Microsoft. All rights reserved.

"""Exact native workflow pairs and linear reply authority within a trusted sandbox."""

from __future__ import annotations

import hashlib
import json
import secrets
from collections.abc import AsyncGenerator, Mapping
from dataclasses import asdict, dataclass, replace
from typing import Any, Literal, cast

from agent_framework import (
    CheckpointStorage,
    Content,
    Workflow,
    WorkflowCheckpoint,
    WorkflowEvent,
    WorkflowInvocationKwargs,
    WorkflowRunState,
)
from agent_framework._workflows._agent_executor import (
    _validate_computer_tool_result,  # pyright: ignore[reportPrivateUsage]
)
from agent_framework._workflows._checkpoint_encoding import encode_checkpoint_value
from agent_framework._workflows._const import (
    RESOLVED_WORKFLOW_RUN_KWARGS_KEY,
    ROUTED_WORKFLOW_RUN_KWARGS_KEY,
    WORKFLOW_RUN_KWARGS_KEY,
)
from agent_framework._workflows._typing_utils import is_instance_of
from agent_framework._workflows._workflow import (
    _coerce_request_info_response,  # pyright: ignore[reportPrivateUsage]
)
from azure.ai.agentserver.core import AgentConfig, FoundryAgentRequestContext
from azure.ai.agentserver.core.storage import (
    FoundryStateStore,
    FoundryStorageConflictError,
    FoundryStoragePreconditionError,
)

from ._request import WorkflowTurn
from ._scope import FoundryRequestScope
from ._state_store import CheckpointStoreProvider, ContextScopedStoreProvider
from ._workflow_source import prepare_workflow_kwargs

_CONFLICT = "Another request advanced this workflow. Reload its current response or start a fresh lineage."
_BLOCKED = "This workflow turn was interrupted or failed; start a fresh workflow lineage to avoid replaying effects."


def _key(kind: str, identifier: str) -> str:
    if not isinstance(identifier, str) or not identifier:
        raise ValueError("A non-empty workflow state identifier is required.")
    return f"{kind}-{hashlib.sha256(identifier.encode('utf-8')).hexdigest()}"


def _json_object(value: Mapping[str, Any]) -> dict[str, Any]:
    """Validate snapshots without arbitrary encoders or success-shaped string fallbacks."""
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise TypeError("A workflow output snapshot must be a JSON object.")
    return cast(dict[str, Any], json.loads(json.dumps(dict(value), allow_nan=False)))


def _checkpoint_hash(checkpoint: WorkflowCheckpoint) -> str:
    encoded = encode_checkpoint_value(checkpoint.to_dict())
    return hashlib.sha256(json.dumps(encoded, sort_keys=True, allow_nan=False).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class WorkflowBinding:
    """The exact checkpoint for one outer response, not a sandbox or provider session."""

    response_id: str
    checkpoint_id: str | None
    lineage_id: str
    workflow_name: str
    graph_hash: str
    scope_key: str
    checkpoint_hash: str | None = None
    conversation_id: str | None = None
    previous_response_id: str | None = None

    @classmethod
    def from_value(cls, value: Any, scope: FoundryRequestScope) -> WorkflowBinding:
        if not isinstance(value, dict):
            raise ValueError("Invalid persisted workflow binding.")
        value = cast(dict[str, Any], value)
        if set(value) != set(cls.__dataclass_fields__):
            raise ValueError("Invalid persisted workflow binding.")
        for name in ("response_id", "lineage_id", "workflow_name", "graph_hash", "scope_key"):
            if not isinstance(value[name], str) or not value[name]:
                raise ValueError("Invalid persisted workflow binding.")
        for name in ("checkpoint_id", "checkpoint_hash", "conversation_id", "previous_response_id"):
            if value[name] is not None and (not isinstance(value[name], str) or not value[name]):
                raise ValueError("Invalid persisted workflow binding.")
        if (value["checkpoint_id"] is None) != (value["checkpoint_hash"] is None):
            raise ValueError("Invalid persisted workflow checkpoint identity.")
        binding = cls(**value)
        if binding.scope_key != scope.storage_key:
            raise PermissionError("The workflow state is not available in this trusted scope.")
        return binding


@dataclass(frozen=True)
class WorkflowRecord:
    """A per-response checkpoint/output pair retained independently of a later head."""

    binding: WorkflowBinding
    owner: str
    status: Literal["active", "completed", "blocked"]
    snapshot: dict[str, Any] | None = None
    approvals: dict[str, str] | None = None

    @classmethod
    def from_value(cls, value: Any, scope: FoundryRequestScope) -> WorkflowRecord:
        if not isinstance(value, dict):
            raise ValueError("Invalid persisted workflow response pair.")
        value = cast(dict[str, Any], value)
        if set(value) != set(cls.__dataclass_fields__):
            raise ValueError("Invalid persisted workflow response pair.")
        binding = WorkflowBinding.from_value(value["binding"], scope)
        if (
            not isinstance(value["owner"], str)
            or not value["owner"]
            or value["status"]
            not in (
                "active",
                "completed",
                "blocked",
            )
        ):
            raise ValueError("Invalid persisted workflow response pair.")
        snapshot = value["snapshot"]
        if snapshot is not None:
            snapshot = _json_object(snapshot)
        raw_approvals = value["approvals"]
        approvals: dict[str, str] | None = None
        if raw_approvals is not None:
            if not isinstance(raw_approvals, dict):
                raise ValueError("Invalid persisted workflow reply authority.")
            approvals = {}
            for wire_id, request_id in cast(dict[object, object], raw_approvals).items():
                if not isinstance(wire_id, str) or not wire_id or not isinstance(request_id, str) or not request_id:
                    raise ValueError("Invalid persisted workflow reply authority.")
                approvals[wire_id] = request_id
        if value["status"] == "completed" and (binding.checkpoint_id is None or snapshot is None):
            raise ValueError("A completed workflow response requires an exact checkpoint/output pair.")
        return cls(binding, value["owner"], value["status"], snapshot, approvals)


@dataclass(frozen=True)
class WorkflowHead:
    """One CAS authority for a lineage, including its optional named conversation."""

    lineage_id: str
    conversation_id: str | None
    binding: WorkflowBinding | None = None
    response_id: str | None = None
    owner: str | None = None
    blocked: bool = False

    @classmethod
    def from_value(cls, value: Any, scope: FoundryRequestScope) -> WorkflowHead:
        if not isinstance(value, dict):
            raise ValueError("Invalid persisted workflow head.")
        value = cast(dict[str, Any], value)
        if set(value) != set(cls.__dataclass_fields__):
            raise ValueError("Invalid persisted workflow head.")
        if not isinstance(value["lineage_id"], str) or not value["lineage_id"] or type(value["blocked"]) is not bool:
            raise ValueError("Invalid persisted workflow head.")
        for name in ("conversation_id", "response_id", "owner"):
            if value[name] is not None and (not isinstance(value[name], str) or not value[name]):
                raise ValueError("Invalid persisted workflow head.")
        if (value["owner"] is None) != (value["response_id"] is None):
            raise ValueError("Invalid persisted workflow claim.")
        binding = WorkflowBinding.from_value(value["binding"], scope) if value["binding"] is not None else None
        if binding is not None and (
            binding.lineage_id != value["lineage_id"] or binding.conversation_id != value["conversation_id"]
        ):
            raise ValueError("Invalid persisted workflow head binding.")
        return cls(
            value["lineage_id"],
            value["conversation_id"],
            binding,
            value["response_id"],
            value["owner"],
            value["blocked"],
        )


class FoundryWorkflowBindingStore:
    """Persist scoped per-response pairs and fenced linear workflow claims."""

    def __init__(self, scope: FoundryRequestScope) -> None:
        self.scope = scope

    async def _get_store(self) -> FoundryStateStore:
        return await FoundryStateStore.get_or_create(
            f"workflow_bindings/v2/{self.scope.storage_key}", user_isolation=True
        )

    async def get_response(self, response_id: str) -> tuple[WorkflowRecord | None, str | None]:
        store = await self._get_store()
        async with store:
            item = await store.get_item(_key("response", response_id), call_id=self.scope.call_id)
        if item is None:
            return None, None
        record = WorkflowRecord.from_value(item.value, self.scope)
        if record.binding.response_id != response_id or not item.etag:
            raise ValueError("Invalid persisted workflow response identity or ETag.")
        return record, item.etag

    async def get_head(self, lineage_id: str, conversation_id: str | None) -> tuple[WorkflowHead | None, str | None]:
        store = await self._get_store()
        key = _key("conversation", conversation_id) if conversation_id is not None else _key("lineage", lineage_id)
        async with store:
            item = await store.get_item(key, call_id=self.scope.call_id)
        if item is None:
            return None, None
        head = WorkflowHead.from_value(item.value, self.scope)
        if (
            head.conversation_id != conversation_id
            or (conversation_id is None and head.lineage_id != lineage_id)
            or not item.etag
        ):
            raise ValueError("Invalid persisted workflow head identity or ETag.")
        return head, item.etag

    async def save_response(self, record: WorkflowRecord, *, expected_etag: str | None) -> str:
        if record.binding.scope_key != self.scope.storage_key:
            raise PermissionError("Cannot write workflow state outside its trusted scope.")
        return await self._write(_key("response", record.binding.response_id), asdict(record), expected_etag)

    async def save_head(self, head: WorkflowHead, *, expected_etag: str | None) -> str:
        if head.binding is not None and head.binding.scope_key != self.scope.storage_key:
            raise PermissionError("Cannot write workflow state outside its trusted scope.")
        key = (
            _key("conversation", head.conversation_id)
            if head.conversation_id is not None
            else _key("lineage", head.lineage_id)
        )
        return await self._write(key, asdict(head), expected_etag)

    async def _write(self, key: str, value: dict[str, Any], expected_etag: str | None) -> str:
        store = await self._get_store()
        async with store:
            try:
                if expected_etag is None:
                    result = await store.create_item(key, value, call_id=self.scope.call_id)
                else:
                    result = await store.set_item(key, value, if_match=expected_etag, call_id=self.scope.call_id)
            except (FoundryStorageConflictError, FoundryStoragePreconditionError) as exc:
                raise RuntimeError(_CONFLICT) from exc
        if not result.etag:
            raise RuntimeError("Workflow storage did not acknowledge a conditional write with an ETag.")
        return result.etag


class _CheckpointWrites:
    """Track acknowledged core saves, never selecting an unrelated latest checkpoint."""

    def __init__(self, storage: CheckpointStorage, run: HostedWorkflowRun) -> None:
        self.storage = storage
        self.run = run
        self.last_checkpoint: WorkflowCheckpoint | None = None
        self.acknowledged_ids: set[str] = set()

    async def save(self, checkpoint: WorkflowCheckpoint) -> str:
        await self.run.assert_claim()
        identifier = await self.storage.save(checkpoint)
        if identifier != checkpoint.checkpoint_id:
            raise RuntimeError("Workflow checkpoint storage acknowledged a different checkpoint.")
        self.last_checkpoint = checkpoint
        self.acknowledged_ids.add(identifier)
        return identifier

    async def load(self, checkpoint_id: str) -> WorkflowCheckpoint:
        checkpoint = await self.storage.load(checkpoint_id)
        # Core checkpoint restoration follows run-kwargs setup. Retain fresh request
        # kwargs rather than restoring the previous request's private call context.
        fresh = self.run.workflow._runner.state.export_state()  # pyright: ignore[reportPrivateUsage]
        state = dict(checkpoint.state)
        for key in (WORKFLOW_RUN_KWARGS_KEY, RESOLVED_WORKFLOW_RUN_KWARGS_KEY, ROUTED_WORKFLOW_RUN_KWARGS_KEY):
            state[key] = fresh.get(key, {})
        return replace(checkpoint, state=state)

    async def list_checkpoints(self, *, workflow_name: str) -> list[WorkflowCheckpoint]:
        return await self.storage.list_checkpoints(workflow_name=workflow_name)

    async def list_checkpoint_ids(self, *, workflow_name: str) -> list[str]:
        return await self.storage.list_checkpoint_ids(workflow_name=workflow_name)

    async def get_latest(self, *, workflow_name: str) -> WorkflowCheckpoint | None:
        return await self.storage.get_latest(workflow_name=workflow_name)

    async def delete(self, checkpoint_id: str) -> bool:
        return await self.storage.delete(checkpoint_id)


class HostedWorkflowRun:
    """A native turn with explicit validation, claim, pairing, commit, and abort boundaries.

    Protocol hosts own output encoding and lifecycle signals. Closing ``events``
    never commits a turn. A failed or cancelled claim is blocked rather than
    releasing potentially consumed approvals or replaying external side effects.
    """

    def __init__(self, workflow: Workflow, scope: FoundryRequestScope, *, stored: bool, recovery: bool) -> None:
        self.workflow = workflow
        self.scope = scope
        self.stored = stored
        self.recovery = recovery
        self.store = FoundryWorkflowBindingStore(scope)
        self.binding: WorkflowBinding
        self._head: WorkflowHead | None = None
        self._head_etag: str | None = None
        self._record: WorkflowRecord | None = None
        self._record_etag: str | None = None
        self._storage: _CheckpointWrites | None = None
        self._checkpoint: WorkflowCheckpoint | None = None
        self._reply_approvals: dict[str, str] = {}
        self._turn: WorkflowTurn[Any] | None = None
        self._client_kwargs = WorkflowInvocationKwargs()
        self._function_kwargs = WorkflowInvocationKwargs()
        self._claimed = False
        self._finalized = False
        self.already_completed = False

    @classmethod
    async def prepare(
        cls,
        workflow: Workflow,
        *,
        scope: FoundryRequestScope,
        response_id: str,
        config: AgentConfig,
        platform_context: FoundryAgentRequestContext,
        checkpoint_store_provider: ContextScopedStoreProvider[CheckpointStorage],
        previous_response_id: str | None = None,
        conversation_id: str | None = None,
        lineage_id: str | None = None,
        stored: bool = True,
        recovery: bool = False,
    ) -> HostedWorkflowRun:
        """Read exact continuation state without claiming, consuming replies, or executing."""
        if not workflow.name or not workflow.graph_signature_hash:
            raise ValueError("Native workflows require a stable, non-empty workflow name and graph identity.")
        if previous_response_id is not None and conversation_id is not None:
            raise ValueError("A workflow turn cannot combine previous_response_id and conversation.")
        if not stored and (recovery or previous_response_id is not None or conversation_id is not None):
            raise ValueError("store=false workflow requests cannot continue stored state; start a one-shot turn.")
        run = cls(workflow, scope, stored=stored, recovery=recovery)
        run.binding = WorkflowBinding(
            response_id=response_id,
            checkpoint_id=None,
            lineage_id=lineage_id or response_id,
            workflow_name=workflow.name,
            graph_hash=workflow.graph_signature_hash,
            scope_key=scope.storage_key,
            conversation_id=conversation_id,
            previous_response_id=previous_response_id,
        )
        if not stored:
            return run

        own, own_etag = await run.store.get_response(response_id)
        if recovery:
            if own is None or own.binding.checkpoint_id is None or own.snapshot is None:
                raise RuntimeError(
                    "No acknowledged checkpoint/output pair can recover this response; start a fresh lineage."
                )
            if own.status == "blocked":
                raise RuntimeError(_BLOCKED)
            run._record, run._record_etag = own, own_etag
            run.binding = own.binding
            run._reply_approvals = own.approvals or {}
        elif own is not None:
            raise ValueError("This workflow response already exists; retrieve it instead of executing it again.")

        previous: WorkflowBinding | None = None
        if not recovery and previous_response_id is not None:
            record, _ = await run.store.get_response(previous_response_id)
            if record is None or record.status != "completed":
                raise ValueError("The previous response has no completed workflow checkpoint in this trusted scope.")
            previous = record.binding
            run._reply_approvals = record.approvals or {}
            if previous.conversation_id is not None:
                raise ValueError("A named workflow conversation cannot be forked through previous_response_id.")
            run.binding = replace(run.binding, lineage_id=previous.lineage_id)

        head, etag = await run.store.get_head(run.binding.lineage_id, run.binding.conversation_id)
        run._head, run._head_etag = head, etag
        if recovery:
            if head is None:
                raise RuntimeError("The workflow recovery authority is unavailable; start a fresh lineage.")
            if own is not None and own.status == "completed":
                current = head.binding
                visited: set[str] = set()
                while current is not None and current != own.binding:
                    if current.response_id in visited or current.previous_response_id is None:
                        current = None
                        break
                    visited.add(current.response_id)
                    parent, _ = await run.store.get_response(current.previous_response_id)
                    current = parent.binding if parent is not None and parent.status == "completed" else None
                if current is not None:
                    run.already_completed = True
                elif head.response_id != response_id or head.blocked:
                    raise RuntimeError(_CONFLICT)
                else:
                    run._finalized = True
            elif own is None or head.response_id != response_id or head.owner != own.owner or head.blocked:
                raise RuntimeError(_CONFLICT)
            previous = run.binding
        elif head is not None:
            if head.blocked:
                raise RuntimeError(_BLOCKED)
            if head.response_id is not None:
                raise RuntimeError("This workflow has an in-flight turn. Wait for it or start a fresh lineage.")
            if previous is not None and head.binding != previous:
                raise ValueError("This workflow continuation is stale or forked; use its current response.")
            previous = head.binding
            if previous is not None:
                record, _ = await run.store.get_response(previous.response_id)
                if record is None or record.status != "completed" or record.binding != previous:
                    raise ValueError("The workflow head has no exact completed response binding.")
                run._reply_approvals = record.approvals or {}
            run.binding = replace(
                run.binding,
                lineage_id=head.lineage_id,
                previous_response_id=previous.response_id if previous is not None else None,
            )
        elif previous is not None:
            raise ValueError("The workflow lineage authority is unavailable in this trusted scope.")

        context_id = _key("native", f"{scope.storage_key}:{run.binding.lineage_id}")
        storage = (
            checkpoint_store_provider.get_store_for_scope(
                scope=scope, context_id=context_id, platform_context=platform_context
            )
            if isinstance(checkpoint_store_provider, CheckpointStoreProvider)
            else checkpoint_store_provider.get_store(
                config=config, context_id=context_id, platform_context=platform_context
            )
        )
        run._storage = _CheckpointWrites(storage, run)
        if previous is not None:
            if previous.workflow_name != workflow.name or previous.graph_hash != workflow.graph_signature_hash:
                raise ValueError(
                    "The stored workflow graph is incompatible. Rebuild its original graph or start a fresh lineage."
                )
            if previous.checkpoint_id is None:
                raise ValueError("The workflow response has no acknowledged checkpoint.")
            checkpoint = await storage.load(previous.checkpoint_id)
            if (
                checkpoint.checkpoint_id != previous.checkpoint_id
                or checkpoint.workflow_name != workflow.name
                or checkpoint.graph_signature_hash != workflow.graph_signature_hash
                or _checkpoint_hash(checkpoint) != previous.checkpoint_hash
            ):
                raise ValueError("The exact workflow checkpoint does not match its response binding.")
            run._checkpoint = checkpoint
        return run

    @property
    def snapshot(self) -> dict[str, Any] | None:
        """The exact same-response recovery snapshot, independent of the current lineage head."""
        return self._record.snapshot if self._record is not None else None

    @property
    def approvals(self) -> Mapping[str, str]:
        """Caller-facing approval aliases bound to the loaded response's exact checkpoint."""
        return self._reply_approvals

    @property
    def has_completed_output(self) -> bool:
        """Whether recovery can deliver already finalized output without rerunning executors."""
        return self._record is not None and self._record.status == "completed"

    @property
    def pending_requests(self) -> Mapping[str, WorkflowEvent[Any]]:
        """Pending request authority from the exact acknowledged checkpoint."""
        checkpoint = self.current_checkpoint
        return checkpoint.pending_request_info_events if checkpoint is not None else {}

    @property
    def current_checkpoint(self) -> WorkflowCheckpoint | None:
        """The last acknowledged checkpoint from this run, or its exact restoration checkpoint."""
        if self._storage is not None and self._storage.last_checkpoint is not None:
            return self._storage.last_checkpoint
        return self._checkpoint

    @property
    def checkpoint_id(self) -> str | None:
        """The exact acknowledged checkpoint ID, never a latest-checkpoint query."""
        checkpoint = self.current_checkpoint
        return checkpoint.checkpoint_id if checkpoint is not None else None

    def validate_turn(self, turn: WorkflowTurn[Any]) -> WorkflowTurn[Any]:
        """Validate all input/replies and existing workflow kwargs before claiming authority."""
        if not isinstance(turn, WorkflowTurn):
            raise TypeError("The workflow parser must return WorkflowTurn.")
        self._client_kwargs, self._function_kwargs = prepare_workflow_kwargs(
            self.workflow, turn, self.scope, stored=self.stored
        )
        if self.recovery:
            self._turn = turn
            return turn
        pending = self.pending_requests
        if turn.responses is not None:
            if not self.stored or self._checkpoint is None:
                raise ValueError("Workflow replies require a pending stored checkpoint.")
            if set(turn.responses) != set(pending) or not pending:
                raise ValueError("Workflow replies must answer exactly the complete pending request batch.")
            replies: dict[str, Any] = {}
            reply_ids: set[tuple[str, str]] = set()
            for request_id, reply in turn.responses.items():
                event = pending[request_id]
                try:
                    reply = _coerce_request_info_response(reply, event.response_type, request_id)
                except (TypeError, ValueError) as exc:
                    raise ValueError("A workflow reply does not match its pending request type.") from exc
                if isinstance(event.data, Content):
                    request = event.data
                    if isinstance(reply, Content):
                        identifier = reply.id if reply.type == "function_approval_response" else reply.call_id
                        if identifier is not None:
                            key = (reply.type, identifier)
                            if key in reply_ids:
                                raise ValueError("Duplicate workflow reply authority is not allowed.")
                            reply_ids.add(key)
                    if request.type == "function_approval_request" and (
                        not isinstance(reply, Content)
                        or reply.type != "function_approval_response"
                        or reply.id != request.id
                        or type(reply.approved) is not bool
                        or reply.function_call is None
                        or request.function_call is None
                        or reply.function_call.to_dict() != request.function_call.to_dict()
                    ):
                        raise ValueError("The approval decision does not match its exact pending function call.")
                    if request.type == "function_call" and (
                        not isinstance(reply, Content)
                        or reply.type != "function_result"
                        or reply.call_id != request.call_id
                    ):
                        raise ValueError("The function result does not match its pending call.")
                    if request.type == "computer_tool_call":
                        if not isinstance(reply, Content):
                            raise ValueError("A computer reply must be typed Content.")
                        _validate_computer_tool_result(request, reply)
                replies[request_id] = reply
            turn = replace(turn, responses=replies)
        else:
            if pending:
                raise ValueError("This workflow is awaiting replies; do not replace them with new input.")
            if self._checkpoint is not None and any(self._checkpoint.messages.values()):
                raise ValueError("The workflow is still in flight; new input cannot replace its checkpoint.")
            if not any(is_instance_of(turn.input, input_type) for input_type in self.workflow.input_types):
                raise ValueError("The workflow parser's input does not match the start executor's type.")
        self._turn = turn
        return turn

    async def claim(self) -> None:
        """Fence the exact validated turn before any executor or response handler runs."""
        if self._turn is None:
            raise RuntimeError("Validate the workflow turn before claiming it.")
        if self._claimed or self.already_completed:
            return
        if not self.stored:
            self._claimed = True
            return
        owner = secrets.token_hex(16)
        head = replace(
            self._head or WorkflowHead(self.binding.lineage_id, self.binding.conversation_id),
            response_id=self.binding.response_id,
            owner=owner,
        )
        self._head_etag = await self.store.save_head(head, expected_etag=self._head_etag)
        self._head = head
        self._claimed = True
        record = (
            replace(self._record, owner=owner)
            if self.recovery and self._record is not None
            else WorkflowRecord(self.binding, owner, "active")
        )
        self._record_etag = await self.store.save_response(record, expected_etag=self._record_etag)
        self._record = record

    async def assert_claim(self) -> None:
        if not self._claimed:
            raise RuntimeError("The workflow turn has not been claimed.")
        if not self.stored:
            return
        head, etag = await self.store.get_head(self.binding.lineage_id, self.binding.conversation_id)
        if head != self._head or etag != self._head_etag or head is None or head.blocked:
            raise RuntimeError(_CONFLICT)

    async def events(
        self,
        turn: WorkflowTurn[Any],
        *,
        client_kwargs: WorkflowInvocationKwargs | Mapping[str, Any] | None = None,
        function_invocation_kwargs: WorkflowInvocationKwargs | Mapping[str, Any] | None = None,
    ) -> AsyncGenerator[WorkflowEvent[Any]]:
        """Execute core events, with explicit caller-owned commit and cancellation boundaries."""
        if self.already_completed or self.has_completed_output:
            return
        await self.assert_claim()
        if self._turn is None:
            raise RuntimeError("The workflow turn has not been validated.")
        turn = self._turn
        if self._checkpoint is not None and not self.recovery:
            await self.workflow._runner.restore_checkpoint(self._checkpoint)  # pyright: ignore[reportPrivateUsage]
        stream = self.workflow.run(
            None if self.recovery else turn.input,
            responses=None if self.recovery else turn.responses,
            checkpoint_id=self._checkpoint.checkpoint_id if self.recovery and self._checkpoint is not None else None,
            checkpoint_storage=self._storage,
            stream=True,
            client_kwargs=client_kwargs if client_kwargs is not None else self._client_kwargs,
            function_invocation_kwargs=(
                function_invocation_kwargs if function_invocation_kwargs is not None else self._function_kwargs
            ),
        )
        try:
            async for event in stream:
                if event.type == "request_info" and not self.stored:
                    raise ValueError("Approval and user-input continuation requires store=true.")
                yield event
            result = await stream.get_final_response()
            if result.get_final_state() not in (WorkflowRunState.IDLE, WorkflowRunState.IDLE_WITH_PENDING_REQUESTS):
                raise RuntimeError("The workflow did not finalize successfully.")
            self._finalized = True
        finally:
            await stream.close()

    async def stage(
        self,
        snapshot: Mapping[str, Any],
        *,
        approvals: Mapping[str, str] | None = None,
        checkpoint_id: str | None = None,
    ) -> None:
        """CAS-pair output with an acknowledged core checkpoint before publishing its events."""
        if not self.stored:
            return
        snapshot_value = _json_object(snapshot)
        checkpoint = await self.get_checkpoint(checkpoint_id or self.checkpoint_id)
        if checkpoint is None:
            raise RuntimeError("Output cannot be paired before a core checkpoint is acknowledged.")
        if approvals is not None and any(
            request_id not in checkpoint.pending_request_info_events for request_id in approvals.values()
        ):
            raise ValueError("Approval authority must belong to this exact pending checkpoint.")
        await self.assert_claim()
        if self._record is None:
            raise RuntimeError("The workflow response pair has not been claimed.")
        binding = replace(
            self.binding, checkpoint_id=checkpoint.checkpoint_id, checkpoint_hash=_checkpoint_hash(checkpoint)
        )
        pending_approvals = {
            wire_id: request_id
            for wire_id, request_id in (approvals if approvals is not None else self._record.approvals or {}).items()
            if request_id in checkpoint.pending_request_info_events
        }
        record = replace(
            self._record,
            binding=binding,
            snapshot=snapshot_value,
            approvals=pending_approvals,
        )
        self._record_etag = await self.store.save_response(record, expected_etag=self._record_etag)
        self.binding, self._record = binding, record
        await self.assert_claim()

    async def get_checkpoint(self, checkpoint_id: str | None) -> WorkflowCheckpoint | None:
        """Read a checkpoint acknowledged in this run, including a producer-stamped stream boundary."""
        if checkpoint_id is None:
            return None
        if self._storage is None or (
            checkpoint_id not in self._storage.acknowledged_ids
            and (self._checkpoint is None or checkpoint_id != self._checkpoint.checkpoint_id)
        ):
            raise ValueError("Output pairing requires a checkpoint acknowledged by this exact workflow turn.")
        checkpoint = await self._storage.storage.load(checkpoint_id)
        if (
            checkpoint.checkpoint_id != checkpoint_id
            or checkpoint.workflow_name != self.workflow.name
            or checkpoint.graph_signature_hash != self.workflow.graph_signature_hash
        ):
            raise ValueError("The acknowledged workflow checkpoint identity changed.")
        return checkpoint

    async def commit(self, snapshot: Mapping[str, Any] | None = None) -> None:
        """Commit only fully finalized, encoded output, before protocol success or done."""
        if self.already_completed:
            return
        if not self._finalized:
            raise RuntimeError("A workflow cannot commit before successful core finalization.")
        if not self.stored:
            return
        if snapshot is not None:
            await self.stage(snapshot)
        await self.assert_claim()
        if self._record is None or self._record.snapshot is None or self.binding.checkpoint_id != self.checkpoint_id:
            raise RuntimeError("The final workflow output has not been paired with its exact checkpoint.")
        record = replace(self._record, status="completed")
        self._record_etag = await self.store.save_response(record, expected_etag=self._record_etag)
        self._record = record
        head = WorkflowHead(self.binding.lineage_id, self.binding.conversation_id, self.binding)
        self._head_etag = await self.store.save_head(head, expected_etag=self._head_etag)
        self._head = head
        self._claimed = False

    async def abort(self) -> None:
        """Block interrupted/failed authority instead of permitting unsafe reply or effect replay."""
        if not self.stored or not self._claimed or self.already_completed:
            return
        await self.assert_claim()
        if self._record is not None:
            record = replace(self._record, status="blocked")
            self._record_etag = await self.store.save_response(record, expected_etag=self._record_etag)
            self._record = record
        if self._head is not None:
            head = replace(self._head, blocked=True)
            self._head_etag = await self.store.save_head(head, expected_etag=self._head_etag)
            self._head = head
        self._claimed = False
