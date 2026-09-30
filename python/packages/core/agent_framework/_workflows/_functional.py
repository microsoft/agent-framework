# Copyright (c) Microsoft. All rights reserved.

"""Functional workflow API for writing workflows as plain async functions.

.. warning:: Experimental

    This API is experimental and subject to change or removal
    in future versions without notice.

This module provides the ``@workflow`` and ``@step`` decorators that let users
define workflows using native Python control flow (if/else, loops,
``asyncio.gather``) instead of a graph-based topology.

A ``@workflow``-decorated async function receives its input as the first
positional argument.  If the function needs HITL (``request_info``), custom
events, or key/value state, add a :class:`RunContext` parameter — otherwise it
can be omitted.  Inside the workflow, plain ``async`` calls run normally.
Optionally, ``@step``-decorated functions gain caching, per-step checkpointing,
and event emission.  ``@step`` functions may also declare a ``RunContext``
parameter to access HITL and state APIs directly.

Key public symbols:

* :func:`workflow` / :class:`FunctionalWorkflowDefinition` — decorator and
  stateless definition.
* :class:`FunctionalWorkflow` — stateful runtime created by
  :meth:`FunctionalWorkflowDefinition.build`.
* :func:`step` / :class:`StepWrapper` — optional step decorator.
* :class:`RunContext` — execution context injected into workflow and step
  functions.
* :func:`get_run_context` — retrieve the active ``RunContext`` from anywhere
  inside a running workflow.
* :class:`FunctionalWorkflowAgent` — agent adapter returned by
  :meth:`FunctionalWorkflow.as_agent`.
"""

from __future__ import annotations

# pyright: reportPrivateUsage=false
# Classes in this module (RunContext, StepWrapper, FunctionalWorkflow) form a
# cohesive unit and intentionally access each other's underscore-prefixed members.
import asyncio
import functools
import hashlib
import inspect
import json
import logging
import math
import typing
from collections.abc import AsyncIterable, Awaitable, Callable, Coroutine, Mapping, Sequence
from contextvars import Context, ContextVar
from copy import deepcopy
from types import CodeType
from typing import Any, Generic, Literal, TypeVar, overload
from weakref import WeakSet

from .._agents import BaseAgent
from .._feature_stage import ExperimentalFeature, experimental
from .._serialization import make_json_safe
from .._types import AgentResponse, AgentResponseUpdate, ResponseStream
from ..observability import (
    OtelAttr,
    _activate_span,
    capture_exception,
    start_workflow_span,
)
from ._checkpoint import CheckpointStorage, WorkflowCheckpoint
from ._events import (
    WorkflowErrorDetails,
    WorkflowEvent,
    WorkflowRunState,
    _framework_event,
)
from ._workflow import WorkflowRunResult, _coerce_request_info_response

logger = logging.getLogger(__name__)

R = TypeVar("R")

_STEP_CACHE_KEY_V2_PREFIX = "v2::"
_UNSUPPORTED_STEP_IDENTITY = object()
_step_wrapper_identity_registry: dict[tuple[str, str], WeakSet[Any]] = {}

# ContextVar holding the active RunContext during workflow execution.
# ContextVar is per-asyncio-Task, so concurrent workflows each get their own context.
_active_run_ctx: ContextVar[RunContext | None] = ContextVar("_active_run_ctx", default=None)
_workflow_task_factory_states: dict[asyncio.AbstractEventLoop, _WorkflowTaskFactoryState] = {}


class _WorkflowTaskFactoryState:
    """Delegate a loop task factory while recording tasks created by active workflows."""

    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop
        self.original_factory = loop.get_task_factory()
        self.active_runs = 0
        self.factory = self._create_task

    def _create_task(
        self,
        loop: asyncio.AbstractEventLoop,
        coro: Coroutine[Any, Any, Any],
        **kwargs: Any,
    ) -> asyncio.Future[Any]:
        if self.original_factory is None:
            task = asyncio.Task(coro, loop=loop, **kwargs)
        else:
            task = self.original_factory(loop, coro, **kwargs)

        task_context = kwargs.get("context")
        ctx = task_context.get(_active_run_ctx) if isinstance(task_context, Context) else _active_run_ctx.get()
        if ctx is not None:
            ctx._workflow_tasks.add(task)
        return task


def _track_workflow_tasks() -> Callable[[], None]:
    loop = asyncio.get_running_loop()
    state = _workflow_task_factory_states.get(loop)
    if state is None or loop.get_task_factory() is not state.factory:
        state = _WorkflowTaskFactoryState(loop)
        _workflow_task_factory_states[loop] = state
        loop.set_task_factory(state.factory)
    state.active_runs += 1
    released = False

    def _release() -> None:
        nonlocal released
        if released:
            return
        released = True
        state.active_runs -= 1
        if state.active_runs == 0:
            if loop.get_task_factory() is state.factory:
                loop.set_task_factory(state.original_factory)
            if _workflow_task_factory_states.get(loop) is state:
                del _workflow_task_factory_states[loop]

    return _release


def _canonicalize_step_identity_value(value: Any, seen: set[int] | None = None) -> Any:
    """Return a type-preserving JSON value, or a sentinel for unsupported input."""
    if seen is None:
        seen = set()
    if value is None:
        return ["none"]
    if type(value) is bool:
        return ["bool", value]
    if type(value) is int:
        return ["int", value]
    if type(value) is float:
        if not math.isfinite(value):
            return _UNSUPPORTED_STEP_IDENTITY
        return ["float", value.hex()]
    if type(value) is complex:
        if not math.isfinite(value.real) or not math.isfinite(value.imag):
            return _UNSUPPORTED_STEP_IDENTITY
        return ["complex", value.real.hex(), value.imag.hex()]
    if type(value) is str:
        return ["str", value]
    if type(value) is bytes:
        return ["bytes", value.hex()]
    if type(value) is list:
        list_value = typing.cast(list[Any], value)
        value_id = id(list_value)
        if value_id in seen:
            return _UNSUPPORTED_STEP_IDENTITY
        seen.add(value_id)
        list_items: list[Any] = []
        try:
            for item in list_value:
                canonical = _canonicalize_step_identity_value(item, seen)
                if canonical is _UNSUPPORTED_STEP_IDENTITY:
                    return _UNSUPPORTED_STEP_IDENTITY
                list_items.append(canonical)
            return ["list", list_items]
        finally:
            seen.remove(value_id)
    if type(value) is tuple:
        tuple_value = typing.cast(tuple[Any, ...], value)
        value_id = id(tuple_value)
        if value_id in seen:
            return _UNSUPPORTED_STEP_IDENTITY
        seen.add(value_id)
        tuple_items: list[Any] = []
        try:
            for item in tuple_value:
                canonical = _canonicalize_step_identity_value(item, seen)
                if canonical is _UNSUPPORTED_STEP_IDENTITY:
                    return _UNSUPPORTED_STEP_IDENTITY
                tuple_items.append(canonical)
            return ["tuple", tuple_items]
        finally:
            seen.remove(value_id)
    if isinstance(value, Mapping):
        mapping = typing.cast(Mapping[Any, Any], value)
        value_id = id(mapping)
        if value_id in seen:
            return _UNSUPPORTED_STEP_IDENTITY
        seen.add(value_id)
        mapping_items: list[Any] = []
        try:
            for key, item in mapping.items():
                if type(key) is not str:
                    return _UNSUPPORTED_STEP_IDENTITY
                canonical = _canonicalize_step_identity_value(item, seen)
                if canonical is _UNSUPPORTED_STEP_IDENTITY:
                    return _UNSUPPORTED_STEP_IDENTITY
                mapping_items.append([key, canonical])
            mapping_type = f"{type(mapping).__module__}.{type(mapping).__qualname__}"
            return ["mapping", mapping_type, mapping_items]
        finally:
            seen.remove(value_id)
    if type(value) is frozenset:
        frozenset_items: list[Any] = []
        for item in typing.cast(frozenset[Any], value):
            canonical = _canonicalize_step_identity_value(item, seen)
            if canonical is _UNSUPPORTED_STEP_IDENTITY:
                return _UNSUPPORTED_STEP_IDENTITY
            frozenset_items.append(canonical)
        frozenset_items.sort(key=lambda item: json.dumps(item, sort_keys=True, separators=(",", ":")))
        return ["frozenset", frozenset_items]
    return _UNSUPPORTED_STEP_IDENTITY


