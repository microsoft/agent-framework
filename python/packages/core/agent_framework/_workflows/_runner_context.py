# Copyright (c) Microsoft. All rights reserved.

import asyncio
import contextlib
import importlib
import logging
import sys
import uuid
from copy import copy
from dataclasses import dataclass, fields, is_dataclass
from typing import Any, Protocol, TypedDict, TypeVar, cast, runtime_checkable

from ._checkpoint import CheckpointStorage, WorkflowCheckpoint
from ._const import DEFAULT_MAX_ITERATIONS
from ._events import WorkflowEvent
from ._shared_state import SharedState

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass
class Message:
    """A class representing a message in the workflow."""

    data: Any
    source_id: str
    target_id: str | None = None

    # OpenTelemetry trace context fields for message propagation
    # These are plural to support fan-in scenarios where multiple messages are aggregated
    trace_contexts: list[dict[str, str]] | None = None  # W3C Trace Context headers from multiple sources
    source_span_ids: list[str] | None = None  # Publishing span IDs for linking from multiple sources

    # Backward compatibility properties
    @property
    def trace_context(self) -> dict[str, str] | None:
        """Get the first trace context for backward compatibility."""
        return self.trace_contexts[0] if self.trace_contexts else None

    @property
    def source_span_id(self) -> str | None:
        """Get the first source span ID for backward compatibility."""
        return self.source_span_ids[0] if self.source_span_ids else None


class CheckpointState(TypedDict):
    messages: dict[str, list[dict[str, Any]]]
    shared_state: dict[str, Any]
    executor_states: dict[str, dict[str, Any]]
    iteration_count: int
    max_iterations: int


# Checkpoint serialization helpers
_MODEL_MARKER = "__af_model__"
_DATACLASS_MARKER = "__af_dataclass__"
_AF_MARKER = "__af__"

# Guards to prevent runaway recursion while encoding arbitrary user data
_MAX_ENCODE_DEPTH = 100
_CYCLE_SENTINEL = "<cycle>"


def _instantiate_checkpoint_dataclass(cls: type[Any], payload: Any) -> Any | None:
    if not isinstance(cls, type):
        logger.debug(f"Checkpoint decoder received non-type dataclass reference: {cls!r}")
        return None

    if isinstance(payload, dict):
        try:
            return cls(**payload)  # type: ignore[arg-type]
        except TypeError as exc:
            logger.debug(f"Checkpoint decoder could not call {cls.__name__}(**payload): {exc}")
        except Exception as exc:
            logger.warning(f"Checkpoint decoder encountered unexpected error calling {cls.__name__}(**payload): {exc}")
        try:
            instance = object.__new__(cls)
        except Exception as exc:
            logger.debug(f"Checkpoint decoder could not allocate {cls.__name__} without __init__: {exc}")
            return None
        for key, val in payload.items():  # type: ignore[attr-defined]
            try:
                setattr(instance, key, val)  # type: ignore[arg-type]
            except Exception as exc:
                logger.debug(f"Checkpoint decoder could not set attribute {key} on {cls.__name__}: {exc}")
        return instance

    try:
        return cls(payload)  # type: ignore[call-arg]
    except TypeError as exc:
        logger.debug(f"Checkpoint decoder could not call {cls.__name__}({payload!r}): {exc}")
    except Exception as exc:
        logger.warning(f"Checkpoint decoder encountered unexpected error calling {cls.__name__}({payload!r}): {exc}")
    return None


def _supports_model_protocol(obj: object) -> bool:
    """Detect objects that expose dictionary serialization hooks."""
    try:
        obj_type: type[Any] = type(obj)
    except Exception:
        return False

    has_to_dict = hasattr(obj, "to_dict") and callable(getattr(obj, "to_dict", None))  # type: ignore[arg-type]
    has_from_dict = hasattr(obj_type, "from_dict") and callable(getattr(obj_type, "from_dict", None))

    has_to_json = hasattr(obj, "to_json") and callable(getattr(obj, "to_json", None))  # type: ignore[arg-type]
    has_from_json = hasattr(obj_type, "from_json") and callable(getattr(obj_type, "from_json", None))

    return (has_to_dict and has_from_dict) or (has_to_json and has_from_json)


