# Copyright (c) Microsoft. All rights reserved.

"""Internal serialization helpers for workflow execution.

These helpers are framework-internal plumbing for moving typed objects across
durable orchestration/activity boundaries. They are **not** part of the public
API and must not be called by application code.

They wrap the core checkpoint codec (``encode_checkpoint_value`` /
``decode_checkpoint_value`` from ``agent_framework._workflows``), which uses
pickle + base64 to round-trip arbitrary Python objects (dataclasses, Pydantic
models, ``Message``, ...) while leaving JSON-native types (str, int, float,
bool, None) as-is.

Because that codec can unpickle objects, every value that crosses an external
trust boundary -- HTTP request bodies and HITL responses raised as external
events -- is sanitized by the framework with :func:`strip_pickle_markers`
*before* it can reach these helpers. Application code never has to perform that
sanitization itself: the orchestrator, the activity body, and the HTTP entry
points already do it at the boundary. See
:mod:`agent_framework._workflows._checkpoint_encoding` for the full security model.

Contents:
- ``serialize_value`` / ``deserialize_value``: internal codec aliases for encode/decode.
- ``reconstruct_to_type``: rebuilds HITL response data (which arrives without type
  markers) to a known type.
- ``resolve_type``: resolves 'module:class' type keys to Python types.
- ``strip_pickle_markers``: the framework's trust-boundary defense that neutralizes
  attacker-injected pickle/type markers.
"""

from __future__ import annotations

import importlib
import logging
from contextlib import suppress
from dataclasses import is_dataclass
from typing import Any, cast

from agent_framework import WorkflowEvent
from agent_framework._workflows._checkpoint_encoding import (
    _PICKLE_MARKER,  # pyright: ignore[reportPrivateUsage]
    _TYPE_MARKER,  # pyright: ignore[reportPrivateUsage]
    decode_checkpoint_value,
    encode_checkpoint_value,
)
from agent_framework._workflows._events import WorkflowEventType
from pydantic import BaseModel

logger = logging.getLogger(__name__)


def resolve_type(type_key: str) -> type | None:
    """Resolve a 'module:class' type key to its Python type.

    Args:
        type_key: Fully qualified type reference in 'module_name:class_name' format.

    Returns:
        The resolved type, or None if resolution fails.
    """
    try:
        module_name, class_name = type_key.split(":", 1)
        module = importlib.import_module(module_name)
        resolved = getattr(module, class_name, None)
        # Only return actual classes. A non-type attribute (function, module member,
        # etc.) would raise TypeError in issubclass() inside reconstruct_to_type().
        return resolved if isinstance(resolved, type) else None
    except Exception:
        logger.debug("Could not resolve type %s", type_key)
        return None


# ============================================================================
# Pickle marker sanitization (security)
# ============================================================================


def strip_pickle_markers(data: Any) -> Any:
    """Recursively strip pickle/type markers from untrusted data.

    The core checkpoint encoding uses ``__pickled__`` and ``__type__`` markers to
    roundtrip arbitrary Python objects via *pickle*.  If an attacker crafts an
    HTTP payload that contains these markers, the data would flow into
    ``pickle.loads()`` and enable **arbitrary code execution**.

    This function walks the incoming data structure and replaces any ``dict``
    that contains either marker key with ``None``, neutralizing the attack
    vector while leaving all other data untouched.

    The framework applies this at every external trust boundary -- HTTP request
    bodies and HITL responses raised as external events -- before the value can
    reach the internal codec (:func:`deserialize_value` /
    ``decode_checkpoint_value``). Application code does not need to call it.
    """
    if isinstance(data, dict):
        if _PICKLE_MARKER in data or _TYPE_MARKER in data:
            logger.debug("Stripped pickle/type markers from untrusted input.")
            return None
        typed_dict = cast(dict[str, Any], data)
        return {k: strip_pickle_markers(v) for k, v in typed_dict.items()}

    if isinstance(data, list):
        typed_list = cast(list[Any], data)
        return [strip_pickle_markers(item) for item in typed_list]

    return data


# ============================================================================
# Serialize / Deserialize
# ============================================================================


def serialize_value(value: Any) -> Any:
    """Encode a value for JSON-compatible cross-activity communication (internal).

    Framework-internal codec. Delegates to core checkpoint encoding which uses
    pickle + base64 for non-JSON-native types (dataclasses, Pydantic models,
    Message, etc.). Not part of the public API.

    Args:
        value: Any Python value (primitive, dataclass, Pydantic model, Message, etc.)

    Returns:
        A JSON-serializable representation with embedded type metadata for reconstruction.
    """
    return encode_checkpoint_value(value)


def deserialize_value(value: Any) -> Any:
    """Decode a value previously encoded with :func:`serialize_value` (internal).

    Framework-internal codec. Delegates to core checkpoint decoding which
    unpickles base64-encoded values and verifies type integrity. Not part of the
    public API: callers only ever hand it values that the framework produced
    itself or that have already passed the :func:`strip_pickle_markers` trust
    boundary, so untrusted markers can never reach ``pickle.loads()`` here.

    Args:
        value: The serialized data (dict with pickle markers, list, or primitive)

    Returns:
        Reconstructed typed object if type metadata found, otherwise original value.
    """
    return decode_checkpoint_value(value)


