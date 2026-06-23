# Copyright (c) Microsoft. All rights reserved.

"""Host-agnostic workflow orchestration engine.

This module provides the shared workflow orchestration logic that executes MAF
Workflows as durable task orchestrations.  It programs against the
:class:`WorkflowOrchestrationContext` protocol so that the same code runs on
both Azure Functions and standalone durabletask hosts.

Key components:

* :func:`run_workflow_orchestrator` — main generator-based orchestrator
* Routing helpers (edge groups, fan-in, HITL)
* Result processing helpers

All host-specific task creation (agent dispatch, activity dispatch, task_all /
task_any) is delegated to the ``WorkflowOrchestrationContext`` adapter.
"""

from __future__ import annotations

import inspect
import json
import logging
from collections import defaultdict
from collections.abc import Generator
from dataclasses import dataclass
from enum import Enum
from typing import Any, cast

from agent_framework import (
    AgentExecutor,
    AgentExecutorRequest,
    AgentExecutorResponse,
    AgentResponse,
    Executor,
    Message,
    Workflow,
    WorkflowConvergenceException,
    WorkflowExecutor,
)
from agent_framework._workflows._edge import (
    Edge,
    EdgeGroup,
    FanInEdgeGroup,
    FanOutEdgeGroup,
    SingleEdgeGroup,
    SwitchCaseEdgeGroup,
)
from agent_framework._workflows._state import State

from .context import WorkflowOrchestrationContext
from .naming import workflow_executor_activity_name, workflow_orchestrator_name, workflow_scoped_executor_id
from .serialization import (
    deserialize_value,
    reconstruct_to_type,
    resolve_type,
    serialize_value,
    strip_pickle_markers,
)

logger = logging.getLogger(__name__)


# ============================================================================
# Source Marker Constants
# ============================================================================

SOURCE_WORKFLOW_START = "__workflow_start__"
SOURCE_ORCHESTRATOR = "__orchestrator__"
SOURCE_HITL_RESPONSE = "__hitl_response__"

# A WorkflowExecutor node runs its inner workflow as a durable child orchestration.
# The parent passes the node's input wrapped in this marker so the child orchestrator
# can tell a trusted sub-orchestration payload (serialized by the parent) apart from
# untrusted top-level client input, and can track nesting depth to bound recursion.
SUBWORKFLOW_INPUT_KEY = "__subworkflow_input__"
SUBWORKFLOW_DEPTH_KEY = "__subworkflow_depth__"

# Maximum sub-workflow nesting depth. Mutually-nested workflows (A hosts B hosts A)
# would otherwise spawn child orchestrations without bound; this caps the tree.
MAX_SUBWORKFLOW_DEPTH = 25

# Name of the auto-generated orchestrator registered by
# ``DurableAIAgentWorker.configure_workflow`` (and the Azure Functions host).
# Standalone clients start a configured workflow by scheduling an orchestration
# with this name, e.g.
# ``client.schedule_new_orchestration(WORKFLOW_ORCHESTRATOR_NAME, input=...)``.
#
# DEPRECATED (multi-workflow migration): this fixed single-workflow name is being
# replaced by per-workflow orchestration names ``dafx-{workflowName}`` derived via
# :func:`agent_framework_durabletask._workflows.naming.workflow_orchestrator_name`.
# It is retained for source compatibility while the single-workflow hosting path
# still uses it; new code should prefer ``workflow_orchestrator_name(name)``.
WORKFLOW_ORCHESTRATOR_NAME = "workflow_orchestrator"


# ============================================================================
# Task Types and Data Structures
# ============================================================================


class TaskType(Enum):
    """Type of executor task."""

    AGENT = "agent"
    ACTIVITY = "activity"
    SUBWORKFLOW = "subworkflow"


@dataclass
class TaskMetadata:
    """Metadata for a pending task."""

    executor_id: str
    message: Any
    source_executor_id: str
    task_type: TaskType
    remaining_messages: list[tuple[str, Any, str]] | None = None
    # For SUBWORKFLOW tasks: the deterministic child orchestration instance id. The
    # parent records these in its custom status before awaiting the child so the read
    # side can reach nested pending HITL requests while the parent is suspended.
    child_instance_id: str | None = None


@dataclass
class ExecutorResult:
    """Result from executing an agent or activity."""

    executor_id: str
    output_message: AgentExecutorResponse | None
    activity_result: dict[str, Any] | None
    task_type: TaskType


@dataclass
class PendingHITLRequest:
    """Tracks a pending Human-in-the-Loop request."""

    request_id: str
    source_executor_id: str
    request_data: Any
    request_type: str | None
    response_type: str | None


# ============================================================================
# Routing Functions
# ============================================================================