def _import_qualified_name(qualname: str) -> type[Any] | None:
    if ":" not in qualname:
        return None
    module_name, class_name = qualname.split(":", 1)
    module = sys.modules.get(module_name)
    if module is None:
        module = importlib.import_module(module_name)
    attr: Any = module
    for part in class_name.split("."):
        attr = getattr(attr, part)
    return attr if isinstance(attr, type) else None


def _encode_checkpoint_value(value: Any) -> Any:
    """Recursively encode values into JSON-serializable structures.

    - Objects exposing to_dict/to_json -> { _MODEL_MARKER: "module:Class", value: encoded }
    - dataclass instances -> { _DATACLASS_MARKER: "module:Class", value: {field: encoded} }
    - dict -> encode keys as str and values recursively
    - list/tuple/set -> list of encoded items
    - other -> returned as-is if already JSON-serializable

    Includes cycle and depth protection to avoid infinite recursion.
    """

    def _enc(v: Any, stack: set[int], depth: int) -> Any:
        # Depth guard
        if depth > _MAX_ENCODE_DEPTH:
            logger.debug(f"Max encode depth reached at depth={depth} for type={type(v)}")
            return "<max_depth>"

        # Structured model handling (objects exposing to_dict/to_json)
        if _supports_model_protocol(v):
            cls = cast(type[Any], type(v))  # type: ignore
            try:
                if hasattr(v, "to_dict") and callable(getattr(v, "to_dict", None)):
                    raw = v.to_dict()  # type: ignore[attr-defined]
                    strategy = "to_dict"
                elif hasattr(v, "to_json") and callable(getattr(v, "to_json", None)):
                    serialized = v.to_json()  # type: ignore[attr-defined]
                    if isinstance(serialized, (bytes, bytearray)):
                        try:
                            serialized = serialized.decode()
                        except Exception:
                            serialized = serialized.decode(errors="replace")
                    raw = serialized
                    strategy = "to_json"
                else:
                    raise AttributeError("Structured model lacks serialization hooks")
                return {
                    _MODEL_MARKER: f"{cls.__module__}:{cls.__name__}",
                    "strategy": strategy,
                    "value": _enc(raw, stack, depth + 1),
                }
            except Exception as exc:  # best-effort fallback
                logger.debug(f"Structured model serialization failed for {cls}: {exc}")
                return str(v)

        # Dataclasses (instances only)
        if is_dataclass(v) and not isinstance(v, type):
            oid = id(v)
            if oid in stack:
                logger.debug("Cycle detected while encoding dataclass instance")
                return _CYCLE_SENTINEL
            stack.add(oid)
            try:
                # type(v) already narrows sufficiently; cast was redundant
                dc_cls: type[Any] = type(v)
                field_values: dict[str, Any] = {}
                for f in fields(v):  # type: ignore[arg-type]
                    field_values[f.name] = _enc(getattr(v, f.name), stack, depth + 1)
                return {
                    _DATACLASS_MARKER: f"{dc_cls.__module__}:{dc_cls.__name__}",
                    "value": field_values,
                }
            finally:
                stack.remove(oid)

        # Collections
        if isinstance(v, dict):
            v_dict = cast("dict[object, object]", v)
            oid = id(v_dict)
            if oid in stack:
                logger.debug("Cycle detected while encoding dict")
                return _CYCLE_SENTINEL
            stack.add(oid)
            try:
                json_dict: dict[str, Any] = {}
                for k_any, val_any in v_dict.items():  # type: ignore[assignment]
                    k_str: str = str(k_any)
                    json_dict[k_str] = _enc(val_any, stack, depth + 1)
                return json_dict
            finally:
                stack.remove(oid)

        if isinstance(v, (list, tuple, set)):
            iterable_v = cast("list[object] | tuple[object, ...] | set[object]", v)
            oid = id(iterable_v)
            if oid in stack:
                logger.debug("Cycle detected while encoding iterable")
                return _CYCLE_SENTINEL
            stack.add(oid)
            try:
                seq: list[object] = list(iterable_v)
                encoded_list: list[Any] = []
                for item in seq:
                    encoded_list.append(_enc(item, stack, depth + 1))
                return encoded_list
            finally:
                stack.remove(oid)

        # Primitives (or unknown objects): ensure JSON-serializable
        if isinstance(v, (str, int, float, bool)) or v is None:
            return v
        # Fallback: stringify unknown objects to avoid JSON serialization errors
        try:
            return str(v)
        except Exception:
            return f"<{type(v).__name__}>"

    return _enc(value, set(), 0)


