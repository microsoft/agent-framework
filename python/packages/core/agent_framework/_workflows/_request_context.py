# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence
from typing import Any, cast

from ._const import (
    WORKFLOW_AGENT_RUN_KEY,
    WORKFLOW_AGENT_SESSION_ID_KEY,
    WORKFLOW_PARENT_SESSION_ID_KEY,
    WORKFLOW_REQUEST_PARENT_CONTEXTS_KEY,
    WORKFLOW_SESSION_ID_KEY,
)
from ._events import WorkflowEvent
from ._state import State

logger = logging.getLogger(__name__)

_RUN_CONTEXT_KEYS = (
    WORKFLOW_SESSION_ID_KEY,
    WORKFLOW_PARENT_SESSION_ID_KEY,
    WORKFLOW_AGENT_RUN_KEY,
    WORKFLOW_AGENT_SESSION_ID_KEY,
)
_MISSING_ORIGIN = object()


def request_context_state_key(boundary_id: str | None = None) -> str:
    """Keep wrapped child origins independent of external requests with the same ID."""
    if boundary_id is None:
        return WORKFLOW_REQUEST_PARENT_CONTEXTS_KEY
    return f"{WORKFLOW_REQUEST_PARENT_CONTEXTS_KEY}:{boundary_id}"


def _validate_origin(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("Invalid parent workflow request context.")
    context = cast(dict[str, Any], value)
    if set(context) != set(_RUN_CONTEXT_KEYS):
        raise ValueError("Invalid parent workflow request context.")
    scope = context[WORKFLOW_SESSION_ID_KEY]
    inherited_scope = context[WORKFLOW_PARENT_SESSION_ID_KEY]
    agent_session = context[WORKFLOW_AGENT_SESSION_ID_KEY]
    if (
        not isinstance(scope, str)
        or not scope
        or (inherited_scope is not None and (not isinstance(inherited_scope, str) or not inherited_scope))
        or not isinstance(context[WORKFLOW_AGENT_RUN_KEY], bool)
        or (agent_session is not None and not isinstance(agent_session, str))
    ):
        raise ValueError("Invalid parent workflow request context.")
    return context


def validate_request_contexts(
    contexts: Any,
    requests: Sequence[WorkflowEvent] = (),
    *,
    boundary_contexts: Sequence[tuple[Any, Sequence[WorkflowEvent]]] = (),
) -> None:
    """Preflight all origin owners together before any responses are consumed."""
    scopes: set[str] = set()
    for pending_contexts, pending_requests in ((contexts, requests), *boundary_contexts):
        if not isinstance(pending_contexts, dict):
            raise ValueError("Invalid parent workflow request contexts.")
        pending_contexts = cast(dict[str, Any], pending_contexts)
        for request_id, value in pending_contexts.items():
            if not isinstance(request_id, str):
                raise ValueError("Invalid parent workflow request context.")
            _validate_origin(value)
        scopes.update(
            pending_contexts[request.request_id][WORKFLOW_SESSION_ID_KEY]
            for request in pending_requests
            if request.request_id in pending_contexts
        )
    if len(scopes) > 1:
        raise ValueError("Responses span multiple parent workflow scopes; submit each scope in a separate run.")


def capture_request_context(state: State, request_id: str, *, boundary_id: str | None = None) -> None:
    """Associate a request with framework-owned run metadata, without copying its payload."""
    state_key = request_context_state_key(boundary_id)
    existing = state._get_mapping_item(state_key, request_id, _MISSING_ORIGIN)  # pyright: ignore[reportPrivateUsage]
    if existing is not _MISSING_ORIGIN:
        _validate_origin(existing)
        return
    origin = {key: state.get(key) for key in _RUN_CONTEXT_KEYS}
    if origin[WORKFLOW_SESSION_ID_KEY] is None:
        logger.warning("Workflow request %s has no active run scope; assigning a new isolated scope.", request_id)
        origin[WORKFLOW_SESSION_ID_KEY] = uuid.uuid4().hex
        state.set(WORKFLOW_SESSION_ID_KEY, origin[WORKFLOW_SESSION_ID_KEY])
    origin[WORKFLOW_AGENT_RUN_KEY] = origin[WORKFLOW_AGENT_RUN_KEY] is True
    _validate_origin(origin)
    state._set_mapping_item(state_key, request_id, origin)  # pyright: ignore[reportPrivateUsage]


def restore_request_context(state: State, request_id: str, *, boundary_id: str | None = None) -> None:
    """Restore and release a request's run metadata before its continuation executes."""
    state_key = request_context_state_key(boundary_id)
    if boundary_id is not None and not state.has(state_key):
        # Checkpoints predating separate boundary ownership used the external-request map.
        state_key = WORKFLOW_REQUEST_PARENT_CONTEXTS_KEY
    origin = state._get_mapping_item(state_key, request_id, _MISSING_ORIGIN)  # pyright: ignore[reportPrivateUsage]
    if origin is not _MISSING_ORIGIN:
        _validate_origin(origin)
        state._pop_mapping_item(state_key, request_id)  # pyright: ignore[reportPrivateUsage]
    else:
        logger.warning(
            "Workflow request %s has no checkpointed run origin; assigning a new isolated scope.", request_id
        )
        origin = {
            WORKFLOW_SESSION_ID_KEY: uuid.uuid4().hex,
            WORKFLOW_PARENT_SESSION_ID_KEY: None,
            WORKFLOW_AGENT_RUN_KEY: False,
            WORKFLOW_AGENT_SESSION_ID_KEY: None,
        }
    for key in _RUN_CONTEXT_KEYS:
        state.set(key, origin[key])