def _evaluate_edge_condition_sync(edge: Edge, message: Any) -> bool:
    """Evaluate an edge's condition synchronously.

    Durable orchestrators run as generators, so conditions are evaluated
    synchronously here; the durabletask host does not support ``async`` edge
    conditions. A condition that returns an awaitable cannot be evaluated in
    this context, so the edge is treated as *not matched* (not traversed)
    rather than assuming a result.
    """
    condition = edge._condition  # pyright: ignore[reportPrivateUsage]
    if condition is None:
        return True
    result = condition(message)
    if inspect.isawaitable(result):
        # Async conditions cannot be evaluated in a synchronous orchestrator.
        # Close the unawaited coroutine to avoid a "never awaited" warning and
        # decline to traverse the edge (treated as not matched).
        if inspect.iscoroutine(result):
            result.close()
        logger.warning(
            "Edge condition for %s->%s is async and cannot be evaluated by the durabletask host; "
            "the edge is not traversed. Use a synchronous condition.",
            edge.source_id,
            edge.target_id,
        )
        return False
    return bool(result)


def route_message_through_edge_groups(
    edge_groups: list[EdgeGroup],
    source_id: str,
    message: Any,
) -> list[str]:
    """Route a message through edge groups to find target executor IDs."""
    targets: list[str] = []

    for group in edge_groups:
        if source_id not in group.source_executor_ids:
            continue

        if isinstance(group, (SwitchCaseEdgeGroup, FanOutEdgeGroup)):
            if group.selection_func is not None:
                selected = group.selection_func(message, group.target_executor_ids)
                targets.extend(selected)
            else:
                targets.extend(group.target_executor_ids)

        elif isinstance(group, SingleEdgeGroup):
            edge = group.edges[0]
            if _evaluate_edge_condition_sync(edge, message):
                targets.append(edge.target_id)

        elif isinstance(group, FanInEdgeGroup):
            pass  # Handled separately in the orchestrator loop

        else:
            for edge in group.edges:
                if edge.source_id == source_id and _evaluate_edge_condition_sync(edge, message):
                    targets.append(edge.target_id)

    return targets


def build_agent_executor_response(
    executor_id: str,
    response_text: str | None,
    structured_response: dict[str, Any] | None,
    previous_message: Any,
) -> AgentExecutorResponse:
    """Build an AgentExecutorResponse from entity response data."""
    final_text: str = response_text or ""
    if structured_response:
        final_text = json.dumps(structured_response)

    assistant_message = Message(role="assistant", contents=[final_text])
    agent_response = AgentResponse(messages=[assistant_message])

    full_conversation: list[Message] = []
    if isinstance(previous_message, AgentExecutorResponse) and previous_message.full_conversation:
        full_conversation.extend(previous_message.full_conversation)
    elif isinstance(previous_message, str):
        full_conversation.append(Message(role="user", contents=[previous_message]))
    full_conversation.append(assistant_message)

    return AgentExecutorResponse(
        executor_id=executor_id,
        agent_response=agent_response,
        full_conversation=full_conversation,
    )


# ============================================================================
# Task Preparation Helpers
# ============================================================================


def _prepare_agent_task(
    ctx: WorkflowOrchestrationContext,
    executor_id: str,
    message: Any,
    workflow_name: str,
) -> Any:
    """Prepare an agent task for execution via the context adapter.

    The agent entity is addressed by the workflow-scoped identity
    ``{workflow_name}-{executor_id}`` so two co-hosted workflows that reuse an
    executor id dispatch to distinct entities (the entity layer prefixes this with
    ``dafx-``). The session *key* stays the orchestration instance id, so
    conversation state remains isolated per run.
    """
    message_content = _extract_message_content(message)
    scoped_id = workflow_scoped_executor_id(workflow_name, executor_id)
    return ctx.prepare_agent_task(scoped_id, message_content, ctx.instance_id)


def _prepare_activity_task(
    ctx: WorkflowOrchestrationContext,
    executor_id: str,
    message: Any,
    source_executor_id: str,
    shared_state_snapshot: dict[str, Any] | None,
    workflow_name: str,
) -> Any:
    """Prepare an activity task for execution via the context adapter.

    The activity is dispatched under the workflow-scoped name
    ``dafx-{workflow_name}-{executor_id}`` so two co-hosted workflows that reuse an
    executor id register and dispatch to distinct activity functions.
    """
    activity_input = {
        "executor_id": executor_id,
        "message": serialize_value(message),
        "shared_state_snapshot": shared_state_snapshot,
        "source_executor_ids": [source_executor_id],
    }
    activity_input_json = json.dumps(activity_input)
    activity_name = workflow_executor_activity_name(workflow_name, executor_id)
    return ctx.prepare_activity_task(activity_name, activity_input_json)


def _prepare_subworkflow_task(
    ctx: WorkflowOrchestrationContext,
    executor: WorkflowExecutor,
    message: Any,
    child_instance_id: str,
    depth: int,
) -> Any:
    """Prepare a child-orchestration task that runs a ``WorkflowExecutor``'s inner workflow.

    The inner workflow runs as its own durable orchestration (``dafx-{innerName}``),
    so its executors are independently durable/observable. The node's message is
    serialized and wrapped in a marker so the child orchestrator reconstructs the
    original typed object (trusted internal input) and tracks nesting depth.
    """
    inner_orchestration_name = workflow_orchestrator_name(executor.workflow.name)
    child_input = {
        SUBWORKFLOW_INPUT_KEY: serialize_value(message),
        SUBWORKFLOW_DEPTH_KEY: depth + 1,
    }
    return ctx.call_sub_orchestrator(inner_orchestration_name, child_input, instance_id=child_instance_id)