def _decode_checkpoint_value(value: Any) -> Any:
    """Recursively decode values previously encoded by _encode_checkpoint_value."""
    if isinstance(value, dict):
        value_dict = cast(dict[str, Any], value)  # encoded form always uses string keys
        # Structured model marker handling
        if _MODEL_MARKER in value_dict and "value" in value_dict:
            type_key: str | None = value_dict.get(_MODEL_MARKER)  # type: ignore[assignment]
            strategy: str | None = value_dict.get("strategy")  # type: ignore[assignment]
            raw_encoded: Any = value_dict.get("value")
            decoded_payload = _decode_checkpoint_value(raw_encoded)
            if isinstance(type_key, str):
                try:
                    cls = _import_qualified_name(type_key)
                except Exception as exc:
                    logger.debug(f"Failed to import structured model {type_key}: {exc}")
                    cls = None

                if cls is not None:
                    if strategy == "to_dict" and hasattr(cls, "from_dict"):
                        with contextlib.suppress(Exception):
                            return cls.from_dict(decoded_payload)
                    if strategy == "to_json" and hasattr(cls, "from_json"):
                        if isinstance(decoded_payload, (str, bytes, bytearray)):
                            with contextlib.suppress(Exception):
                                return cls.from_json(decoded_payload)
                        if isinstance(decoded_payload, dict) and hasattr(cls, "from_dict"):
                            with contextlib.suppress(Exception):
                                return cls.from_dict(decoded_payload)
            return decoded_payload
        # Dataclass marker handling
        if _DATACLASS_MARKER in value_dict and "value" in value_dict:
            type_key_dc: str | None = value_dict.get(_DATACLASS_MARKER)  # type: ignore[assignment]
            raw_dc: Any = value_dict.get("value")
            decoded_raw = _decode_checkpoint_value(raw_dc)
            if isinstance(type_key_dc, str):
                try:
                    module_name, class_name = type_key_dc.split(":", 1)
                    module = sys.modules.get(module_name)
                    if module is None:
                        module = importlib.import_module(module_name)
                    cls_dc: Any = getattr(module, class_name)
                    constructed = _instantiate_checkpoint_dataclass(cls_dc, decoded_raw)
                    if constructed is not None:
                        return constructed
                except Exception as exc:
                    logger.debug(f"Failed to decode dataclass {type_key_dc}: {exc}; returning raw value")
            return decoded_raw

        # Regular dict: decode recursively
        decoded: dict[str, Any] = {}
        for k_any, v_any in value_dict.items():
            decoded[k_any] = _decode_checkpoint_value(v_any)
        return decoded
    if isinstance(value, list):
        # After isinstance check, treat value as list[Any] for decoding
        value_list: list[Any] = value  # type: ignore[assignment]
        return [_decode_checkpoint_value(v_any) for v_any in value_list]
    return value


