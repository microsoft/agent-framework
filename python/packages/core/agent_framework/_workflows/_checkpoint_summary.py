# Copyright (c) Microsoft. All rights reserved.

import logging
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from textwrap import shorten
from typing import Any

from ._checkpoint import WorkflowCheckpoint
from ._request_info_executor import PendingRequestDetails, RequestInfoMessage, RequestResponse
from ._runner_context import _decode_checkpoint_value  # type: ignore

logger = logging.getLogger(__name__)


@dataclass
class WorkflowCheckpointSummary:
    """Human-readable summary of a workflow checkpoint."""

    checkpoint_id: str
    iteration_count: int
    targets: list[str]
    executor_ids: list[str]
    status: str
    draft_preview: str | None
    pending_requests: list[PendingRequestDetails]


def get_checkpoint_summary(
    checkpoint: WorkflowCheckpoint,
    *,
    request_executor_ids: Iterable[str] | None = None,
    preview_width: int = 70,
) -> WorkflowCheckpointSummary:
    targets = sorted(checkpoint.messages.keys())
    executor_ids = sorted(checkpoint.executor_states.keys())
    pending = _pending_requests_from_checkpoint(checkpoint, request_executor_ids=request_executor_ids)

    draft_preview: str | None = None
    for entry in pending:
        if entry.draft:
            draft_preview = shorten(entry.draft, width=preview_width, placeholder="…")
            break

    status = "idle"
    if pending:
        status = "awaiting request response"
    elif not checkpoint.messages and "finalise" in executor_ids:
        status = "completed"
    elif checkpoint.messages:
        status = "awaiting next superstep"
    elif request_executor_ids is not None and any(tid in targets for tid in request_executor_ids):
        status = "awaiting request delivery"

    return WorkflowCheckpointSummary(
        checkpoint_id=checkpoint.checkpoint_id,
        iteration_count=checkpoint.iteration_count,
        targets=targets,
        executor_ids=executor_ids,
        status=status,
        draft_preview=draft_preview,
        pending_requests=pending,
    )


def _pending_requests_from_checkpoint(
    checkpoint: WorkflowCheckpoint,
    *,
    request_executor_ids: Iterable[str] | None = None,
) -> list[PendingRequestDetails]:
    executor_filter: set[str] | None = None
    if request_executor_ids is not None:
        executor_filter = {str(value) for value in request_executor_ids}

    pending: dict[str, PendingRequestDetails] = {}

    for state in checkpoint.executor_states.values():
        if not isinstance(state, Mapping):
            continue
        inner = state.get("pending_requests")
        if isinstance(inner, Mapping):
            for request_id, snapshot in inner.items():  # type: ignore[attr-defined]
                _merge_snapshot(pending, str(request_id), snapshot)  # type: ignore[arg-type]

    for source_id, message_list in checkpoint.messages.items():
        if executor_filter is not None and source_id not in executor_filter:
            continue
        if not isinstance(message_list, list):
            continue
        for message in message_list:
            if not isinstance(message, Mapping):
                continue
            payload = _decode_checkpoint_value(message.get("data"))
            _merge_message_payload(pending, payload, message)

    return list(pending.values())


def _merge_snapshot(pending: dict[str, PendingRequestDetails], request_id: str, snapshot: Any) -> None:
    if not request_id or not isinstance(snapshot, Mapping):
        return

    details = pending.setdefault(request_id, PendingRequestDetails(request_id=request_id))

    _apply_update(
        details,
        prompt=snapshot.get("prompt"),  # type: ignore[attr-defined]
        draft=snapshot.get("draft"),  # type: ignore[attr-defined]
        iteration=snapshot.get("iteration"),  # type: ignore[attr-defined]
        source_executor_id=snapshot.get("source_executor_id"),  # type: ignore[attr-defined]
    )

    extra = snapshot.get("details")  # type: ignore[attr-defined]
    if isinstance(extra, Mapping):
        _apply_update(
            details,
            prompt=extra.get("prompt"),  # type: ignore[attr-defined]
            draft=extra.get("draft"),  # type: ignore[attr-defined]
            iteration=extra.get("iteration"),  # type: ignore[attr-defined]
        )


def _merge_message_payload(
    pending: dict[str, PendingRequestDetails],
    payload: Any,
    raw_message: Mapping[str, Any],
) -> None:
    if isinstance(payload, RequestResponse):
        request_id = payload.request_id or _get_field(payload.original_request, "request_id")  # type: ignore[arg-type]
        if not request_id:
            return
        details = pending.setdefault(request_id, PendingRequestDetails(request_id=request_id))
        _apply_update(
            details,
            prompt=_get_field(payload.original_request, "prompt"),  # type: ignore[arg-type]
            draft=_get_field(payload.original_request, "draft"),  # type: ignore[arg-type]
            iteration=_get_field(payload.original_request, "iteration"),  # type: ignore[arg-type]
            source_executor_id=raw_message.get("source_id"),
            original_request=payload.original_request,  # type: ignore[arg-type]
        )
    elif isinstance(payload, RequestInfoMessage):
        request_id = getattr(payload, "request_id", None)
        if not request_id:
            return
        details = pending.setdefault(request_id, PendingRequestDetails(request_id=request_id))
        _apply_update(
            details,
            prompt=getattr(payload, "prompt", None),
            draft=getattr(payload, "draft", None),
            iteration=getattr(payload, "iteration", None),
            source_executor_id=raw_message.get("source_id"),
            original_request=payload,
        )


def _apply_update(
    details: PendingRequestDetails,
    *,
    prompt: Any = None,
    draft: Any = None,
    iteration: Any = None,
    source_executor_id: Any = None,
    original_request: Any = None,
) -> None:
    if prompt and not details.prompt:
        details.prompt = str(prompt)
    if draft and not details.draft:
        details.draft = str(draft)
    if iteration is not None and details.iteration is None:
        coerced = _coerce_int(iteration)
        if coerced is not None:
            details.iteration = coerced
    if source_executor_id and not details.source_executor_id:
        details.source_executor_id = str(source_executor_id)
    if original_request is not None and details.original_request is None:
        details.original_request = original_request


def _get_field(obj: Any, key: str) -> Any:
    if obj is None:
        return None
    if isinstance(obj, Mapping):
        return obj.get(key)  # type: ignore[attr-defined,return-value]
    return getattr(obj, key, None)


def _coerce_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