# ============================================================================
# Result Processing Helpers
# ============================================================================


def _process_agent_response(
    agent_response: AgentResponse,
    executor_id: str,
    message: Any,
) -> ExecutorResult:
    """Process an agent response into an ExecutorResult."""
    response_text = agent_response.text if agent_response else None
    structured_response: dict[str, Any] | None = None

    if agent_response and agent_response.value is not None:
        model_dump = getattr(agent_response.value, "model_dump", None)
        if callable(model_dump):
            dumped = model_dump()
            if isinstance(dumped, dict):
                structured_response = dumped  # type: ignore[assignment]
        elif isinstance(agent_response.value, dict):
            structured_response = agent_response.value

    output_message = build_agent_executor_response(
        executor_id=executor_id,
        response_text=response_text,
        structured_response=structured_response,
        previous_message=message,
    )

    return ExecutorResult(
        executor_id=executor_id,
        output_message=output_message,
        activity_result=None,
        task_type=TaskType.AGENT,
    )


def _process_activity_result(
    result_json: str | None,
    executor_id: str,
    shared_state: dict[str, Any] | None,
    workflow_outputs: list[Any],
) -> ExecutorResult:
    """Process an activity result and apply shared state updates."""
    result = json.loads(result_json) if result_json else None

    if shared_state is not None and result:
        if result.get("shared_state_updates"):
            updates = result["shared_state_updates"]
            logger.debug("[workflow] Applying SharedState updates from %s: %s", executor_id, updates)
            shared_state.update(updates)
        if result.get("shared_state_deletes"):
            deletes = result["shared_state_deletes"]
            logger.debug("[workflow] Applying SharedState deletes from %s: %s", executor_id, deletes)
            for key in deletes:
                shared_state.pop(key, None)

    if result and result.get("outputs"):
        workflow_outputs.extend(result["outputs"])

    return ExecutorResult(
        executor_id=executor_id,
        output_message=None,
        activity_result=result,
        task_type=TaskType.ACTIVITY,
    )


def _process_subworkflow_result(
    child_result: Any,
    executor: WorkflowExecutor,
    workflow_outputs: list[Any],
) -> ExecutorResult:
    """Process a child orchestration's result into an ``ExecutorResult``.

    The child orchestration returns the inner workflow's outputs (a list of values
    already encoded by the inner activity via ``serialize_value``). Mirroring the
    in-process :class:`~agent_framework.WorkflowExecutor`:

    * ``allow_direct_output`` is ``False`` (default): each inner output becomes a
      message routed through the ``WorkflowExecutor`` node's outgoing edges.
    * ``allow_direct_output`` is ``True``: each inner output becomes one of the
      parent workflow's own outputs.
    """
    if isinstance(child_result, list):
        outputs: list[Any] = cast("list[Any]", child_result)
    elif child_result is None:
        outputs = []
    else:
        outputs = [child_result]

    sent_messages: list[dict[str, Any]] = []
    if executor.allow_direct_output:
        # Inner outputs are already serialized (serialize_value); workflow_outputs
        # holds serialized values, so they are directly compatible.
        workflow_outputs.extend(outputs)
    else:
        # Route each inner output as a message from the node; _route_result_messages
        # deserializes each "message" value before routing through edge groups.
        sent_messages = [{"message": output, "target_id": None, "source_id": executor.id} for output in outputs]

    return ExecutorResult(
        executor_id=executor.id,
        output_message=None,
        activity_result={"sent_messages": sent_messages, "outputs": [], "events": []},
        task_type=TaskType.SUBWORKFLOW,
    )


# ============================================================================
# Routing Helpers
# ============================================================================


def _route_result_messages(
    result: ExecutorResult,
    workflow: Workflow,
    next_pending_messages: dict[str, list[tuple[Any, str]]],
    fan_in_pending: dict[str, dict[str, list[tuple[Any, str]]]],
) -> None:
    """Route messages from an executor result to their targets."""
    executor_id = result.executor_id
    messages_to_route: list[tuple[Any, str | None]] = []

    if result.output_message:
        messages_to_route.append((result.output_message, None))

    if result.activity_result and result.activity_result.get("sent_messages"):
        for msg_data in result.activity_result["sent_messages"]:
            sent_msg = msg_data.get("message")
            target_id = msg_data.get("target_id")
            # Use an explicit None check so legitimately falsy payloads
            # (empty string, 0, False) are still routed.
            if sent_msg is not None:
                sent_msg = deserialize_value(sent_msg)
                messages_to_route.append((sent_msg, target_id))

    for msg_to_route, explicit_target in messages_to_route:
        logger.debug("Routing output from %s", executor_id)

        if explicit_target:
            if explicit_target not in next_pending_messages:
                next_pending_messages[explicit_target] = []
            next_pending_messages[explicit_target].append((msg_to_route, executor_id))
            logger.debug("Routed message from %s to explicit target %s", executor_id, explicit_target)
            continue

        for group in workflow.edge_groups:
            if isinstance(group, FanInEdgeGroup) and executor_id in group.source_executor_ids:
                fan_in_pending[group.id][executor_id].append((msg_to_route, executor_id))
                logger.debug("Accumulated message for FanIn group %s from %s", group.id, executor_id)

        targets = route_message_through_edge_groups(workflow.edge_groups, executor_id, msg_to_route)

        for target_id in targets:
            logger.debug("Routing to %s", target_id)
            if target_id not in next_pending_messages:
                next_pending_messages[target_id] = []
            next_pending_messages[target_id].append((msg_to_route, executor_id))