@runtime_checkable
class RunnerContext(Protocol):
    """Protocol for the execution context used by the runner.

    A single context that supports messaging, events, and optional checkpointing.
    If checkpoint storage is not configured, checkpoint methods may raise.
    """

    async def send_message(self, message: Message) -> None:
        """Send a message from the executor to the context.

        Args:
            message: The message to be sent.
        """
        ...

    async def drain_messages(self) -> dict[str, list[Message]]:
        """Drain all messages from the context.

        Returns:
            A dictionary mapping executor IDs to lists of messages.
        """
        ...

    async def has_messages(self) -> bool:
        """Check if there are any messages in the context.

        Returns:
            True if there are messages, False otherwise.
        """
        ...

    async def add_event(self, event: WorkflowEvent) -> None:
        """Add an event to the execution context.

        Args:
            event: The event to be added.
        """
        ...

    async def drain_events(self) -> list[WorkflowEvent]:
        """Drain all events from the context.

        Returns:
            A list of events that were added to the context.
        """
        ...

    async def has_events(self) -> bool:
        """Check if there are any events in the context.

        Returns:
            True if there are events, False otherwise.
        """
        ...

    async def next_event(self) -> WorkflowEvent:  # pragma: no cover - interface only
        """Wait for and return the next event emitted by the workflow run."""
        ...

    async def set_state(self, executor_id: str, state: dict[str, Any]) -> None:
        """Set the state for a specific executor.

        Args:
            executor_id: The ID of the executor whose state is being set.
            state: The state data to be set for the executor.
        """
        ...

    async def get_state(self, executor_id: str) -> dict[str, Any] | None:
        """Get the state for a specific executor.

        Args:
            executor_id: The ID of the executor whose state is being retrieved.

        Returns:
            The state data for the executor, or None if not found.
        """
        ...

    # Checkpointing capability
    def has_checkpointing(self) -> bool:
        """Check if the context supports checkpointing.

        Returns:
            True if checkpointing is supported, False otherwise.
        """
        ...

    # Checkpointing APIs (optional, enabled by storage)
    def set_workflow_id(self, workflow_id: str) -> None:
        """Set the workflow ID for the context."""
        ...

    def reset_for_new_run(self, workflow_shared_state: SharedState | None = None) -> None:
        """Reset the context for a new workflow run."""
        ...

    def set_streaming(self, streaming: bool) -> None:
        """Set whether agents should stream incremental updates.

        Args:
            streaming: True for streaming mode (run_stream), False for non-streaming (run).
        """
        ...

    def is_streaming(self) -> bool:
        """Check if the workflow is in streaming mode.

        Returns:
            True if streaming mode is enabled, False otherwise.
        """
        ...

    async def create_checkpoint(self, metadata: dict[str, Any] | None = None) -> str:
        """Create a checkpoint of the current workflow state.

        Args:
            metadata: Optional metadata to associate with the checkpoint.
        """
        ...

    async def restore_from_checkpoint(self, checkpoint_id: str) -> bool:
        """Restore the context from a checkpoint.

        Args:
            checkpoint_id: The ID of the checkpoint to restore from.

        Returns:
            True if the restoration was successful, False otherwise.
        """
        ...

    async def load_checkpoint(self, checkpoint_id: str) -> WorkflowCheckpoint | None:
        """Load a checkpoint without mutating the current context state."""
        ...

    async def get_checkpoint_state(self) -> CheckpointState:
        """Get the current state of the context suitable for checkpointing."""
        ...

    async def set_checkpoint_state(self, state: CheckpointState) -> None:
        """Set the state of the context from a checkpoint.

        Args:
            state: The state data to set for the context.
        """
        ...


