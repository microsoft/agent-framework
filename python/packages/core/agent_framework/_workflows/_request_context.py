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


def validate_request_contexts(contexts: Any, requests: Sequence[WorkflowEvent] = ()) -> dict[str, dict[str, Any]]:
    """Preflight checkpointed request origins before any responses are consumed."""
    if not isinstance(contexts, dict):
        raise ValueError("Invalid parent workflow request contexts.")
    contexts = cast(dict[str, dict[str, Any]], contexts)
    for request_id, value in contexts.items():
        if not isinstance(request_id, str) or not isinstance(value, dict):
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
    scopes = {
        contexts[request.request_id][WORKFLOW_SESSION_ID_KEY] for request in requests if request.request_id in contexts
    }
    if len(scopes) > 1:
        raise ValueError("Responses span multiple parent workflow scopes; submit each scope in a separate run.")
    return contexts


def capture_request_context(state: State, request_id: str) -> None:
    """Associate a request with framework-owned run metadata, without copying its payload."""
    contexts = validate_request_contexts(state.get(WORKFLOW_REQUEST_PARENT_CONTEXTS_KEY, {}))
    origin = {key: state.get(key) for key in _RUN_CONTEXT_KEYS}
    if origin[WORKFLOW_SESSION_ID_KEY] is None:
        logger.warning("Workflow request %s has no active run scope; assigning a new isolated scope.", request_id)
        origin[WORKFLOW_SESSION_ID_KEY] = uuid.uuid4().hex
        state.set(WORKFLOW_SESSION_ID_KEY, origin[WORKFLOW_SESSION_ID_KEY])
    origin[WORKFLOW_AGENT_RUN_KEY] = origin[WORKFLOW_AGENT_RUN_KEY] is True
    contexts.setdefault(request_id, origin)
    state.set(WORKFLOW_REQUEST_PARENT_CONTEXTS_KEY, contexts)


def restore_request_context(state: State, request_id: str) -> None:
    """Restore and release a request's run metadata before its continuation executes."""
    contexts = validate_request_contexts(state.get(WORKFLOW_REQUEST_PARENT_CONTEXTS_KEY, {}))
    origin = contexts.pop(request_id, None)
    if origin is None:
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
    state.set(WORKFLOW_REQUEST_PARENT_CONTEXTS_KEY, contexts)