def _check_fan_in_ready(
    workflow: Workflow,
    fan_in_pending: dict[str, dict[str, list[tuple[Any, str]]]],
    next_pending_messages: dict[str, list[tuple[Any, str]]],
) -> None:
    """Check if any FanInEdgeGroups are ready and deliver their messages."""
    for group in workflow.edge_groups:
        if not isinstance(group, FanInEdgeGroup):
            continue

        pending_sources = fan_in_pending.get(group.id, {})

        if not all(src in pending_sources and pending_sources[src] for src in group.source_executor_ids):
            continue

        aggregated: list[Any] = []
        aggregated_sources: list[str] = []
        for src in group.source_executor_ids:
            for msg, msg_source in pending_sources[src]:
                aggregated.append(msg)
                aggregated_sources.append(msg_source)

        target_id = group.target_executor_ids[0]
        logger.debug("FanIn group %s ready, delivering %d messages to %s", group.id, len(aggregated), target_id)

        if target_id not in next_pending_messages:
            next_pending_messages[target_id] = []

        first_source = aggregated_sources[0] if aggregated_sources else "__fan_in__"
        next_pending_messages[target_id].append((aggregated, first_source))

        fan_in_pending[group.id] = defaultdict(list)


# ============================================================================
# HITL Helpers
# ============================================================================


def _collect_hitl_requests(
    result: ExecutorResult,
    pending_hitl_requests: dict[str, PendingHITLRequest],
) -> None:
    """Collect pending HITL requests from an activity result."""
    if result.activity_result and result.activity_result.get("pending_request_info_events"):
        for req_data in result.activity_result["pending_request_info_events"]:
            request_id = req_data.get("request_id")
            if request_id:
                pending_hitl_requests[request_id] = PendingHITLRequest(
                    request_id=request_id,
                    source_executor_id=req_data.get("source_executor_id", result.executor_id),
                    request_data=req_data.get("data"),
                    request_type=req_data.get("request_type"),
                    response_type=req_data.get("response_type"),
                )
                logger.debug(
                    "Collected HITL request %s from executor %s",
                    request_id,
                    result.executor_id,
                )


def _route_hitl_response(
    hitl_request: PendingHITLRequest,
    raw_response: Any,
    pending_messages: dict[str, list[tuple[Any, str]]],
) -> None:
    """Route a HITL response back to the source executor's @response_handler."""
    response_message = {
        "request_id": hitl_request.request_id,
        "original_request": hitl_request.request_data,
        "response": raw_response,
        "response_type": hitl_request.response_type,
    }

    target_id = hitl_request.source_executor_id
    if target_id not in pending_messages:
        pending_messages[target_id] = []

    source_id = f"{SOURCE_HITL_RESPONSE}_{hitl_request.request_id}"
    pending_messages[target_id].append((response_message, source_id))

    logger.debug(
        "Routed HITL response for request %s to executor %s",
        hitl_request.request_id,
        target_id,
    )


# ============================================================================
# Message Content Extraction
# ============================================================================


def _extract_message_content(message: Any) -> str:
    """Extract text content from various message types."""
    message_content = ""
    if isinstance(message, AgentExecutorResponse) and message.agent_response:
        if message.agent_response.text:
            message_content = message.agent_response.text
        elif message.agent_response.messages:
            message_content = message.agent_response.messages[-1].text or ""
    elif isinstance(message, AgentExecutorRequest) and message.messages:
        message_content = message.messages[-1].text or ""
    elif isinstance(message, dict):
        key_names = list(message.keys())  # type: ignore[union-attr]
        logger.warning("Unexpected dict message in _extract_message_content. Keys: %s", key_names)  # type: ignore
    elif isinstance(message, str):
        message_content = message
    return message_content


def _select_primary_input_type(executor: Executor) -> type | None:
    """Return the executor's primary concrete declared input type, if any.

    The first declared input type that is a concrete class is used; union or
    unannotated types yield ``None`` (the caller then passes the value through
    unchanged).
    """
    for input_type in executor.input_types:
        if isinstance(input_type, type):
            return input_type
    return None


def _try_unwrap_subworkflow_input(raw_value: Any) -> tuple[bool, Any]:
    """Detect and unwrap a sub-orchestration input marker.

    Returns ``(True, inner)`` when ``raw_value`` is the parent-supplied marker
    payload (see :data:`SUBWORKFLOW_INPUT_KEY`), with ``inner`` reconstructed from
    the wrapped, parent-serialized message. Returns ``(False, None)`` otherwise.

    Kept separate from :func:`_coerce_initial_input` so the ``isinstance`` narrowing
    here does not leak into that function's untyped ``raw_value`` coercion path.
    """
    if isinstance(raw_value, dict):
        marker_input = cast("dict[str, Any]", raw_value)
        if SUBWORKFLOW_INPUT_KEY in marker_input:
            return True, deserialize_value(marker_input[SUBWORKFLOW_INPUT_KEY])
    return False, None