def _hash_step_identity(value: Any) -> str | None:
    canonical = _canonicalize_step_identity_value(value)
    if canonical is _UNSUPPORTED_STEP_IDENTITY:
        return None
    encoded = json.dumps(canonical, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _canonicalize_code_value(value: Any) -> Any:
    if isinstance(value, CodeType):
        return ["code", _get_code_identity_payload(value)]
    if value is None or type(value) in (bool, int, str):
        return [type(value).__name__, value]
    if type(value) is float:
        return ["float", value.hex()]
    if type(value) is complex:
        return ["complex", value.real.hex(), value.imag.hex()]
    if type(value) is bytes:
        return ["bytes", value.hex()]
    if type(value) is tuple:
        tuple_value = typing.cast(tuple[Any, ...], value)
        return ["tuple", [_canonicalize_code_value(item) for item in tuple_value]]
    if type(value) is frozenset:
        frozenset_value = typing.cast(frozenset[Any], value)
        items = [_canonicalize_code_value(item) for item in frozenset_value]
        items.sort(key=lambda item: json.dumps(item, sort_keys=True, separators=(",", ":")))
        return ["frozenset", items]
    if value is Ellipsis:
        return ["ellipsis"]
    return ["unsupported", type(value).__module__, type(value).__qualname__]


def _get_code_identity_payload(code: CodeType) -> dict[str, Any]:
    return {
        "argcount": code.co_argcount,
        "posonlyargcount": code.co_posonlyargcount,
        "kwonlyargcount": code.co_kwonlyargcount,
        "flags": code.co_flags,
        "code": code.co_code.hex(),
        "consts": [_canonicalize_code_value(item) for item in code.co_consts],
        "names": list(code.co_names),
        "varnames": list(code.co_varnames),
        "freevars": list(code.co_freevars),
        "cellvars": list(code.co_cellvars),
    }


def _canonicalize_wrapper_state(value: Any) -> tuple[Any, bool]:
    canonical = _canonicalize_step_identity_value(value)
    if canonical is _UNSUPPORTED_STEP_IDENTITY:
        return (["opaque", type(value).__module__, type(value).__qualname__], False)
    return (canonical, _is_immutable_wrapper_state(value))


def _is_immutable_wrapper_state(value: Any) -> bool:
    if value is None or type(value) in (bool, int, float, complex, str, bytes):
        return True
    if type(value) is tuple:
        return all(_is_immutable_wrapper_state(item) for item in typing.cast(tuple[Any, ...], value))
    if type(value) is frozenset:
        return all(_is_immutable_wrapper_state(item) for item in typing.cast(frozenset[Any], value))
    return False


def _get_step_wrapper_defaults_state(func: Callable[..., Awaitable[Any]]) -> tuple[dict[str, Any], bool]:
    defaults, defaults_are_durable = _canonicalize_wrapper_state(func.__defaults__ or ())
    raw_kwdefaults = func.__kwdefaults__ or {}
    kwdefaults, _ = _canonicalize_wrapper_state(raw_kwdefaults)
    kwdefaults_are_durable = all(_is_immutable_wrapper_state(value) for value in raw_kwdefaults.values())
    return (
        {
            "defaults": defaults,
            "kwdefaults": kwdefaults,
        },
        defaults_are_durable and kwdefaults_are_durable,
    )


def _get_step_wrapper_identity(func: Callable[..., Awaitable[Any]]) -> tuple[str, bool]:
    code = getattr(func, "__code__", None)
    defaults_state, defaults_are_durable = _get_step_wrapper_defaults_state(func)
    closure_items: list[Any] = []
    closure_is_durable = True
    if code is not None and func.__closure__ is not None:
        for name, cell in zip(code.co_freevars, func.__closure__):
            try:
                value = cell.cell_contents
            except ValueError:
                closure_items.append([name, ["empty"]])
                closure_is_durable = False
                continue
            canonical, is_durable = _canonicalize_wrapper_state(value)
            closure_items.append([name, canonical])
            closure_is_durable = closure_is_durable and is_durable

    payload = {
        "module": func.__module__,
        "qualname": func.__qualname__,
        "firstlineno": code.co_firstlineno if code is not None else None,
        "code": _get_code_identity_payload(code) if code is not None else None,
        **defaults_state,
        "closure": closure_items,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return (
        hashlib.sha256(encoded.encode("utf-8")).hexdigest(),
        defaults_are_durable and closure_is_durable,
    )


def _encode_step_cache_key(
    kind: Literal["auto", "explicit"],
    step_name: str,
    wrapper_identity: str,
    identity: str,
    occurrence: int | None = None,
) -> str:
    payload: list[str | int] = [kind, step_name, wrapper_identity, identity]
    if kind == "auto":
        if occurrence is None:
            raise ValueError("Automatic step cache keys require an occurrence index.")
        payload.append(occurrence)
    return f"{_STEP_CACHE_KEY_V2_PREFIX}{json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}"


def _decode_versioned_step_cache_key(
    key: str,
) -> tuple[Literal["auto", "explicit"], str, str, str, int | None] | None:
    if not key.startswith(_STEP_CACHE_KEY_V2_PREFIX):
        return None
    try:
        raw_payload: object = json.loads(key.removeprefix(_STEP_CACHE_KEY_V2_PREFIX))
    except json.JSONDecodeError:
        return None
    if not isinstance(raw_payload, list) or not raw_payload:
        return None
    payload = typing.cast(list[Any], raw_payload)
    kind = payload[0]
    if (
        kind == "auto"
        and len(payload) == 5
        and all(isinstance(item, str) for item in payload[1:4])
        and isinstance(payload[4], int)
        and payload[4] >= 0
    ):
        return ("auto", payload[1], payload[2], payload[3], payload[4])
    if kind == "explicit" and len(payload) == 4 and all(isinstance(item, str) for item in payload[1:]):
        return ("explicit", payload[1], payload[2], payload[3], None)
    raise ValueError("Invalid versioned step cache key.")


def _validate_step_cache_key(key: Any) -> str:
    if not isinstance(key, str):
        raise TypeError("Step cache keys must be strings.")

    if _decode_versioned_step_cache_key(key) is not None:
        return key

    name, idx_str = key.rsplit("::", 1)
    if not name or int(idx_str) < 0:
        raise ValueError("Invalid legacy step cache key.")
    return key


def _snapshot_step_cache_value(value: Any) -> Any:
    try:
        return deepcopy(value)
    except Exception as exc:
        raise ValueError(
            "@step results must support deepcopy so cached replay cannot be changed by downstream mutation."
        ) from exc


@experimental(feature_id=ExperimentalFeature.FUNCTIONAL_WORKFLOWS)
def get_run_context() -> RunContext | None:
    """Return the active :class:`RunContext`, or ``None`` if not inside a ``@workflow``.

    This is useful inside ``@step`` functions (or any code called from a
    workflow) that need access to HITL, state, or event APIs without
    requiring a ``RunContext`` parameter.
    """
    return _active_run_ctx.get()


# ---------------------------------------------------------------------------
# Internal exception for HITL interruption
# ---------------------------------------------------------------------------


class WorkflowInterrupted(BaseException):
    """Internal: raised when request_info() is called during initial execution.

    Inherits from ``BaseException`` (not ``Exception``) so that user code
    with ``except Exception:`` handlers inside a ``@workflow`` function does
    not accidentally intercept the HITL interruption signal.
    """

    def __init__(self, request_id: str, request_data: Any, response_type: type) -> None:
        self.request_id = request_id
        self.request_data = request_data
        self.response_type = response_type
        super().__init__(f"Workflow interrupted by request_info (request_id={request_id})")


# ---------------------------------------------------------------------------
# RunContext
# ---------------------------------------------------------------------------


@experimental(feature_id=ExperimentalFeature.FUNCTIONAL_WORKFLOWS)
class RunContext:
    """Opt-in handle for workflow-only features inside a ``@workflow`` function.

    Use ``RunContext`` when a workflow function needs one of the following,
    otherwise omit it entirely for a cleaner signature:

    * Human-in-the-loop: :meth:`request_info` pauses the workflow until a
      response is supplied, then resumes with that value.
    * Custom events: :meth:`add_event` emits events into the run stream
      (useful for progress reporting or tracing).
    * Workflow-scoped key/value state: :meth:`get_state` / :meth:`set_state`
      persist values across a run and survive checkpoints.

    The context is injected automatically. Declare it either by parameter
    name (``ctx``) or by type annotation (``: RunContext``); both work.

    Args:
        workflow_name: Identifier for the enclosing workflow, used when
            generating events and checkpoint metadata.
        streaming: Whether the current run was started with ``stream=True``.
        run_kwargs: Extra keyword arguments forwarded from
            :meth:`FunctionalWorkflow.run`.

    Examples:

        .. code-block:: python

            # Simple workflow: no context parameter needed.
            @workflow
            async def my_pipeline(data: str) -> str:
                return await some_step(data)


            # HITL workflow: request a response from a human reviewer.
            @workflow
            async def hitl_pipeline(data: str, ctx: RunContext) -> str:
                feedback = await ctx.request_info({"draft": data}, response_type=str)
                return feedback


            # RunContext also works inside @step functions.
            @step
            async def review_step(doc: str, ctx: RunContext) -> str:
                feedback = await ctx.request_info({"draft": doc}, response_type=str)
                return feedback
    """

    def __init__(
        self,
        workflow_name: str,
        *,
        streaming: bool = False,
        run_kwargs: dict[str, Any] | None = None,
    ) -> None:
        self._workflow_name = workflow_name
        self._streaming = streaming
        self._run_kwargs = run_kwargs or {}

        # Event accumulator
        self._events: list[WorkflowEvent[Any]] = []

        # Step result cache. Keys are already checkpoint-safe strings so result
        # and metadata maps cannot drift during serialization.
        self._step_cache: dict[str, Any] = {}
        # Cached step metadata used to keep auto-generated request_info IDs in sync on bypass.
        self._step_cache_auto_request_info_counts: dict[str, int] = {}
        # Legacy per-step call counters retained for old checkpoint compatibility.
        self._step_call_counters: dict[str, int] = {}
        # Per-identity counters keep repeated automatic invocations distinct.
        self._step_identity_counters: dict[tuple[str, str, str], int] = {}
        # Explicit replay keys identify exactly one logical invocation per run.
        self._used_explicit_step_cache_keys: set[str] = set()
        # Tasks created while this workflow context is active.
        self._workflow_tasks: set[asyncio.Future[Any]] = set()
        # The task executing the workflow body; gather/task-group children differ from this task.
        self._root_task: asyncio.Task[Any] | None = None
        # Deterministic call counter for auto-generated request_info IDs
        self._auto_request_info_index: int = 0

        # HITL responses (set via _set_responses before replay)
        self._responses: dict[str, Any] = {}
        # Pending request_info events (for checkpointing)
        self._pending_requests: dict[str, WorkflowEvent[Any]] = {}

        # User state (simple dict)
        self._state: dict[str, Any] = {}

        # Callback invoked after each step completes (set by FunctionalWorkflow)
        self._on_step_completed: Callable[[], Awaitable[None]] | None = None

    # ------------------------------------------------------------------
    # Public API (for @workflow functions)
    # ------------------------------------------------------------------

    async def request_info(
        self,
        request_data: Any,
        response_type: type,
        *,
        request_id: str | None = None,
    ) -> Any:
        """Request external information (human-in-the-loop).

        On first execution this suspends the workflow by raising an internal
        ``WorkflowInterrupted`` signal (caught by the framework, never exposed
        to user code).  The caller receives a ``WorkflowRunResult`` (or a
        ``ResponseStream`` when ``stream=True``) whose
        :meth:`~WorkflowRunResult.get_request_info_events` contains the pending
        request.  When the workflow is resumed with
        ``run(responses={request_id: value})``, the same function re-executes
        and ``request_info`` returns the provided *value* directly.

        Args:
            request_data: Arbitrary payload describing what information is
                needed (e.g. a Pydantic model, dict, or string prompt).
            response_type: The expected Python type of the response value.
            request_id: Optional stable identifier for this request.  If
                omitted, a deterministic identifier is derived from the call
                order (``auto::<index>``) so that resume works without the
                caller needing to echo back an explicit ID.

        Returns:
            The response value supplied during replay.  ``None`` is allowed
            but triggers a warning — prefer a sentinel value when the
            absence of data is meaningful.

        Raises:
            WorkflowInterrupted: Raised internally on initial execution
                (not visible to workflow authors).
        """
        if request_id is None:
            # Deterministic id; same determinism contract as @step caching.
            rid = f"auto::{self._auto_request_info_index}"
            self._auto_request_info_index += 1
        else:
            rid = request_id

        found, value = self._get_response(rid)
        if found:
            self._pending_requests.pop(rid, None)
            # Functional workflows intentionally allow None responses; _set_responses logs a warning for them.
            if value is not None:
                value = _coerce_request_info_response(value, response_type, rid)
            return value

        # No response — emit event and interrupt
        event = WorkflowEvent.request_info(
            request_id=rid,
            source_executor_id=self._workflow_name,
            request_data=request_data,
            response_type=response_type,
        )
        await self.add_event(event)
        self._pending_requests[rid] = event
        raise WorkflowInterrupted(rid, request_data, response_type)

    async def add_event(self, event: WorkflowEvent[Any]) -> None:
        """Add a custom event to the workflow event stream.

        Use this to inject application-specific events alongside the
        framework-generated lifecycle events.

        Args:
            event: The workflow event to append.
        """
        self._events.append(event)

    def get_state(self, key: str, default: Any = None) -> Any:
        """Retrieve a value from the workflow's key/value state.

        State values are persisted across HITL interruptions and are included
        in checkpoints when checkpoint storage is configured.

        Args:
            key: The state key to look up.
            default: Value returned when *key* is absent.

        Returns:
            The stored value, or *default* if the key does not exist.
        """
        return self._state.get(key, default)

    def set_state(self, key: str, value: Any) -> None:
        """Store a value in the workflow's key/value state.

        Args:
            key: The state key.  Must not start with ``_`` — framework
                bookkeeping (e.g. ``_step_cache``, ``_original_message``) uses
                the underscore prefix and user keys in that namespace are
                silently clobbered by checkpoint save and dropped on
                checkpoint restore.  Use names without a leading underscore
                for user state.
            value: The value to store.  Must be JSON-serializable if
                checkpoint storage is used.

        Raises:
            ValueError: If *key* begins with ``_`` (reserved for framework
                bookkeeping).
        """
        if key.startswith("_"):
            raise ValueError(
                f"State key {key!r} starts with '_', which is reserved for "
                f"framework bookkeeping (e.g. '_step_cache', '_original_message') "
                f"and would be silently dropped on checkpoint restore.  Use a "
                f"non-underscore-prefixed key for user state."
            )
        self._state[key] = value

    def is_streaming(self) -> bool:
        """Return whether the current run was started with ``stream=True``.

        Returns:
            ``True`` if the workflow is running in streaming mode.
        """
        return self._streaming

    # ------------------------------------------------------------------
    # Internal API (for StepWrapper and FunctionalWorkflow)
    # ------------------------------------------------------------------

    def _get_events(self) -> list[WorkflowEvent[Any]]:
        return list(self._events)

    def _get_legacy_step_cache_key(self, step_name: str) -> str:
        idx = self._step_call_counters.get(step_name, 0)
        self._step_call_counters[step_name] = idx + 1
        return f"{step_name}::{idx}"

    def _get_automatic_step_cache_key(self, step_name: str, wrapper_identity: str, identity: str) -> str:
        counter_key = (step_name, wrapper_identity, identity)
        occurrence = self._step_identity_counters.get(counter_key, 0)
        self._step_identity_counters[counter_key] = occurrence + 1
        return _encode_step_cache_key("auto", step_name, wrapper_identity, identity, occurrence)

    def _get_explicit_step_cache_key(self, step_name: str, wrapper_identity: str, identity: str) -> str:
        key = _encode_step_cache_key("explicit", step_name, wrapper_identity, identity)
        if key in self._used_explicit_step_cache_keys:
            raise ValueError(
                f"@step '{step_name}' produced duplicate replay_key values in one workflow run. "
                "Each explicit replay key must identify exactly one logical invocation."
            )
        self._used_explicit_step_cache_keys.add(key)
        return key

    def _is_concurrent_execution(self) -> bool:
        current_task = asyncio.current_task()
        if self._root_task is None or current_task is None:
            return False
        if current_task is not self._root_task:
            return True
        return any(task is not current_task and not task.done() for task in self._workflow_tasks)

    def _get_cached_result(self, key: str) -> tuple[bool, Any]:
        if key in self._step_cache:
            return True, self._step_cache[key]
        return False, None

    def _has_incompatible_versioned_cache_entry(self, key: str) -> bool:
        current = _decode_versioned_step_cache_key(key)
        if current is None:
            return False
        current_kind, current_step, current_wrapper, _current_identity, current_occurrence = current
        for cached_key in self._step_cache:
            cached = _decode_versioned_step_cache_key(cached_key)
            if cached is None:
                continue
            cached_kind, cached_step, cached_wrapper, _cached_identity, cached_occurrence = cached
            if (
                cached_kind == current_kind
                and cached_step == current_step
                and cached_occurrence == current_occurrence
                and cached_wrapper != current_wrapper
            ):
                live_wrappers = _step_wrapper_identity_registry.get((cached_step, cached_wrapper))
                if not live_wrappers:
                    return True
        return False

    def _set_cached_result(self, key: str, value: Any) -> None:
        self._step_cache[key] = value

    def _set_cached_step_auto_request_info_count(self, key: str, count: int) -> None:
        self._step_cache_auto_request_info_counts[key] = count

    def _advance_auto_request_info_index_for_cached_step(self, key: str) -> None:
        self._auto_request_info_index += self._step_cache_auto_request_info_counts.get(key, 0)

    def _set_responses(self, responses: dict[str, Any]) -> None:
        for rid, value in responses.items():
            if value is None:
                logger.warning(
                    "Response for request_id=%r is None. If this is intentional, "
                    "consider using a sentinel value instead.",
                    rid,
                )
        self._responses = dict(responses)
        # Remove resolved requests from the pending set so downstream
        # checkpoints don't re-serialize them as still-pending.
        for rid in responses:
            self._pending_requests.pop(rid, None)

    def _get_response(self, request_id: str) -> tuple[bool, Any]:
        """Look up a HITL response by *request_id*.

        Returns:
            A ``(found, value)`` tuple.  When *found* is ``True``, *value* is
            the caller-supplied response (which **may be** ``None`` — a warning
            is logged by :meth:`_set_responses` in that case).  When *found* is
            ``False``, *value* is always ``None`` and simply means no response
            has been provided yet.
        """
        if request_id in self._responses:
            return True, self._responses[request_id]
        return False, None

    def _export_step_cache(self) -> dict[str, Any]:
        """Serialize the step cache for checkpointing."""
        return dict(self._step_cache)

    def _export_step_cache_auto_request_info_counts(self) -> dict[str, int]:
        """Serialize per-step auto request_info counts for checkpointing."""
        return dict(self._step_cache_auto_request_info_counts)

    def _import_step_cache(self, data: dict[str, Any]) -> None:
        """Restore step cache from checkpoint data."""
        self._step_cache = {}
        for k, v in data.items():
            try:
                self._step_cache[_validate_step_cache_key(k)] = v
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                raise ValueError(
                    f"Corrupted step cache entry in checkpoint: key={k!r}. "
                    f"The checkpoint may be from an incompatible version or corrupted. "
                    f"Original error: {exc}"
                ) from exc

    def _import_step_cache_auto_request_info_counts(self, data: dict[str, Any]) -> None:
        """Restore per-step auto request_info counts from checkpoint data."""
        self._step_cache_auto_request_info_counts = {}
        for k, v in data.items():
            try:
                self._step_cache_auto_request_info_counts[_validate_step_cache_key(k)] = int(v)
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                raise ValueError(
                    f"Corrupted step cache request_info metadata in checkpoint: key={k!r}, value={v!r}. "
                    f"The checkpoint may be from an incompatible version or corrupted. "
                    f"Original error: {exc}"
                ) from exc


# ---------------------------------------------------------------------------
# StepWrapper
# ---------------------------------------------------------------------------


@experimental(feature_id=ExperimentalFeature.FUNCTIONAL_WORKFLOWS)
class StepWrapper(Generic[R]):
    """Wrapper returned by the ``@step`` decorator.

    When called inside a running ``@workflow`` function, the wrapper
    intercepts execution to provide:

    * **Caching** — results use a stable identity derived from bound,
      canonical arguments so HITL replay and checkpoint restore skip the
      matching logical invocation even if concurrent scheduling changes.
      Use ``replay_key`` for opaque arguments or concurrent calls whose
      identical arguments do not imply interchangeable results. On cache
      hit a single ``executor_bypassed`` event is emitted instead of the
      normal ``executor_invoked`` / ``executor_completed`` pair.
    * **Event emission** — ``executor_invoked`` / ``executor_completed`` /
      ``executor_failed`` events are emitted for observability.
    * **RunContext injection** — if the step function declares a parameter
      annotated as :class:`RunContext` (or named ``ctx``), the active
      context is automatically injected, giving step functions access to
      HITL, state, and event APIs.
    * **Per-step checkpointing** — a checkpoint is saved after each live
      execution when checkpoint storage is configured.

    Outside a workflow the wrapper is transparent: it delegates directly to
    the original function, making decorated functions fully testable in
    isolation.

    Automatic replay identity supports ``None``, booleans, integers, finite
    floats/complex numbers, strings, bytes, lists, tuples, frozensets, and
    string-key mappings containing those values. Concurrent calls with the
    same automatic identity must produce interchangeable results; use
    distinct ``replay_key`` values otherwise.
    Opaque captured defaults/closure state, and multiple wrappers whose
    canonical source and captured state are identical, require ``replay_key``
    for concurrent use.
    Legacy order-based checkpoints remain replayable sequentially, but a
    concurrent legacy cache hit raises instead of risking a mismatched result.

    Args:
        func: The async function to wrap.
        name: Optional display name.  Defaults to ``func.__name__``.
        replay_key: Optional callback returning a stable, unique, non-empty
            string for each logical invocation. The callback receives the
            original user arguments and is not called outside a workflow.

    Raises:
        TypeError: If *func* is not an async (coroutine) function.
        ValueError: If replay identity is unavailable or invalid for a
            concurrent invocation, or a legacy checkpoint cannot be replayed
            safely under concurrency.
    """

    def __init__(
        self,
        func: Callable[..., Awaitable[R]],
        *,
        name: str | None = None,
        replay_key: Callable[..., str] | None = None,
    ) -> None:
        if not inspect.iscoroutinefunction(func):
            raise TypeError(
                f"@step can only decorate async functions, but '{func.__name__}' is not a coroutine function."
            )
        self._func = func
        self.name: str = name or func.__name__
        self._signature = inspect.signature(func)
        self._wrapper_identity, self._wrapper_identity_is_durable = _get_step_wrapper_identity(func)
        defaults_state, self._wrapper_defaults_are_durable = _get_step_wrapper_defaults_state(func)
        defaults_encoded = json.dumps(defaults_state, sort_keys=True, separators=(",", ":"))
        self._wrapper_defaults_identity = hashlib.sha256(defaults_encoded.encode("utf-8")).hexdigest()
        if _active_run_ctx.get() is not None:
            self._wrapper_identity_is_durable = False
        self._wrapper_registry_key = (self.name, self._wrapper_identity)
        matching_wrappers = _step_wrapper_identity_registry.setdefault(self._wrapper_registry_key, WeakSet())
        matching_wrappers.add(self)
        self._replay_key = replay_key
        functools.update_wrapper(self, func)

        # Detect RunContext parameter for auto-injection inside workflows
        self._ctx_param_name: str | None = None
        try:
            hints = typing.get_type_hints(func)
        except Exception:
            hints = {}
        for param_name, param in self._signature.parameters.items():
            if param.kind not in (
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                inspect.Parameter.KEYWORD_ONLY,
            ):
                continue
            resolved = hints.get(param_name, param.annotation)
            if resolved is RunContext or param_name == "ctx":
                self._ctx_param_name = param_name
                break

        identity_parameters = [
            param for param in self._signature.parameters.values() if param.name != self._ctx_param_name
        ]
        self._identity_signature = self._signature.replace(parameters=identity_parameters)

    def _get_replay_identity(
        self,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> tuple[Literal["auto", "explicit"], str] | None:
        if self._wrapper_defaults_are_durable:
            current_defaults, current_defaults_are_durable = _get_step_wrapper_defaults_state(self._func)
            current_encoded = json.dumps(current_defaults, sort_keys=True, separators=(",", ":"))
            current_identity = hashlib.sha256(current_encoded.encode("utf-8")).hexdigest()
            if not current_defaults_are_durable or current_identity != self._wrapper_defaults_identity:
                raise ValueError(
                    f"@step '{self.name}' defaults changed after decoration. "
                    "Create a new workflow definition or provide a versioned replay_key."
                )

        if self._replay_key is not None:
            explicit_key = self._replay_key(*args, **kwargs)
            if not isinstance(explicit_key, str) or not explicit_key:
                raise ValueError(f"@step '{self.name}' replay_key must return a non-empty string.")
            return ("explicit", hashlib.sha256(explicit_key.encode("utf-8")).hexdigest())

        matching_wrappers = _step_wrapper_identity_registry.get(self._wrapper_registry_key)
        if matching_wrappers is not None and len(matching_wrappers) > 1:
            raise ValueError(
                f"@step '{self.name}' was generated from a function definition used by multiple wrappers. "
                "Provide replay_key so each logical invocation has an explicit durable identity."
            )

        if not self._wrapper_identity_is_durable:
            return None

        identity_kwargs = kwargs
        if self._ctx_param_name is not None and self._ctx_param_name in kwargs:
            identity_kwargs = dict(kwargs)
            identity_kwargs.pop(self._ctx_param_name)
        bound = self._identity_signature.bind(*args, **identity_kwargs)
        bound.apply_defaults()
        identity = _hash_step_identity(bound.arguments)
        if identity is None:
            return None
        return ("auto", identity)

    async def _return_cached_result(self, ctx: RunContext, cache_key: str, cached: Any) -> R:
        ctx._advance_auto_request_info_index_for_cached_step(cache_key)
        replayed = _snapshot_step_cache_value(cached)
        await ctx.add_event(WorkflowEvent.executor_bypassed(self.name, _snapshot_step_cache_value(replayed)))
        return replayed

    def _build_call_args_with_ctx(
        self,
        ctx: RunContext,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> tuple[tuple[Any, ...], dict[str, Any]]:
        """Inject RunContext without consuming a user positional argument."""
        if self._ctx_param_name is None or self._ctx_param_name in kwargs:
            return args, dict(kwargs)

        call_args: list[Any] = []
        call_kwargs = dict(kwargs)
        arg_index = 0

        for param in self._signature.parameters.values():
            if param.name == self._ctx_param_name:
                if param.kind == inspect.Parameter.KEYWORD_ONLY:
                    call_kwargs[param.name] = ctx
                else:
                    call_args.append(ctx)
                continue

            if param.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD):
                if arg_index < len(args):
                    call_args.append(args[arg_index])
                    arg_index += 1
            elif param.kind == inspect.Parameter.VAR_POSITIONAL:
                call_args.extend(args[arg_index:])
                arg_index = len(args)

        if arg_index < len(args):
            call_args.extend(args[arg_index:])

        return tuple(call_args), call_kwargs

    async def __call__(self, *args: Any, **kwargs: Any) -> R:
        ctx = _active_run_ctx.get()
        if ctx is None:
            # Outside a workflow — pass through directly
            return await self._func(*args, **kwargs)

        legacy_cache_key = ctx._get_legacy_step_cache_key(self.name)
        cache_key = legacy_cache_key
        replay_identity = self._get_replay_identity(args, kwargs)
        if replay_identity is not None:
            identity_kind, identity = replay_identity
            if identity_kind == "explicit":
                cache_key = ctx._get_explicit_step_cache_key(self.name, self._wrapper_identity, identity)
            else:
                cache_key = ctx._get_automatic_step_cache_key(self.name, self._wrapper_identity, identity)

            found, cached = ctx._get_cached_result(cache_key)
            if found:
                return await self._return_cached_result(ctx, cache_key, cached)
            if ctx._has_incompatible_versioned_cache_entry(cache_key):
                raise ValueError(
                    f"Checkpoint cache for @step '{self.name}' was created by a different step definition. "
                    "Start a new run or restore a checkpoint created by the current workflow version."
                )

        found, cached = ctx._get_cached_result(legacy_cache_key)
        if found:
            if ctx._is_concurrent_execution():
                raise ValueError(
                    f"Cannot safely replay legacy order-based cache entry for concurrent @step '{self.name}'. "
                    "Regenerate the checkpoint with the current version and provide replay_key for opaque or "
                    "non-interchangeable concurrent calls."
                )
            return await self._return_cached_result(ctx, legacy_cache_key, cached)

        if replay_identity is None and ctx._is_concurrent_execution():
            raise ValueError(
                f"Cannot derive a stable replay identity for concurrent @step '{self.name}'. "
                "Use @step(replay_key=...) to identify each logical invocation."
            )

        # Inject RunContext if the step function declares it
        call_args, call_kwargs = self._build_call_args_with_ctx(ctx, args, kwargs)

        # Defensive deepcopy for the event log only; fall back to the live
        # reference so non-deepcopyable args (locks, sockets) don't fail.
        if args or kwargs:
            try:
                invocation_data: Any = deepcopy({"args": args, "kwargs": kwargs})
            except Exception:
                invocation_data = {"args": args, "kwargs": kwargs}
        else:
            invocation_data = None
        await ctx.add_event(WorkflowEvent.executor_invoked(self.name, invocation_data))
        auto_request_info_index_before = ctx._auto_request_info_index
        try:
            result = await self._func(*call_args, **call_kwargs)
        except Exception as exc:
            # NOTE: WorkflowInterrupted (from request_info inside a step) inherits
            # from BaseException, NOT Exception, so it propagates past this handler
            # without emitting a spurious executor_failed event.  This is intentional
            # — request_info is fully supported inside @step functions.
            await ctx.add_event(WorkflowEvent.executor_failed(self.name, WorkflowErrorDetails.from_exception(exc)))
            raise
        ctx._set_cached_step_auto_request_info_count(
            cache_key,
            ctx._auto_request_info_index - auto_request_info_index_before,
        )
        ctx._set_cached_result(cache_key, _snapshot_step_cache_value(result))
        await ctx.add_event(WorkflowEvent.executor_completed(self.name, _snapshot_step_cache_value(result)))
        if ctx._on_step_completed is not None:
            await ctx._on_step_completed()
        return result


# ---------------------------------------------------------------------------
# @step decorator
# ---------------------------------------------------------------------------


@overload
def step(func: Callable[..., Awaitable[R]]) -> StepWrapper[R]: ...


@overload
def step(
    *,
    name: str | None = None,
    replay_key: Callable[..., str] | None = None,
) -> Callable[[Callable[..., Awaitable[R]]], StepWrapper[R]]: ...


@experimental(feature_id=ExperimentalFeature.FUNCTIONAL_WORKFLOWS)
def step(
    func: Callable[..., Awaitable[Any]] | None = None,
    *,
    name: str | None = None,
    replay_key: Callable[..., str] | None = None,
) -> StepWrapper[Any] | Callable[[Callable[..., Awaitable[Any]]], StepWrapper[Any]]:
    """Decorator that marks an async function as a tracked workflow step.

    Supports both bare ``@step`` and parameterized ``@step(name="custom")``
    forms.  Inside a running ``@workflow`` function, calls to a step are
    intercepted for result caching, event emission, and per-step
    checkpointing.  If the step function declares a :class:`RunContext`
    parameter (by type annotation or the name ``ctx``), the active context
    is automatically injected, giving the step access to
    :meth:`~RunContext.request_info`, state, and event APIs.  Outside a
    workflow the decorated function behaves identically to the original,
    making it fully testable in isolation.

    The ``@step`` decorator is **optional**.  Plain async functions work
    inside ``@workflow`` without it; use ``@step`` only when you need
    caching, checkpointing, or observability for a particular call.

    Automatic replay identity is derived from bound canonical arguments.
    Concurrent calls with identical automatic identities must produce
    interchangeable results. Use distinct ``replay_key`` values when opaque
    arguments, captured state, generated wrappers, or other state distinguish
    the logical invocations. Legacy order-based checkpoints replay sequential
    steps, but concurrent legacy cache hits fail explicitly rather than
    returning a potentially mismatched result.

    Args:
        func: The async function to decorate (when using the bare
            ``@step`` form).
        name: Optional display name for the step.  Defaults to the
            function's ``__name__``.
        replay_key: Optional callback that returns a stable, unique,
            non-empty string for each logical invocation. Use this when step
            arguments are opaque or when concurrent calls with identical
            arguments can produce different results.

    Returns:
        A :class:`StepWrapper` (bare form) or a decorator that produces
        one (parameterized form).

    Raises:
        TypeError: If the decorated function is not async.
        ValueError: If replay identity is unavailable or invalid for a
            concurrent invocation, or a legacy checkpoint cannot be replayed
            safely under concurrency.

    Examples:

        .. code-block:: python

            @step
            async def fetch_data(url: str) -> dict:
                return await http_get(url)


            @step(name="transform")
            async def transform_data(raw: dict) -> str:
                return json.dumps(raw)


            @step(replay_key=lambda connection, record_id: record_id)
            async def load_record(connection: object, record_id: str) -> dict:
                return await connection.load(record_id)


            # Step with HITL — RunContext is auto-injected inside a workflow:
            @step
            async def review(doc: str, ctx: RunContext) -> str:
                return await ctx.request_info({"draft": doc}, response_type=str)
    """
    if func is not None:
        return StepWrapper(func, name=name, replay_key=replay_key)

    def _decorator(fn: Callable[..., Awaitable[Any]]) -> StepWrapper[Any]:
        return StepWrapper(fn, name=name, replay_key=replay_key)

    return _decorator


# ---------------------------------------------------------------------------
# FunctionalWorkflowDefinition
# ---------------------------------------------------------------------------


@experimental(feature_id=ExperimentalFeature.FUNCTIONAL_WORKFLOWS)
class FunctionalWorkflowDefinition:
    """Stateless definition produced by :func:`workflow`.

    Call :meth:`build` to create a stateful :class:`FunctionalWorkflow`.
    Each built workflow represents one logical caller or session.
    """

    def __init__(
        self,
        func: Callable[..., Awaitable[Any]],
        *,
        name: str | None = None,
        description: str | None = None,
    ) -> None:
        FunctionalWorkflow._classify_signature(func)
        self._func = func
        self.name = name or func.__name__
        self.description = description
        functools.update_wrapper(self, func)  # type: ignore[arg-type]

    def build(
        self,
        *,
        checkpoint_storage: CheckpointStorage | None = None,
    ) -> FunctionalWorkflow:
        """Build a stateful workflow for one logical caller or session."""
        return FunctionalWorkflow(
            self._func,
            name=self.name,
            description=self.description,
            checkpoint_storage=checkpoint_storage,
        )


# ---------------------------------------------------------------------------
# FunctionalWorkflow
# ---------------------------------------------------------------------------


@experimental(feature_id=ExperimentalFeature.FUNCTIONAL_WORKFLOWS)
class FunctionalWorkflow:
    """A workflow backed by a user-defined async function.

    Built from a :class:`FunctionalWorkflowDefinition`. Exposes the same
    ``run()`` interface as graph-based :class:`Workflow` objects, returning a
    :class:`WorkflowRunResult` (or a :class:`ResponseStream` in streaming
    mode).

    The underlying function is executed directly — no graph compilation or
    edge wiring is involved.  Native Python control flow (``if``/``else``,
    ``for``, ``asyncio.gather``) is used for branching and parallelism.

    Like graph-based :class:`Workflow`, each instance owns mutable execution
    state across calls to :meth:`run`. Scope an instance to one logical
    caller or session; build separate instances for independent callers.

    Args:
        func: The async function that implements the workflow logic.
        name: Display name for the workflow.  Defaults to ``func.__name__``.
        description: Optional human-readable description.
        checkpoint_storage: Default :class:`CheckpointStorage` used for
            persisting step results and state between runs.  Can be
            overridden per-run via the *checkpoint_storage* parameter of
            :meth:`run`.

    Examples:

        .. code-block:: python

            @workflow
            async def my_pipeline(data: str) -> str:
                return await to_upper(data)


            pipeline = my_pipeline.build()
            result = await pipeline.run("hello")
            print(result.get_outputs())  # ['HELLO']
    """

    def __init__(
        self,
        func: Callable[..., Awaitable[Any]],
        *,
        name: str | None = None,
        description: str | None = None,
        checkpoint_storage: CheckpointStorage | None = None,
    ) -> None:
        self._func = func
        self.name = name or func.__name__
        self.description = description
        self._checkpoint_storage = checkpoint_storage
        self._is_running = False
        # Replay state: cleared on clean completion so later responses-only
        # calls can't silently replay with stale data from a prior run.
        self._last_message: Any = None
        self._last_step_cache: dict[str, Any] = {}
        self._last_step_cache_auto_request_info_counts: dict[str, int] = {}
        self._last_state: dict[str, Any] = {}
        self._last_pending_request_ids: set[str] = set()

        # Signature arity is validated once at decoration time.
        self._non_ctx_param_names = self._classify_signature(func)

        # Discover step names referenced in the function for signature hash
        self._step_names = self._discover_step_names(func)

        # Compute a stable signature hash
        self.graph_signature_hash = self._compute_signature_hash()

        functools.update_wrapper(self, func)  # type: ignore[arg-type]

    @staticmethod
    def _snapshot_replay_message(message: Any) -> Any:
        try:
            return deepcopy(message)
        except Exception:
            return message

    def _capture_replay_state(self, ctx: RunContext, message: Any | None = None) -> None:
        """Capture the state needed to continue a response-only HITL replay."""
        if message is not None and self._last_message is None:
            self._last_message = self._snapshot_replay_message(message)
        self._last_step_cache = dict(ctx._step_cache)
        self._last_step_cache_auto_request_info_counts = dict(ctx._step_cache_auto_request_info_counts)
        self._last_state = dict(ctx._state)
        self._last_pending_request_ids = set(ctx._pending_requests)

    def _restore_replay_state(self, ctx: RunContext) -> Any:
        """Restore cached execution state and return the message used by the replay."""
        ctx._step_cache = dict(self._last_step_cache)
        ctx._step_cache_auto_request_info_counts = dict(self._last_step_cache_auto_request_info_counts)
        ctx._state = dict(self._last_state)
        return self._last_message

    def _clear_replay_state(self) -> None:
        """Clear all state retained for a response-only replay."""
        self._last_message = None
        self._last_step_cache = {}
        self._last_step_cache_auto_request_info_counts = {}
        self._last_state = {}
        self._last_pending_request_ids = set()

    @staticmethod
    def _classify_signature(func: Callable[..., Any]) -> list[str]:
        """Return the names of non-ctx parameters, validating arity.

        A workflow function may declare at most one non-ctx parameter (which
        receives the caller-supplied ``message``).  Any extra non-ctx
        parameters would be silently dropped by ``_execute``, so we reject
        them at decoration time.
        """
        try:
            hints = typing.get_type_hints(func)
        except Exception:
            hints = {}
        non_ctx: list[str] = []
        for param_name, param in inspect.signature(func).parameters.items():
            resolved = hints.get(param_name, param.annotation)
            if resolved is RunContext or param_name == "ctx":
                continue
            if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
                continue
            non_ctx.append(param_name)
        if len(non_ctx) > 1:
            raise ValueError(
                f"@workflow function '{func.__name__}' declares multiple non-RunContext "
                f"parameters ({non_ctx}); at most one is supported (it receives the "
                f"'message' argument passed to .run()).  Combine the inputs into a "
                f"single object or dict."
            )
        return non_ctx

    # ------------------------------------------------------------------
    # run() — same overloaded interface as graph Workflow
    # ------------------------------------------------------------------

    @overload
    def run(
        self,
        message: Any | None = None,
        *,
        stream: Literal[True],
        responses: dict[str, Any] | None = None,
        checkpoint_id: str | None = None,
        checkpoint_storage: CheckpointStorage | None = None,
        **kwargs: Any,
    ) -> ResponseStream[WorkflowEvent[Any], WorkflowRunResult]: ...

    @overload
    def run(
        self,
        message: Any | None = None,
        *,
        stream: Literal[False] = ...,
        responses: dict[str, Any] | None = None,
        checkpoint_id: str | None = None,
        checkpoint_storage: CheckpointStorage | None = None,
        include_status_events: bool = False,
        **kwargs: Any,
    ) -> Awaitable[WorkflowRunResult]: ...

    def run(
        self,
        message: Any | None = None,
        *,
        stream: bool = False,
        responses: dict[str, Any] | None = None,
        checkpoint_id: str | None = None,
        checkpoint_storage: CheckpointStorage | None = None,
        include_status_events: bool = False,
        **kwargs: Any,
    ) -> ResponseStream[WorkflowEvent[Any], WorkflowRunResult] | Awaitable[WorkflowRunResult]:
        """Run the functional workflow.

        At least one of *message*, *responses*, or *checkpoint_id* must be
        provided.  *message* starts a fresh run; *responses* resumes after a
        HITL interruption; *checkpoint_id* restores from a previously saved
        checkpoint.  *responses* may be combined with *checkpoint_id* to
        restore a checkpoint and inject HITL responses in a single call.
        *message* is mutually exclusive with both *responses* and
        *checkpoint_id*.

        Args:
            message: Input data passed as the first positional argument to
                the workflow function.
            stream: If ``True``, return a :class:`ResponseStream` that
                yields :class:`WorkflowEvent` instances as they are produced.
            responses: HITL responses keyed by ``request_id``, used to
                resume a workflow that was suspended by
                :meth:`RunContext.request_info`.
            checkpoint_id: Identifier of a checkpoint to restore from.
                Requires *checkpoint_storage* to be set (here or on the
                decorator).
            checkpoint_storage: Override the default checkpoint storage
                for this run.
            include_status_events: When ``True`` (non-streaming only),
                include status-change events in the result.

        Keyword Args:
            **kwargs: Extra keyword arguments stored on
                :attr:`RunContext._run_kwargs` and accessible to step
                functions.

        Returns:
            A :class:`WorkflowRunResult` (non-streaming) or a
            :class:`ResponseStream` (streaming).

        Raises:
            ValueError: If the combination of *message*, *responses*, and
                *checkpoint_id* is invalid.
            RuntimeError: If the workflow is already running (concurrent
                execution is not allowed).
        """
        self._validate_run_params(message, responses, checkpoint_id)
        # Warn (but don't block) when a fresh message or a checkpoint restore begins while a prior
        # run left request_info events pending. Mirrors Workflow.run. Delivering responses is the
        # normal way to complete the pending cycle and is intentionally not warned.
        if (message is not None or checkpoint_id is not None) and self._last_pending_request_ids:
            logger.warning(
                "Workflow %s received %s while %d request_info event(s) are still pending from an "
                "unfinished request/response cycle; %s. Deliver responses (responses=...) to complete "
                "the pending cycle before starting new input.",
                self.name,
                "a fresh message" if message is not None else "a checkpoint restore",
                len(self._last_pending_request_ids),
                (
                    "those requests remain answerable, but this run advances workflow state, so a "
                    "response that arrives later may apply to a workflow that has moved on"
                    if message is not None
                    else "those pending requests will be overwritten by the checkpoint's state"
                ),
            )
        if responses and checkpoint_id is None:
            # Require at least one response key to match a currently-pending
            # request; prevents silent replay against stale state while still
            # allowing callers to accumulate prior answers across multi-round
            # HITL.
            if not self._last_pending_request_ids:
                raise ValueError(
                    f"responses={list(responses)!r} do not correspond to any pending request on "
                    f"workflow '{self.name}'.  The workflow has no pending request_info events, "
                    f"so there is nothing to resume.  Start a fresh run with 'message', or supply "
                    f"'checkpoint_id' to restore a specific checkpoint."
                )
            if not (set(responses) & self._last_pending_request_ids):
                raise ValueError(
                    f"responses={list(responses)!r} do not answer any of the currently-pending "
                    f"requests on workflow '{self.name}' ({sorted(self._last_pending_request_ids)!r}).  "
                    f"Provide a response keyed by one of the pending request_ids."
                )
        self._ensure_not_running()

        response_stream: ResponseStream[WorkflowEvent[Any], WorkflowRunResult] = ResponseStream(
            self._run_core(
                message=message,
                responses=responses,
                checkpoint_id=checkpoint_id,
                checkpoint_storage=checkpoint_storage,
                streaming=stream,
                **kwargs,
            ),
            finalizer=functools.partial(self._finalize_events, include_status_events=include_status_events),
            cleanup_hooks=[self._run_cleanup],
        )

        if stream:
            return response_stream
        return response_stream.get_final_response()

    # ------------------------------------------------------------------
    # As agent
    # ------------------------------------------------------------------

    def as_agent(
        self,
        name: str | None = None,
        *,
        description: str | None = None,
        context_providers: Sequence[Any] | None = None,
        **kwargs: Any,
    ) -> FunctionalWorkflowAgent:
        """Wrap this workflow as an agent-compatible object.

        The returned :class:`FunctionalWorkflowAgent` exposes a ``run()``
        method that delegates to the workflow, surfaces ``request_info``
        events as function approval requests, and converts outputs into an
        :class:`AgentResponse`.

        Signature mirrors graph :meth:`Workflow.as_agent` so polymorphic
        code works over either flavor.

        Args:
            name: Display name for the agent.  Defaults to the workflow name.
            description: Optional description override.  Defaults to the
                workflow's ``description``.
            context_providers: Optional context providers to associate with
                the agent.  Stored for caller introspection.
            **kwargs: Reserved for future parity with
                :meth:`Workflow.as_agent`.

        Returns:
            A :class:`FunctionalWorkflowAgent` wrapping this workflow.
        """
        return FunctionalWorkflowAgent(
            workflow=self,
            name=name,
            description=description,
            context_providers=context_providers,
            **kwargs,
        )

    # ------------------------------------------------------------------
    # Internal execution
    # ------------------------------------------------------------------

    async def _run_core(
        self,
        message: Any | None = None,
        *,
        responses: dict[str, Any] | None = None,
        checkpoint_id: str | None = None,
        checkpoint_storage: CheckpointStorage | None = None,
        streaming: bool = False,
        **kwargs: Any,
    ) -> AsyncIterable[WorkflowEvent[Any]]:
        storage = checkpoint_storage or self._checkpoint_storage

        # Build context
        ctx = RunContext(self.name, streaming=streaming, run_kwargs=kwargs if kwargs else None)

        # Restore from checkpoint if requested
        prev_checkpoint_id: str | None = None
        if checkpoint_id is not None:
            if storage is None:
                raise ValueError(
                    "Cannot restore from checkpoint without checkpoint_storage. "
                    "Provide checkpoint_storage to build() or to this run."
                )
            checkpoint = await storage.load(checkpoint_id)
            if checkpoint.graph_signature_hash != self.graph_signature_hash:
                raise ValueError(
                    f"Checkpoint '{checkpoint_id}' was created by a different version of workflow "
                    f"'{checkpoint.workflow_name}' and is not compatible with the current version. "
                    f"The workflow's step structure may have changed since this checkpoint was saved."
                )
            prev_checkpoint_id = checkpoint_id
            # Restore step cache
            step_cache_data = checkpoint.state.get("_step_cache", {})
            ctx._import_step_cache(step_cache_data)
            step_cache_auto_request_info_counts = checkpoint.state.get("_step_cache_auto_request_info_counts", {})
            ctx._import_step_cache_auto_request_info_counts(step_cache_auto_request_info_counts)
            # Restore user state
            ctx._state = {k: v for k, v in checkpoint.state.items() if not k.startswith("_")}
            # Restore pending request info events
            ctx._pending_requests = dict(checkpoint.pending_request_info_events)
            # Restore original message for replay
            if message is None:
                message = checkpoint.state.get("_original_message")

        # For response-only replay (no checkpoint), restore cached state
        if checkpoint_id is None and responses:
            replay_message = self._restore_replay_state(ctx)
            if message is None:
                message = replay_message

        # Store message for future replays
        if message is not None:
            self._last_message = self._snapshot_replay_message(message)

        # Set responses for replay
        if responses:
            ctx._set_responses(responses)

        # Wire up per-step checkpointing
        # Use a mutable list so the closure can update prev_checkpoint_id
        ckpt_chain: list[str | None] = [prev_checkpoint_id]
        if storage is not None:

            async def _on_step_completed() -> None:
                ckpt_chain[0] = await self._save_checkpoint(ctx, storage, ckpt_chain[0])

            ctx._on_step_completed = _on_step_completed

        # Tracing: start the run span without attaching it. Attaching with
        # create_workflow_span() across a yield leaves OpenTelemetry's context
        # token set when this generator is later closed on GC from a different
        # Context. Activate the span only around non-yielding work.
        attributes: dict[str, Any] = {OtelAttr.WORKFLOW_NAME: self.name}
        if self.description:
            attributes[OtelAttr.WORKFLOW_DESCRIPTION] = self.description

        span = start_workflow_span(OtelAttr.WORKFLOW_RUN_SPAN, attributes)
        saw_request = False
        try:
            span.add_event(OtelAttr.WORKFLOW_STARTED)

            yield _framework_event(WorkflowEvent.started)
            yield _framework_event(WorkflowEvent.status, WorkflowRunState.IN_PROGRESS)

            # Execute the user function with the run span current so nested
            # executor/processing spans parent correctly.
            with _activate_span(span):
                return_value = await self._execute(ctx, message)

                # Emit the return value as the workflow output.
                if return_value is not None:
                    await ctx.add_event(
                        _framework_event(WorkflowEvent, "output", executor_id=self.name, data=return_value)
                    )

                # Persist step cache for response-only replay
                self._capture_replay_state(ctx, message)

            # Yield collected events.
            # NOTE: Events are buffered during _execute() and yielded after
            # the user function completes.  This is *not* true streaming —
            # all events have already been produced by this point.  True
            # per-token streaming from inner agent calls is a future
            # enhancement.
            for event in ctx._get_events():
                if event.type == "request_info":
                    saw_request = True
                yield event
                if event.type == "request_info":
                    yield _framework_event(WorkflowEvent.status, WorkflowRunState.IN_PROGRESS_PENDING_REQUESTS)

            # Save final checkpoint if storage is available
            if storage is not None:
                await self._save_checkpoint(ctx, storage, ckpt_chain[0])

            # Final status
            if saw_request:
                yield _framework_event(WorkflowEvent.status, WorkflowRunState.IDLE_WITH_PENDING_REQUESTS)
            else:
                # Clean completion — drop cross-run replay state.
                self._clear_replay_state()
                yield _framework_event(WorkflowEvent.status, WorkflowRunState.IDLE)

            span.add_event(OtelAttr.WORKFLOW_COMPLETED)

        except WorkflowInterrupted:
            # Persist step cache for response-only replay
            self._capture_replay_state(ctx, message)

            # HITL interruption — yield events collected so far
            for event in ctx._get_events():
                if event.type == "request_info":
                    saw_request = True
                yield event
                if event.type == "request_info":
                    yield _framework_event(WorkflowEvent.status, WorkflowRunState.IN_PROGRESS_PENDING_REQUESTS)

            # Save checkpoint
            if storage is not None:
                await self._save_checkpoint(ctx, storage, ckpt_chain[0])

            yield _framework_event(WorkflowEvent.status, WorkflowRunState.IDLE_WITH_PENDING_REQUESTS)

            span.add_event(OtelAttr.WORKFLOW_COMPLETED)

        except Exception as exc:
            # Yield any events collected before the failure
            for event in ctx._get_events():
                yield event

            details = WorkflowErrorDetails.from_exception(exc)
            yield _framework_event(WorkflowEvent.failed, details)
            yield _framework_event(WorkflowEvent.status, WorkflowRunState.FAILED)

            span.add_event(
                name=OtelAttr.WORKFLOW_ERROR,
                attributes={
                    "error.message": str(exc),
                    "error.type": type(exc).__name__,
                },
            )
            capture_exception(span, exception=exc)
            raise
        finally:
            # ResponseStream cleanup_hooks do not run when the generator is
            # closed by GC. Release the run lock here so a follow-up run
            # after an abandoned stream is not rejected as concurrent.
            self._release_run_guard()
            span.end()

    async def _execute(self, ctx: RunContext, message: Any) -> Any:
        """Run the user's async function with the active context."""
        if message is not None and not self._non_ctx_param_names:
            raise ValueError(
                f"@workflow function '{self._func.__name__}' has no non-RunContext "
                f"parameter to receive a message, but .run(message=...) was called "
                f"with a non-None value.  Either add a first parameter to the "
                f"workflow function or omit 'message'."
            )

        token = _active_run_ctx.set(ctx)
        ctx._root_task = asyncio.current_task()
        release_task_tracking = _track_workflow_tasks()
        try:
            sig = inspect.signature(self._func)
            params = list(sig.parameters.values())

            # Resolve string annotations to actual types
            try:
                hints = typing.get_type_hints(self._func)
            except Exception as exc:
                logger.warning(
                    "Failed to resolve type hints for workflow function '%s': %s. "
                    "RunContext injection may not work if annotations are forward references.",
                    self._func.__name__,
                    exc,
                )
                hints = {}

            # Build call arguments: inject RunContext and pass `message`.
            # RunContext is detected by type annotation first, then by
            # parameter name "ctx" — so both of these work:
            #   async def my_workflow(data: str, ctx: RunContext) -> str:
            #   async def my_workflow(data: str, ctx) -> str:
            call_args: list[Any] = []
            message_injected = False

            for param in params:
                resolved = hints.get(param.name, param.annotation)
                if resolved is RunContext or param.name == "ctx":
                    call_args.append(ctx)
                elif not message_injected:
                    # First non-ctx param gets the message
                    call_args.append(message)
                    message_injected = True

            return await self._func(*call_args)
        finally:
            release_task_tracking()
            _active_run_ctx.reset(token)

    # ------------------------------------------------------------------
    # Checkpoint helpers
    # ------------------------------------------------------------------

    async def _save_checkpoint(
        self,
        ctx: RunContext,
        storage: CheckpointStorage,
        previous_checkpoint_id: str | None = None,
    ) -> str:
        state = dict(ctx._state)
        state["_step_cache"] = ctx._export_step_cache()
        state["_step_cache_auto_request_info_counts"] = ctx._export_step_cache_auto_request_info_counts()
        state["_original_message"] = self._last_message

        checkpoint = WorkflowCheckpoint(
            workflow_name=self.name,
            graph_signature_hash=self.graph_signature_hash,
            previous_checkpoint_id=previous_checkpoint_id,
            state=state,
            pending_request_info_events=dict(ctx._pending_requests),
        )
        return await storage.save(checkpoint)

    def _compute_signature_hash(self) -> str:
        """Stable hash of the workflow's code shape.

        Mixes workflow name, statically-discovered step names, and a digest
        of ``__code__.co_code`` + ``co_names``.  The code digest catches
        body changes that step-name discovery misses (e.g. attribute-access
        step references).
        """
        code = getattr(self._func, "__code__", None)
        co_code_hex = hashlib.sha256(code.co_code).hexdigest() if code is not None else ""
        co_names = tuple(sorted(code.co_names)) if code is not None else ()
        sig_data = {
            "workflow": self.name,
            "steps": sorted(self._step_names),
            "co_code": co_code_hex,
            "co_names": list(co_names),
        }
        canonical = json.dumps(sig_data, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _discover_step_names(func: Callable[..., Any]) -> list[str]:
        """Extract step names referenced by the workflow function.

        Inspects the function's ``__code__.co_names`` and global scope for
        ``StepWrapper`` instances.  Steps accessed via module or class
        attributes (``my_steps.fetch``) are missed here, but
        :meth:`_compute_signature_hash` still captures them through the
        ``co_code`` digest.
        """
        names: list[str] = []
        globs = getattr(func, "__globals__", {})
        code_names = getattr(getattr(func, "__code__", None), "co_names", ())
        for n in code_names:
            obj = globs.get(n)
            if isinstance(obj, StepWrapper):
                names.append(obj.name)
        return names

    # ------------------------------------------------------------------
    # Finalize / cleanup / validation (mirrors Workflow)
    # ------------------------------------------------------------------

    @staticmethod
    def _finalize_events(
        events: Sequence[WorkflowEvent[Any]],
        *,
        include_status_events: bool = False,
    ) -> WorkflowRunResult:
        filtered: list[WorkflowEvent[Any]] = []
        status_events: list[WorkflowEvent[Any]] = []

        for ev in events:
            if ev.type == "started":
                continue
            if ev.type == "status":
                status_events.append(ev)
                if include_status_events:
                    filtered.append(ev)
                continue
            filtered.append(ev)

        return WorkflowRunResult(filtered, status_events)

    @staticmethod
    def _validate_run_params(
        message: Any | None,
        responses: dict[str, Any] | None,
        checkpoint_id: str | None,
    ) -> None:
        if message is not None and responses is not None:
            raise ValueError("Cannot provide both 'message' and 'responses'. Use one or the other.")

        if message is not None and checkpoint_id is not None:
            raise ValueError("Cannot provide both 'message' and 'checkpoint_id'. Use one or the other.")

        if message is None and responses is None and checkpoint_id is None:
            raise ValueError(
                "Must provide at least one of: 'message' (new run), 'responses' (send responses), "
                "or 'checkpoint_id' (resume from checkpoint)."
            )

    def _ensure_not_running(self) -> None:
        if self._is_running:
            raise RuntimeError("Workflow is already running. Concurrent executions are not allowed.")
        self._is_running = True

    def _release_run_guard(self) -> None:
        self._is_running = False

    async def _run_cleanup(self) -> None:
        self._release_run_guard()


# ---------------------------------------------------------------------------
# @workflow decorator
# ---------------------------------------------------------------------------


@overload
def workflow(func: Callable[..., Awaitable[Any]]) -> FunctionalWorkflowDefinition: ...


@overload
def workflow(
    *,
    name: str | None = None,
    description: str | None = None,
) -> Callable[[Callable[..., Awaitable[Any]]], FunctionalWorkflowDefinition]: ...


@experimental(feature_id=ExperimentalFeature.FUNCTIONAL_WORKFLOWS)
def workflow(
    func: Callable[..., Awaitable[Any]] | None = None,
    *,
    name: str | None = None,
    description: str | None = None,
) -> FunctionalWorkflowDefinition | Callable[[Callable[..., Awaitable[Any]]], FunctionalWorkflowDefinition]:
    """Decorator that creates a stateless :class:`FunctionalWorkflowDefinition`.

    Supports both bare ``@workflow`` and parameterized
    ``@workflow(name="my_wf")`` forms.

    The decorated function receives its input as the first positional argument
    and a :class:`RunContext` instance wherever a parameter is annotated with
    that type. Call ``build()`` on the resulting definition to create a
    stateful :class:`FunctionalWorkflow`.

    Args:
        func: The async function to decorate (when using the bare
            ``@workflow`` form).
        name: Display name for the workflow.  Defaults to ``func.__name__``.
        description: Optional human-readable description.

    Returns:
        A :class:`FunctionalWorkflowDefinition` (bare form) or a decorator
        that produces one (parameterized form).

    Examples:

        .. code-block:: python

            # Bare form
            @workflow
            async def pipeline(data: str) -> str:
                return await process(data)


            # Parameterized form
            @workflow(name="my_pipeline")
            async def pipeline(data: str) -> str: ...


            instance = pipeline.build(checkpoint_storage=storage)
    """
    if func is not None:
        return FunctionalWorkflowDefinition(func, name=name, description=description)

    def _decorator(fn: Callable[..., Awaitable[Any]]) -> FunctionalWorkflowDefinition:
        return FunctionalWorkflowDefinition(fn, name=name, description=description)

    return _decorator


# ---------------------------------------------------------------------------
# FunctionalWorkflowAgent
# ---------------------------------------------------------------------------


@experimental(feature_id=ExperimentalFeature.FUNCTIONAL_WORKFLOWS)
class FunctionalWorkflowAgent(BaseAgent):
    """Agent adapter for a :class:`FunctionalWorkflow`.

    Provides a ``run()`` method with the same overloaded signature as
    :class:`BaseAgent` — returning an :class:`AgentResponse` (non-streaming)
    or a :class:`ResponseStream[AgentResponseUpdate, AgentResponse]`
    (streaming), making functional workflows usable anywhere an
    agent-compatible object is expected.

    ``request_info`` events emitted by the underlying workflow are surfaced
    as :class:`FunctionApprovalRequestContent` items (mirroring the graph
    :class:`WorkflowAgent`), so HITL workflows are callable via this
    adapter.  Callers resume via ``responses=`` / ``checkpoint_id=``.

    The wrapped workflow owns mutable execution state. Scope the workflow and
    this adapter to one logical caller or session; create separate workflow
    instances for independent or mutually untrusted callers. If those
    instances use checkpoint storage, the host must also authorize and
    tenant-scope access to that external store.

    Args:
        workflow: The :class:`FunctionalWorkflow` to wrap.
        name: Display name for the agent.  Defaults to the workflow name.
        description: Display description.  Defaults to ``workflow.description``.
        context_providers: Optional context providers stored for caller
            introspection.
        **kwargs: Reserved for future parity with :class:`WorkflowAgent`;
            currently ignored.
    """

    REQUEST_INFO_FUNCTION_NAME: str = "request_info"

    def __init__(
        self,
        workflow: FunctionalWorkflow,
        *,
        name: str | None = None,
        description: str | None = None,
        context_providers: Sequence[Any] | None = None,
        **kwargs: Any,
    ) -> None:
        # kwargs is accepted for signature parity with graph Workflow.as_agent
        # but not otherwise consumed.
        del kwargs
        self._workflow = workflow
        resolved_name = name or workflow.name
        super().__init__(
            id=f"FunctionalWorkflowAgent_{resolved_name}",
            name=resolved_name,
            description=description if description is not None else workflow.description,
            context_providers=context_providers,
        )
        self._pending_requests: dict[str, WorkflowEvent[Any]] = {}

    @property
    def pending_requests(self) -> dict[str, WorkflowEvent[Any]]:
        """Pending request_info events emitted during the last run."""
        return self._pending_requests

    @overload
    def run(
        self,
        messages: Any | None = None,
        *,
        stream: Literal[True],
        responses: dict[str, Any] | None = None,
        checkpoint_id: str | None = None,
        checkpoint_storage: CheckpointStorage | None = None,
        **kwargs: Any,
    ) -> ResponseStream[AgentResponseUpdate, AgentResponse]: ...

    @overload
    def run(
        self,
        messages: Any | None = None,
        *,
        stream: Literal[False] = ...,
        responses: dict[str, Any] | None = None,
        checkpoint_id: str | None = None,
        checkpoint_storage: CheckpointStorage | None = None,
        **kwargs: Any,
    ) -> Awaitable[AgentResponse]: ...

    def run(
        self,
        messages: Any | None = None,
        *,
        stream: bool = False,
        responses: dict[str, Any] | None = None,
        checkpoint_id: str | None = None,
        checkpoint_storage: CheckpointStorage | None = None,
        **kwargs: Any,
    ) -> ResponseStream[AgentResponseUpdate, AgentResponse] | Awaitable[AgentResponse]:
        """Run the underlying workflow and return the result as an agent response.

        Args:
            messages: Input data forwarded to :meth:`FunctionalWorkflow.run`.

        Keyword Args:
            stream: If ``True``, return a :class:`ResponseStream` of
                :class:`AgentResponseUpdate` items.
            responses: HITL responses keyed by ``request_id``, forwarded to
                the underlying workflow so HITL resumes work via this agent.
            checkpoint_id: Optional checkpoint to restore from.
            checkpoint_storage: Override the workflow's default
                :class:`CheckpointStorage` for this run.
            **kwargs: Extra keyword arguments forwarded to the workflow run.

        Returns:
            An :class:`AgentResponse` (non-streaming) or a
            :class:`ResponseStream` (streaming).
        """
        if stream:
            return self._run_streaming(
                messages,
                responses=responses,
                checkpoint_id=checkpoint_id,
                checkpoint_storage=checkpoint_storage,
                **kwargs,
            )
        return self._run_non_streaming(
            messages,
            responses=responses,
            checkpoint_id=checkpoint_id,
            checkpoint_storage=checkpoint_storage,
            **kwargs,
        )

    async def _run_non_streaming(
        self,
        messages: Any | None,
        *,
        responses: dict[str, Any] | None = None,
        checkpoint_id: str | None = None,
        checkpoint_storage: CheckpointStorage | None = None,
        **kwargs: Any,
    ) -> AgentResponse:
        result = await self._workflow.run(
            messages,
            responses=responses,
            checkpoint_id=checkpoint_id,
            checkpoint_storage=checkpoint_storage,
            **kwargs,
        )
        return self._result_to_agent_response(result)

    def _run_streaming(
        self,
        messages: Any | None,
        *,
        responses: dict[str, Any] | None = None,
        checkpoint_id: str | None = None,
        checkpoint_storage: CheckpointStorage | None = None,
        **kwargs: Any,
    ) -> ResponseStream[AgentResponseUpdate, AgentResponse]:
        from .._types import Content

        agent_name = self.name
        # Clear per-run pending state up front
        self._pending_requests = {}
        workflow_stream = self._workflow.run(
            messages,
            stream=True,
            responses=responses,
            checkpoint_id=checkpoint_id,
            checkpoint_storage=checkpoint_storage,
            **kwargs,
        )

        async def _generate_updates() -> AsyncIterable[AgentResponseUpdate]:
            async for event in workflow_stream:
                if event.type == "output":
                    data = event.data
                    if isinstance(data, str):
                        contents: list[Content] = [Content.from_text(text=data)]
                    elif isinstance(data, Content):
                        contents = [data]
                    else:
                        contents = [Content.from_text(text=str(data))]
                    yield AgentResponseUpdate(
                        contents=contents,
                        role="assistant",
                        author_name=agent_name,
                    )
                elif event.type == "request_info":
                    approval = self._request_info_to_approval_request(event)
                    if approval is None:
                        continue
                    yield AgentResponseUpdate(
                        contents=[approval],
                        role="assistant",
                        author_name=agent_name,
                    )

        return ResponseStream(
            _generate_updates(),
            finalizer=AgentResponse.from_updates,
        )

    def _request_info_to_approval_request(self, event: WorkflowEvent[Any]) -> Any:
        """Convert a `request_info` event to `FunctionApprovalRequestContent`.

        Returns ``None`` if the event is missing a request_id (defensive;
        `request_info` always sets one).
        """
        from .._types import Content

        request_id = event.request_id
        if not request_id:
            return None
        self._pending_requests[request_id] = event
        function_call = Content.from_function_call(
            call_id=request_id,
            name=self.REQUEST_INFO_FUNCTION_NAME,
            arguments={"request_id": request_id, "data": make_json_safe(event.data)},
        )
        return Content.from_function_approval_request(
            id=request_id,
            function_call=function_call,
            additional_properties={"request_id": request_id},
        )

    def _result_to_agent_response(self, result: WorkflowRunResult) -> AgentResponse:
        from .._types import Content
        from .._types import Message as Msg

        # Refresh pending_requests for this run.
        self._pending_requests = {}

        messages: list[Msg] = []
        for output in result.get_outputs():
            if isinstance(output, str):
                contents: list[Content] = [Content.from_text(text=output)]
            elif isinstance(output, Content):
                contents = [output]
            else:
                contents = [Content.from_text(text=str(output))]
            messages.append(Msg("assistant", contents))

        # Surface pending request_info events so HITL callers see them.
        approval_contents: list[Content] = []
        for event in result.get_request_info_events():
            approval = self._request_info_to_approval_request(event)
            if approval is not None:
                approval_contents.append(approval)
        if approval_contents:
            messages.append(Msg("assistant", approval_contents))

        return AgentResponse(messages=messages)