class InProcRunnerContext:
    """In-process execution context for local execution and optional checkpointing."""

    def __init__(self, checkpoint_storage: CheckpointStorage | None = None):
        """Initialize the in-process execution context.

        Args:
            checkpoint_storage: Optional storage to enable checkpointing.
        """
        self._messages: dict[str, list[Message]] = {}
        # Event queue for immediate streaming of events (e.g., AgentRunUpdateEvent)
        self._event_queue: asyncio.Queue[WorkflowEvent] = asyncio.Queue()

        # Checkpointing configuration/state
        self._checkpoint_storage = checkpoint_storage
        self._workflow_id: str | None = None
        self._shared_state: dict[str, Any] = {}
        self._executor_states: dict[str, dict[str, Any]] = {}
        self._iteration_count: int = 0
        self._max_iterations: int = 100

        # Streaming flag - set by workflow's run_stream() vs run()
        self._streaming: bool = False

    async def send_message(self, message: Message) -> None:
        self._messages.setdefault(message.source_id, [])
        self._messages[message.source_id].append(message)

    async def drain_messages(self) -> dict[str, list[Message]]:
        messages = copy(self._messages)
        self._messages.clear()
        return messages

    async def has_messages(self) -> bool:
        return bool(self._messages)

    async def add_event(self, event: WorkflowEvent) -> None:
        """Add an event to the context immediately.

        Events are enqueued so runners can stream them in real time instead of
        waiting for superstep boundaries.
        """
        await self._event_queue.put(event)

    async def drain_events(self) -> list[WorkflowEvent]:
        """Drain all currently queued events without blocking for new ones."""
        events: list[WorkflowEvent] = []
        while True:
            try:
                events.append(self._event_queue.get_nowait())
            except asyncio.QueueEmpty:  # type: ignore[attr-defined]
                break
        return events

    async def has_events(self) -> bool:
        return not self._event_queue.empty()

    async def next_event(self) -> WorkflowEvent:
        """Wait for and return the next event.

        Used by the runner to interleave event emission with ongoing iteration work.
        """
        return await self._event_queue.get()

    async def set_state(self, executor_id: str, state: dict[str, Any]) -> None:
        self._executor_states[executor_id] = state

    async def get_state(self, executor_id: str) -> dict[str, Any] | None:
        return self._executor_states.get(executor_id)

    def has_checkpointing(self) -> bool:
        return self._checkpoint_storage is not None

    def set_workflow_id(self, workflow_id: str) -> None:
        self._workflow_id = workflow_id

    def set_streaming(self, streaming: bool) -> None:
        """Set whether agents should stream incremental updates.

        Args:
            streaming: True for streaming mode (run_stream), False for non-streaming (run).
        """
        self._streaming = streaming

    def is_streaming(self) -> bool:
        """Check if the workflow is in streaming mode.

        Returns:
            True if streaming mode is enabled, False otherwise.
        """
        return self._streaming

    def reset_for_new_run(self, workflow_shared_state: SharedState | None = None) -> None:
        self._messages.clear()
        # Clear any pending events (best-effort) by recreating the queue
        self._event_queue = asyncio.Queue()
        self._shared_state.clear()
        self._executor_states.clear()
        self._iteration_count = 0
        self._streaming = False  # Reset streaming flag
        if workflow_shared_state is not None and hasattr(workflow_shared_state, "_state"):
            workflow_shared_state._state.clear()  # type: ignore[attr-defined]

    async def create_checkpoint(self, metadata: dict[str, Any] | None = None) -> str:
        if not self._checkpoint_storage:
            raise ValueError("Checkpoint storage not configured")

        wf_id = self._workflow_id or str(uuid.uuid4())
        self._workflow_id = wf_id
        state = await self.get_checkpoint_state()

        checkpoint = WorkflowCheckpoint(
            workflow_id=wf_id,
            messages=state["messages"],
            shared_state=state.get("shared_state", {}),
            executor_states=state.get("executor_states", {}),
            iteration_count=state.get("iteration_count", 0),
            max_iterations=state.get("max_iterations", DEFAULT_MAX_ITERATIONS),
            metadata=metadata or {},
        )
        checkpoint_id = await self._checkpoint_storage.save_checkpoint(checkpoint)
        logger.info(f"Created checkpoint {checkpoint_id} for workflow {wf_id}'")
        return checkpoint_id

    async def restore_from_checkpoint(self, checkpoint_id: str) -> bool:
        if not self._checkpoint_storage:
            raise ValueError("Checkpoint storage not configured")

        checkpoint = await self._checkpoint_storage.load_checkpoint(checkpoint_id)
        if not checkpoint:
            logger.error(f"Checkpoint {checkpoint_id} not found")
            return False

        state: CheckpointState = {
            "messages": checkpoint.messages,
            "shared_state": checkpoint.shared_state,
            "executor_states": checkpoint.executor_states,
            "iteration_count": checkpoint.iteration_count,
            "max_iterations": checkpoint.max_iterations,
        }
        await self.set_checkpoint_state(state)
        self._workflow_id = checkpoint.workflow_id
        logger.info(f"Restored state from checkpoint {checkpoint_id}'")
        return True

    async def load_checkpoint(self, checkpoint_id: str) -> WorkflowCheckpoint | None:
        if not self._checkpoint_storage:
            raise ValueError("Checkpoint storage not configured")
        return await self._checkpoint_storage.load_checkpoint(checkpoint_id)

    async def get_checkpoint_state(self) -> CheckpointState:
        serializable_messages: dict[str, list[dict[str, Any]]] = {}
        for source_id, message_list in self._messages.items():
            serializable_messages[source_id] = [
                {
                    "data": _encode_checkpoint_value(msg.data),
                    "source_id": msg.source_id,
                    "target_id": msg.target_id,
                    "trace_contexts": msg.trace_contexts,
                    "source_span_ids": msg.source_span_ids,
                }
                for msg in message_list
            ]
        return {
            "messages": serializable_messages,
            "shared_state": _encode_checkpoint_value(self._shared_state),
            "executor_states": _encode_checkpoint_value(self._executor_states),
            "iteration_count": self._iteration_count,
            "max_iterations": self._max_iterations,
        }

    async def set_checkpoint_state(self, state: CheckpointState) -> None:
        self._messages.clear()
        messages_data = state.get("messages", {})
        for source_id, message_list in messages_data.items():
            self._messages[source_id] = [
                Message(
                    data=_decode_checkpoint_value(msg.get("data")),
                    source_id=msg.get("source_id", ""),
                    target_id=msg.get("target_id"),
                    trace_contexts=msg.get("trace_contexts"),
                    source_span_ids=msg.get("source_span_ids"),
                )
                for msg in message_list
            ]
        # Restore shared_state
        decoded_shared_raw = _decode_checkpoint_value(state.get("shared_state", {}))
        if isinstance(decoded_shared_raw, dict):
            self._shared_state = cast(dict[str, Any], decoded_shared_raw)
        else:  # fallback to empty dict if corrupted
            self._shared_state = {}

        # Restore executor_states ensuring value types are dicts
        decoded_exec_raw = _decode_checkpoint_value(state.get("executor_states", {}))
        if isinstance(decoded_exec_raw, dict):
            typed_exec: dict[str, dict[str, Any]] = {}
            for k_raw, v_raw in decoded_exec_raw.items():  # type: ignore[assignment]
                if isinstance(k_raw, str) and isinstance(v_raw, dict):
                    # Filter inner dict to string keys only (best-effort)
                    inner: dict[str, Any] = {}
                    for inner_k, inner_v in v_raw.items():  # type: ignore[assignment]
                        if isinstance(inner_k, str):
                            inner[inner_k] = inner_v
                    typed_exec[k_raw] = inner
            self._executor_states = typed_exec
        else:
            self._executor_states = {}

        self._iteration_count = state.get("iteration_count", 0)
        self._max_iterations = state.get("max_iterations", 100)