def _coerce_initial_input(workflow: Workflow, raw_value: Any) -> Any:
    """Coerce the client's initial workflow input to the start executor's type.

    A durable workflow runs as a durable orchestration, so its initial payload
    arrives as plain JSON via ``context.get_input()`` -- without the type markers
    that inter-executor messages carry (those are reconstructed by
    :func:`deserialize_value`). This single entry hop therefore needs explicit
    reconstruction to mirror in-process delivery, where the start executor
    receives its declared type:

    * Agent start executors only consume text, so non-text input is stringified.
    * Other executors get their primary declared input type reconstructed
      (``dict`` -> Pydantic/dataclass, ``str`` -> ``str``, ...) via
      :func:`reconstruct_to_type`; union/unannotated types pass through unchanged.

    A sub-orchestration payload (a ``WorkflowExecutor`` invoking this workflow as a
    child) carries the node's message wrapped in :data:`SUBWORKFLOW_INPUT_KEY`. That
    is trusted internal data the parent produced with :func:`serialize_value`, so it
    is reconstructed directly to the original typed object -- mirroring the
    in-process ``WorkflowExecutor`` which passes its input straight to the inner
    workflow -- without the HTTP-boundary pickle-marker stripping.
    """
    unwrapped, inner_input = _try_unwrap_subworkflow_input(raw_value)
    if unwrapped:
        return inner_input

    start_executor = workflow.executors.get(workflow.start_executor_id)
    if start_executor is None:
        return raw_value

    if isinstance(start_executor, AgentExecutor):
        if isinstance(raw_value, str):
            return raw_value
        if isinstance(raw_value, (dict, list)):
            return json.dumps(raw_value)
        return str(raw_value)

    input_type = _select_primary_input_type(start_executor)
    if input_type is None:
        return raw_value
    # The initial payload is untrusted external input (HTTP body / client input) with no
    # legitimate checkpoint type markers, so neutralize any pickle-marker injection before
    # it can reach deserialize_value() inside reconstruct_to_type() (avoids pickle RCE).
    return reconstruct_to_type(strip_pickle_markers(raw_value), input_type)


# ============================================================================
# HITL Response Handler Execution
# ============================================================================


async def execute_hitl_response_handler(
    executor: Any,
    hitl_message: dict[str, Any],
    shared_state: State,
    runner_context: Any,
) -> None:
    """Execute a HITL response handler on an executor.

    Args:
        executor: The executor instance that has a @response_handler.
        hitl_message: The HITL response message dict.
        shared_state: The shared state for the workflow context.
        runner_context: The runner context for capturing outputs.
    """
    from agent_framework._workflows._workflow_context import WorkflowContext

    original_request_data = hitl_message.get("original_request")
    response_data = hitl_message.get("response")
    response_type_str = hitl_message.get("response_type")

    original_request = deserialize_value(original_request_data)
    response = _deserialize_hitl_response(response_data, response_type_str)

    handler = executor._find_response_handler(original_request, response)

    if handler is None:
        logger.warning(
            "No response handler found for HITL response in executor %s. Request type: %s, Response type: %s",
            executor.id,
            type(original_request).__name__,
            type(response).__name__,
        )
        return

    ctx = WorkflowContext(
        executor=executor,
        source_executor_ids=[SOURCE_HITL_RESPONSE],
        runner_context=runner_context,
        state=shared_state,
    )

    logger.debug(
        "Invoking response handler for HITL request in executor %s",
        executor.id,
    )
    await handler(response, ctx)


def _deserialize_hitl_response(response_data: Any, response_type_str: str | None) -> Any:
    """Deserialize a HITL response to its expected type."""
    logger.debug(
        "Deserializing HITL response. response_type_str=%s, response_data type=%s",
        response_type_str,
        type(response_data).__name__,
    )

    if response_data is None:
        return None

    response_data = strip_pickle_markers(response_data)
    if response_data is None:
        return None

    if not isinstance(response_data, dict):
        logger.debug("Response data is not a dict, returning as-is: %s", type(response_data).__name__)
        return response_data

    if response_type_str:
        response_type = resolve_type(response_type_str)
        if response_type:
            logger.debug("Found response type %s, attempting reconstruction", response_type)
            result = reconstruct_to_type(response_data, response_type)
            logger.debug("Reconstructed response type: %s", type(result).__name__)
            return result
        logger.warning("Could not resolve response type: %s", response_type_str)

    logger.debug("No type hint; returning sanitized data as-is")
    return response_data  # type: ignore[reportUnknownVariableType]


# ============================================================================
# Task Preparation (All Tasks)
# ============================================================================


