# Copyright (c) Microsoft. All rights reserved.

"""Host-agnostic execution of non-agent workflow executors as durable activities.

When a MAF :class:`Workflow` runs as a durable orchestration, each non-agent
executor is dispatched as a durable *activity*. The activity body is identical
regardless of host (Azure Functions or a standalone durabletask worker): it
deserializes the activity input, runs the executor (or a human-in-the-loop
response handler), diffs the shared state, and serializes the executor's
outputs, sent messages, shared-state changes, and any pending HITL requests back
to the orchestrator.

This module provides that shared body as :func:`execute_workflow_activity` so
both host adapters call one implementation instead of duplicating it.
"""

from __future__ import annotations

import asyncio
import json
from copy import deepcopy
from typing import Any, cast

from agent_framework import Executor, Workflow, WorkflowEvent
from agent_framework._workflows._runner_context import YieldOutputEventType
from agent_framework._workflows._state import State

from .orchestrator import (
    SOURCE_HITL_RESPONSE,
    SOURCE_ORCHESTRATOR,
    execute_hitl_response_handler,
)
from .runner_context import CapturingRunnerContext
from .serialization import deserialize_value, serialize_value, serialize_workflow_event


def execute_workflow_activity(executor: Executor, input_json: str, workflow: Workflow | None = None) -> str:
    """Execute a single non-agent workflow executor and return its serialized result.

    This is the host-agnostic activity body shared by the Azure Functions and
    standalone durabletask workflow hosts.

    Args:
        executor: The non-agent executor instance to run.
        input_json: JSON-encoded activity input with keys ``message``,
            ``shared_state_snapshot``, and ``source_executor_ids``.
        workflow: The owning workflow, used to classify the executor's
            ``yield_output`` payloads as final ``output`` vs ``intermediate``.
            When omitted, all yielded outputs are treated as final outputs.

    Returns:
        A JSON string with keys ``sent_messages``, ``outputs``, ``events``,
        ``shared_state_updates``, ``shared_state_deletes``, and
        ``pending_request_info_events``.

    Raises:
        ValueError: If the input does not decode to a JSON object, or a HITL
            message payload is not a JSON object.
    """
    data_obj = json.loads(input_json)
    if not isinstance(data_obj, dict):
        raise ValueError("Activity input must decode to a JSON object")
    data = cast(dict[str, Any], data_obj)

    message_data = data.get("message")
    # The orchestrator may pass null for these when shared state / sources are
    # omitted, so coerce None to the appropriate empty default.
    shared_state_snapshot: dict[str, Any] = data.get("shared_state_snapshot") or {}
    source_executor_ids = cast(list[str], data.get("source_executor_ids") or [SOURCE_ORCHESTRATOR])

    # Reconstruct the message - deserialize_value restores the original typed
    # objects from the encoded data (with type markers).
    message = deserialize_value(message_data)

    # A HITL response is identified by a source id starting with the HITL prefix.
    is_hitl_response = any(s.startswith(SOURCE_HITL_RESPONSE) for s in source_executor_ids)

    def classify_yielded_output(executor_id: str) -> YieldOutputEventType | None:
        # Mirror the core runner's classification so intermediate executors'
        # yields are not surfaced as final workflow outputs.
        if workflow is None:
            return "output"
        if workflow.is_terminal_executor(executor_id):
            return "output"
        if workflow.is_intermediate_executor(executor_id):
            return "intermediate"
        return None

    async def _run() -> dict[str, Any]:
        runner_context = CapturingRunnerContext()
        runner_context.set_yield_output_classifier(classify_yielded_output)
        shared_state = State()

        # Deserialize shared state values to reconstruct dataclasses / Pydantic models.
        deserialized_state: dict[str, Any] = {str(k): deserialize_value(v) for k, v in shared_state_snapshot.items()}
        # Snapshot the deserialized (in-memory) state for diffing. State.export_state()
        # returns the in-memory committed objects, so the snapshot must hold objects
        # too (deepcopy) - comparing against a serialized snapshot would mark every
        # key as changed.
        original_snapshot = deepcopy(deserialized_state)
        shared_state.import_state(deserialized_state)

        if is_hitl_response:
            if not isinstance(message_data, dict):
                raise ValueError("HITL message payload must be a JSON object")
            await execute_hitl_response_handler(
                executor=executor,
                hitl_message=cast(dict[str, Any], message_data),
                shared_state=shared_state,
                runner_context=runner_context,
            )
        else:
            await executor.execute(
                message=message,
                source_executor_ids=source_executor_ids,
                state=shared_state,
                runner_context=runner_context,
            )

        # Commit pending state changes and compute the diff vs the original snapshot.
        shared_state.commit()
        current_state = shared_state.export_state()
        original_keys: set[str] = set(original_snapshot.keys())
        current_keys: set[str] = set(current_state.keys())

        # Deleted = was in original, not in current.
        deletes: set[str] = original_keys - current_keys

        # Updates = keys that are new or whose value changed.
        updates: dict[str, Any] = {}
        for key in current_keys:
            if key not in original_keys or current_state[key] != original_snapshot.get(key):
                updates[key] = current_state[key]

        sent_messages = await runner_context.drain_messages()
        events = await runner_context.drain_events()

        # Serialize the executor's workflow events so the orchestrator can republish
        # them to the streaming custom status. Output payloads are also extracted
        # separately for message routing and the final workflow result.
        outputs: list[Any] = []
        serialized_events: list[dict[str, Any]] = []
        for event in events:
            if not isinstance(event, WorkflowEvent):
                continue
            serialized_events.append(serialize_workflow_event(event))
            if event.type == "output":
                outputs.append(serialize_value(event.data))

        # Serialize pending HITL request info events for the orchestrator.
        pending_request_info_events = await runner_context.get_pending_request_info_events()
        serialized_pending_requests: list[dict[str, Any]] = []
        for _request_id, event in pending_request_info_events.items():
            serialized_pending_requests.append({
                "request_id": event.request_id,
                "source_executor_id": event.source_executor_id,
                "data": serialize_value(event.data),
                "request_type": f"{type(event.data).__module__}:{type(event.data).__name__}",
                "response_type": f"{event.response_type.__module__}:{event.response_type.__name__}"
                if event.response_type
                else None,
            })

        # Serialize sent messages for JSON compatibility.
        serialized_sent_messages: list[dict[str, Any]] = []
        for _source_id, msg_list in sent_messages.items():
            for msg in msg_list:
                serialized_sent_messages.append({
                    "message": serialize_value(msg.data),
                    "target_id": msg.target_id,
                    "source_id": msg.source_id,
                })

        serialized_updates = {k: serialize_value(v) for k, v in updates.items()}

        return {
            "sent_messages": serialized_sent_messages,
            "outputs": outputs,
            "events": serialized_events,
            "shared_state_updates": serialized_updates,
            "shared_state_deletes": list(deletes),
            "pending_request_info_events": serialized_pending_requests,
        }

    result = asyncio.run(_run())
    return json.dumps(result)