def deserialize_workflow_output(output: Any) -> Any:
    """Reconstruct the workflow outputs produced by the shared activity.

    Each value an executor yields is encoded with :func:`serialize_value` before
    it reaches the orchestrator, so typed objects (dataclasses, Pydantic models,
    ``AgentResponse``, ...) are stored as checkpoint-marker dicts. This reverses
    that encoding so callers receive the original objects.

    This is the single decode path shared by every host (the in-process
    :class:`DurableWorkflowClient` and the Azure Functions status endpoint) so
    they never diverge in how a completed workflow's output is reconstructed.

    ``output`` must originate from the workflow's own orchestration result
    (trusted durable storage), never from untrusted external input. Markers in
    untrusted input must be neutralized with :func:`strip_pickle_markers` first.

    Args:
        output: The workflow's orchestration result, already JSON-decoded (a list
            of yielded outputs or a single value).

    Returns:
        The output with every checkpoint-encoded value reconstructed; primitives
        and plain JSON structures pass through unchanged.
    """
    return deserialize_value(output)


# ============================================================================
# Workflow Event Serialization (streaming)
# ============================================================================


def _type_key(value_type: type[Any] | None) -> str | None:
    """Format a type as a ``'module:qualname'`` key for :func:`resolve_type`."""
    if value_type is None:
        return None
    return f"{value_type.__module__}:{value_type.__name__}"


def serialize_workflow_event(event: WorkflowEvent[Any]) -> dict[str, Any]:
    """Serialize a :class:`WorkflowEvent` to a JSON-compatible dict.

    Carries a workflow event from the durable activity, through the orchestration
    custom status, to a streaming client. The data payload is encoded with
    :func:`serialize_value` so typed objects survive the round trip;
    :func:`deserialize_workflow_event` reverses it into a ``WorkflowEvent`` so
    callers never handle checkpoint-marker dicts directly.

    Args:
        event: The workflow event to serialize.

    Returns:
        A JSON-serializable dict with the event ``type`` and the fields needed to
        reconstruct it.
    """
    serialized: dict[str, Any] = {"type": event.type}
    if event.executor_id is not None:
        serialized["executor_id"] = event.executor_id
    if event.data is not None:
        serialized["data"] = serialize_value(event.data)
    if event.type == "request_info":
        # request_type is omitted: deserialize_workflow_event rebuilds the event via
        # WorkflowEvent.request_info, which derives it from the data payload.
        serialized["request_id"] = event.request_id
        serialized["source_executor_id"] = event.source_executor_id
        serialized["response_type"] = _type_key(event.response_type)
    return serialized


def deserialize_workflow_event(serialized: dict[str, Any]) -> WorkflowEvent[Any]:
    """Reconstruct a :class:`WorkflowEvent` from :func:`serialize_workflow_event` output.

    ``serialized`` must originate from the workflow's own orchestration custom
    status (trusted durable storage); its encoded payload is decoded with
    :func:`deserialize_value`. Never pass untrusted external input here.

    Args:
        serialized: A dict previously produced by :func:`serialize_workflow_event`,
            optionally augmented with an ``iteration`` key by the orchestrator.

    Returns:
        The reconstructed workflow event with its data payload restored.
    """
    event_type = cast(WorkflowEventType, serialized["type"])
    payload = deserialize_value(serialized["data"]) if "data" in serialized else None

    if event_type == "request_info":
        response_key = serialized.get("response_type")
        response_type = resolve_type(response_key) if response_key else None
        event: WorkflowEvent[Any] = WorkflowEvent.request_info(
            request_id=cast(str, serialized["request_id"]),
            source_executor_id=cast(str, serialized["source_executor_id"]),
            request_data=payload,
            response_type=response_type or object,
        )
    else:
        event = WorkflowEvent(event_type, data=payload, executor_id=serialized.get("executor_id"))

    iteration = serialized.get("iteration")
    if iteration is not None:
        event.iteration = iteration
    return event


# ============================================================================
# HITL Type Reconstruction
# ============================================================================


def reconstruct_to_type(value: Any, target_type: type) -> Any:
    """Reconstruct a value to a known target type.

    Used for HITL responses where external data (without checkpoint type markers)
    needs to be reconstructed to a specific type determined by the response_type hint.

    Tries strategies in order:
    1. Return as-is if already the correct type
    2. deserialize_value (for data with any type markers)
    3. Pydantic model_validate (for Pydantic models)
    4. Dataclass constructor (for dataclasses)

    Args:
        value: The value to reconstruct (typically a dict from JSON)
        target_type: The expected type to reconstruct to

    Returns:
        Reconstructed value if possible, otherwise the original value
    """
    if value is None:
        return None

    with suppress(TypeError):
        if isinstance(value, target_type):
            return value

    if not isinstance(value, dict):
        return value

    # Try decoding if data has pickle markers (from checkpoint encoding).
    # NOTE: This function is general-purpose.  Callers that handle untrusted
    # data (e.g. HITL responses) MUST call strip_pickle_markers() before
    # passing data here.  See _deserialize_hitl_response in orchestrator.py.
    decoded = deserialize_value(value)
    if not isinstance(decoded, dict):
        return decoded

    # Try Pydantic model validation (for unmarked dicts, e.g., external HITL data)
    if issubclass(target_type, BaseModel):
        try:
            return target_type.model_validate(value)
        except Exception:
            logger.debug("Could not validate Pydantic model %s", target_type)
            return value  # type: ignore[return-value]

    # Try dataclass construction (for unmarked dicts, e.g., external HITL data)
    if is_dataclass(target_type) and isinstance(target_type, type):  # type: ignore
        try:
            return target_type(**value)
        except Exception:
            logger.debug("Could not construct dataclass %s", target_type)

    return value  # type: ignore[return-value]