def _prepare_all_tasks(
    ctx: WorkflowOrchestrationContext,
    workflow: Workflow,
    pending_messages: dict[str, list[tuple[Any, str]]],
    shared_state: dict[str, Any] | None,
    depth: int,
    subworkflow_counter: list[int],
) -> tuple[list[Any], list[TaskMetadata], list[tuple[str, Any, str]]]:
    """Prepare all pending tasks for parallel execution.

    Groups agent messages by executor ID so that only the first message per agent
    runs in the parallel batch.  Additional messages to the same agent are returned
    for sequential processing. A :class:`~agent_framework.WorkflowExecutor` node is
    dispatched as a durable child orchestration (one per message), with a
    deterministic child instance id derived from the parent so replay is stable.

    Args:
        ctx: The orchestration context used to schedule activities, entity calls,
            and child orchestrations.
        workflow: The workflow whose executors are being dispatched.
        pending_messages: Messages to deliver this superstep, grouped by target
            executor id, each paired with its source executor id.
        shared_state: Optional dict for cross-executor state sharing.
        depth: This orchestration's sub-workflow nesting depth, propagated to child
            orchestrations so recursion can be bounded.
        subworkflow_counter: A single-element mutable counter, persistent across
            supersteps, used to derive unique deterministic child instance ids.
    """
    all_tasks: list[Any] = []
    task_metadata_list: list[TaskMetadata] = []
    remaining_agent_messages: list[tuple[str, Any, str]] = []

    agent_messages_by_executor: dict[str, list[tuple[str, Any, str]]] = defaultdict(list)

    for executor_id, messages_with_sources in pending_messages.items():
        executor = workflow.executors[executor_id]
        is_agent = isinstance(executor, AgentExecutor)
        is_subworkflow = isinstance(executor, WorkflowExecutor)

        for message, source_executor_id in messages_with_sources:
            if is_agent:
                agent_messages_by_executor[executor_id].append((executor_id, message, source_executor_id))
            elif is_subworkflow:
                # Derive a deterministic, globally-unique child instance id. The counter
                # persists across supersteps, so two invocations of the same node (in the
                # same or different supersteps, e.g. fan-out) never collide, and the ids
                # are stable across orchestration replay.
                child_instance_id = f"{ctx.instance_id}::{executor_id}::{subworkflow_counter[0]}"
                subworkflow_counter[0] += 1
                logger.debug("Preparing sub-workflow task: %s -> %s", executor_id, child_instance_id)
                task = _prepare_subworkflow_task(ctx, executor, message, child_instance_id, depth)
                all_tasks.append(task)
                task_metadata_list.append(
                    TaskMetadata(
                        executor_id=executor_id,
                        message=message,
                        source_executor_id=source_executor_id,
                        task_type=TaskType.SUBWORKFLOW,
                        child_instance_id=child_instance_id,
                    )
                )
            else:
                logger.debug("Preparing activity task: %s", executor_id)
                task = _prepare_activity_task(
                    ctx, executor_id, message, source_executor_id, shared_state, workflow.name
                )
                all_tasks.append(task)
                task_metadata_list.append(
                    TaskMetadata(
                        executor_id=executor_id,
                        message=message,
                        source_executor_id=source_executor_id,
                        task_type=TaskType.ACTIVITY,
                    )
                )

    for executor_id, messages_list in agent_messages_by_executor.items():
        first_msg = messages_list[0]
        remaining = messages_list[1:]

        logger.debug("Preparing agent task: %s", executor_id)
        task = _prepare_agent_task(ctx, first_msg[0], first_msg[1], workflow.name)
        all_tasks.append(task)
        task_metadata_list.append(
            TaskMetadata(
                executor_id=first_msg[0],
                message=first_msg[1],
                source_executor_id=first_msg[2],
                task_type=TaskType.AGENT,
            )
        )

        remaining_agent_messages.extend(remaining)

    return all_tasks, task_metadata_list, remaining_agent_messages


# ============================================================================
# Main Orchestrator
# ============================================================================


def run_workflow_orchestrator(
    ctx: WorkflowOrchestrationContext,
    workflow: Workflow,
    initial_message: Any,
    shared_state: dict[str, Any] | None = None,
) -> Generator[Any, Any, list[Any]]:
    """Traverse and execute the workflow graph as a durable orchestration.

    This is a generator-based orchestrator that works with any host by
    programming against the :class:`WorkflowOrchestrationContext` protocol.

    Supports:
    - SingleEdgeGroup: Direct 1:1 routing with optional condition
    - SwitchCaseEdgeGroup: First matching condition wins
    - FanOutEdgeGroup: Broadcast to multiple targets (parallel execution)
    - FanInEdgeGroup: Aggregates messages from multiple sources
    - SharedState: Cross-executor state sharing (local to orchestration)
    - HITL: Human-in-the-loop via request_info / @response_handler

    Args:
        ctx: Host-specific orchestration context adapter.
        workflow: The MAF Workflow instance to execute.
        initial_message: Initial message to send to the start executor. When this
            workflow runs as a sub-workflow, this is the parent-supplied marker
            payload (see :data:`SUBWORKFLOW_INPUT_KEY`), which also carries the
            nesting depth.
        shared_state: Optional dict for cross-executor state sharing.

    Returns:
        List of workflow outputs collected from executor activities.
    """
    # When invoked as a child orchestration, the initial payload carries the nesting
    # depth; bound recursion so mutually-nested workflows cannot spawn unbounded
    # child orchestrations. (Top-level runs start at depth 0.)
    depth = 0
    if isinstance(initial_message, dict) and SUBWORKFLOW_INPUT_KEY in initial_message:
        marker = cast("dict[str, Any]", initial_message)
        depth = int(marker.get(SUBWORKFLOW_DEPTH_KEY, 0) or 0)
        if depth > MAX_SUBWORKFLOW_DEPTH:
            raise RuntimeError(
                f"Sub-workflow nesting exceeded the maximum depth of {MAX_SUBWORKFLOW_DEPTH} "
                f"(workflow '{workflow.name}'). Check for mutually-nested workflows."
            )

    pending_messages: dict[str, list[tuple[Any, str]]] = {
        workflow.start_executor_id: [(_coerce_initial_input(workflow, initial_message), SOURCE_WORKFLOW_START)]
    }
    workflow_outputs: list[Any] = []
    iteration = 0

    # Monotonic, replay-stable counter for deriving child orchestration instance ids;
    # persists across supersteps so repeated sub-workflow invocations never collide.
    subworkflow_counter: list[int] = [0]

    # Accumulate workflow events and publish them to the orchestration custom status
    # after each superstep so an external client can stream progress by polling.
    # Non-agent executors are run inside a durable activity that captures their events
    # with data payloads (replayed via append_activity_events); agents contribute only
    # synthesized invoked/completed lifecycle events. Events are per executor / per
    # yielded output, not token-level, and accumulate for the run.
    #
    # Only hosts that stream this timeline (ctx.supports_event_streaming) accumulate
    # and publish it. The Azure Functions host opts out: its custom status is capped
    # at 16 KB and it has no event-streaming endpoint, so accumulating the log would
    # only grow orchestrator memory and overflow the cap on publish.
    live_events: list[dict[str, Any]] = []

    def emit_event(event_type: str, executor_id: str) -> None:
        if not ctx.supports_event_streaming:
            return
        live_events.append({"type": event_type, "executor_id": executor_id, "iteration": iteration})

    def append_activity_events(activity_result: dict[str, Any] | None) -> None:
        # Replay the events captured inside the activity, tagging each with the current
        # superstep iteration so clients can group events by superstep.
        if not ctx.supports_event_streaming or not activity_result:
            return
        captured = activity_result.get("events")
        if not isinstance(captured, list):
            return
        for serialized_event in cast("list[dict[str, Any]]", captured):
            enriched = dict(serialized_event)
            enriched["iteration"] = iteration
            live_events.append(enriched)

    def publish_live_status(
        state: str,
        pending_requests: dict[str, Any] | None = None,
        subworkflows: dict[str, str] | None = None,
    ) -> None:
        # Publish only on live execution so events are not re-emitted on replay
        # (the custom status set during the first execution already persisted).
        if ctx.is_replaying:
            return
        status: dict[str, Any] = {"state": state}
        # Hosts that don't stream the event timeline (e.g. Azure Functions, whose
        # custom status is 16 KB-capped) omit the events key entirely, preserving the
        # compact {state, pending_requests} status those hosts expect.
        if ctx.supports_event_streaming:
            status["events"] = live_events
        if pending_requests is not None:
            status["pending_requests"] = pending_requests
        # Map of {executorId: childInstanceId} for sub-workflows dispatched this
        # superstep. The parent is suspended in task_all while a child waits for human
        # input, so recording the child ids here lets the read side discover and
        # qualify nested pending requests (B2 single-surface HITL).
        if subworkflows:
            status["subworkflows"] = subworkflows
        ctx.set_custom_status(status)

    fan_in_pending: dict[str, dict[str, list[tuple[Any, str]]]] = {
        group.id: defaultdict(list) for group in workflow.edge_groups if isinstance(group, FanInEdgeGroup)
    }

    pending_hitl_requests: dict[str, PendingHITLRequest] = {}

    while pending_messages and iteration < workflow.max_iterations:
        logger.debug("Orchestrator iteration %d", iteration)
        next_pending_messages: dict[str, list[tuple[Any, str]]] = {}

        # Phase 1: Prepare all tasks
        all_tasks, task_metadata_list, remaining_agent_messages = _prepare_all_tasks(
            ctx, workflow, pending_messages, shared_state, depth, subworkflow_counter
        )

        # Agents and sub-workflows bypass the per-executor activity, so synthesize their
        # invoked event here; activity executors emit their own events from inside the
        # activity.
        for task_meta in task_metadata_list:
            if task_meta.task_type in (TaskType.AGENT, TaskType.SUBWORKFLOW):
                emit_event("executor_invoked", task_meta.executor_id)
        for invoked_executor_id, _invoked_message, _invoked_source in remaining_agent_messages:
            emit_event("executor_invoked", invoked_executor_id)

        # Phase 2: Execute all tasks in parallel
        all_results: list[ExecutorResult] = []
        if all_tasks:
            logger.debug("Executing %d tasks in parallel (agents + activities)", len(all_tasks))
            # Record dispatched sub-workflow child instance ids before suspending in
            # task_all. While a nested sub-workflow waits for human input, this parent
            # stays suspended here, so its custom status must already carry the child
            # ids for the read side to discover and qualify nested pending requests.
            active_subworkflows = {
                meta.executor_id: meta.child_instance_id
                for meta in task_metadata_list
                if meta.task_type == TaskType.SUBWORKFLOW and meta.child_instance_id is not None
            }
            if active_subworkflows:
                publish_live_status("running", subworkflows=active_subworkflows)
            raw_results = yield ctx.task_all(all_tasks)
            logger.debug("All %d tasks completed", len(all_tasks))

            for idx, raw_result in enumerate(raw_results):
                metadata = task_metadata_list[idx]
                if metadata.task_type == TaskType.AGENT:
                    result = _process_agent_response(raw_result, metadata.executor_id, metadata.message)
                    emit_event("executor_completed", metadata.executor_id)
                elif metadata.task_type == TaskType.SUBWORKFLOW:
                    subworkflow_executor = cast(WorkflowExecutor, workflow.executors[metadata.executor_id])
                    result = _process_subworkflow_result(raw_result, subworkflow_executor, workflow_outputs)
                    emit_event("executor_completed", metadata.executor_id)
                else:
                    result = _process_activity_result(raw_result, metadata.executor_id, shared_state, workflow_outputs)
                    append_activity_events(result.activity_result)
                all_results.append(result)

        # Phase 3: Process sequential agent messages
        for executor_id, message, _source_executor_id in remaining_agent_messages:
            logger.debug("Processing sequential message for agent: %s", executor_id)
            task = _prepare_agent_task(ctx, executor_id, message, workflow.name)
            agent_response: AgentResponse = yield task
            logger.debug("Agent %s sequential response completed", executor_id)

            result = _process_agent_response(agent_response, executor_id, message)
            all_results.append(result)
            emit_event("executor_completed", executor_id)

        # Phase 4: Collect HITL requests
        for result in all_results:
            _collect_hitl_requests(result, pending_hitl_requests)

        # Phase 5: Route results
        for result in all_results:
            _route_result_messages(result, workflow, next_pending_messages, fan_in_pending)

        # Phase 6: Check fan-in readiness
        _check_fan_in_ready(workflow, fan_in_pending, next_pending_messages)

        pending_messages = next_pending_messages

        # Publish accumulated events after each superstep. When the workflow is about
        # to pause for human input, the HITL block below publishes the waiting status
        # with the pending requests instead.
        if pending_messages or not pending_hitl_requests:
            publish_live_status("running")

        # Phase 7: HITL wait
        if not pending_messages and pending_hitl_requests:
            logger.debug("Workflow paused for HITL - %d pending requests", len(pending_hitl_requests))

            publish_live_status(
                "waiting_for_human_input",
                pending_requests={
                    req_id: {
                        "request_id": req.request_id,
                        "source_executor_id": req.source_executor_id,
                        "data": req.request_data,
                        "request_type": req.request_type,
                        "response_type": req.response_type,
                    }
                    for req_id, req in pending_hitl_requests.items()
                },
            )

            for request_id, hitl_request in list(pending_hitl_requests.items()):
                # Wait indefinitely for the human response, matching MAF core's
                # request_info (and the .NET durable host); the durable orchestration
                # simply stays paused until a response arrives. A payload rejected by
                # sanitization (pickle/type markers) does not consume the request, so
                # the caller can resubmit a corrected response.
                while True:
                    logger.debug("Waiting for HITL response for request: %s", request_id)

                    raw_response = yield ctx.wait_for_external_event(request_id)
                    logger.debug(
                        "Received HITL response for request %s. Type: %s, Value: %s",
                        request_id,
                        type(raw_response).__name__,
                        raw_response,
                    )

                    if isinstance(raw_response, str):
                        try:
                            raw_response = json.loads(raw_response)
                            logger.debug("Parsed JSON string response to: %s", type(raw_response).__name__)
                        except (json.JSONDecodeError, TypeError):
                            logger.debug("Response is not JSON, keeping as string")

                    # Sanitize against pickle-marker injection in case a caller bypassed
                    # DurableWorkflowClient.send_hitl_response and raised the external
                    # event directly (e.g. via the raw DTS client). Sanitize *before*
                    # consuming the request so a rejected payload can be resubmitted.
                    sanitized_response = strip_pickle_markers(raw_response)
                    if sanitized_response is None and raw_response is not None:
                        logger.warning(
                            "Rejected HITL response for request %s: payload contained "
                            "disallowed pickle/type markers. Awaiting a new response.",
                            request_id,
                        )
                        continue

                    del pending_hitl_requests[request_id]
                    _route_hitl_response(
                        hitl_request,
                        sanitized_response,
                        pending_messages,
                    )
                    break

            publish_live_status("running")

        iteration += 1

    # Match the core WorkflowRunner: if the loop stopped because max_iterations
    # was reached while messages are still pending, the workflow did not converge.
    if pending_messages:
        raise WorkflowConvergenceException(f"Workflow did not converge after {workflow.max_iterations} iterations.")

    return workflow_outputs  # noqa: B901
