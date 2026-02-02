# Copyright (c) Microsoft. All rights reserved.

"""Workflow Execution for Durable Functions.

This module provides the workflow orchestration engine that executes MAF Workflows
using Azure Durable Functions. It reuses MAF's edge group routing logic while
adapting execution to the DF generator-based model (yield instead of await).

Key components:
- run_workflow_orchestrator: Main orchestration function for workflow execution
- route_message_through_edge_groups: Routing helper using MAF edge group APIs
- build_agent_executor_response: Helper to construct AgentExecutorResponse

HITL (Human-in-the-Loop) Support:
- Detects pending RequestInfoEvents from executor activities
- Uses wait_for_external_event to pause for human input
- Routes responses back to executor's @response_handler methods
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import timedelta
from enum import Enum
from typing import Any

from agent_framework import (
    AgentExecutor,
    AgentExecutorRequest,
    AgentExecutorResponse,
    AgentResponse,
    ChatMessage,
    Workflow,
)
from agent_framework._workflows._edge import (
    EdgeGroup,
    FanInEdgeGroup,
    FanOutEdgeGroup,
    SingleEdgeGroup,
    SwitchCaseEdgeGroup,
)
from agent_framework_durabletask import AgentSessionId, DurableAgentThread, DurableAIAgent
from azure.durable_functions import DurableOrchestrationContext

from ._orchestration import AzureFunctionsAgentExecutor
from ._utils import deserialize_value, serialize_message

logger = logging.getLogger(__name__)


# ============================================================================
# Task Types and Data Structures
# ============================================================================


class TaskType(Enum):
    """Type of executor task."""

    AGENT = "agent"
    ACTIVITY = "activity"


@dataclass
class TaskMetadata:
    """Metadata for a pending task."""

    executor_id: str
    message: Any
    source_executor_id: str
    task_type: TaskType
    remaining_messages: list[tuple[str, Any, str]] | None = None  # For agents with multiple messages


@dataclass
class ExecutorResult:
    """Result from executing an agent or activity."""

    executor_id: str
    output_message: AgentExecutorResponse | None
    activity_result: dict[str, Any] | None
    task_type: TaskType


@dataclass
class PendingHITLRequest:
    """Tracks a pending Human-in-the-Loop request in the orchestrator.

    Attributes:
        request_id: Unique identifier for correlation with external events
        source_executor_id: The executor that called ctx.request_info()
        request_data: The serialized request payload
        request_type: Fully qualified type name of the request data
        response_type: Fully qualified type name of expected response
    """

    request_id: str
    source_executor_id: str
    request_data: Any
    request_type: str | None
    response_type: str | None


# Default timeout for HITL requests (72 hours)
DEFAULT_HITL_TIMEOUT_HOURS = 72.0


# ============================================================================
# Routing Functions
# ============================================================================


def _evaluate_edge_condition_sync(edge: Any, message: Any) -> bool:
    """Evaluate an edge's condition synchronously.

    This is needed because Durable Functions orchestrators use generators,
    not async/await, so we cannot call async methods like edge.should_route().

    Args:
        edge: The Edge object with a _condition attribute
        message: The message to evaluate against the condition

    Returns:
        True if the edge should be traversed, False otherwise
    """
    # Access the internal condition directly since should_route is async
    condition = getattr(edge, "_condition", None)
    if condition is None:
        return True
    result = condition(message)
    # If the condition is async, we cannot await it in a generator context
    # Log a warning and assume True (or False for safety)
    if hasattr(result, "__await__"):
        import warnings

        warnings.warn(
            f"Edge condition for {edge.source_id}->{edge.target_id} is async, "
            "which is not supported in Durable Functions orchestrators. "
            "The edge will be traversed unconditionally.",
            RuntimeWarning,
            stacklevel=2,
        )
        return True
    return bool(result)


def route_message_through_edge_groups(
    edge_groups: list[EdgeGroup],
    source_id: str,
    message: Any,
) -> list[str]:
    """Route a message through edge groups to find target executor IDs.

    Delegates to MAF's edge group routing logic instead of manual inspection.

    Args:
        edge_groups: List of EdgeGroup instances from the workflow
        source_id: The ID of the source executor
        message: The message to route

    Returns:
        List of target executor IDs that should receive the message
    """
    targets: list[str] = []

    for group in edge_groups:
        if source_id not in group.source_executor_ids:
            continue

        # SwitchCaseEdgeGroup and FanOutEdgeGroup use selection_func
        if isinstance(group, (SwitchCaseEdgeGroup, FanOutEdgeGroup)):
            if group.selection_func is not None:
                selected = group.selection_func(message, group.target_executor_ids)
                targets.extend(selected)
            else:
                # No selection func means broadcast to all targets
                targets.extend(group.target_executor_ids)

        elif isinstance(group, SingleEdgeGroup):
            # SingleEdgeGroup has exactly one edge
            edge = group.edges[0]
            if _evaluate_edge_condition_sync(edge, message):
                targets.append(edge.target_id)

        elif isinstance(group, FanInEdgeGroup):
            # FanIn is handled separately in the orchestrator loop
            # since it requires aggregation
            pass

        else:
            # Generic EdgeGroup: check each edge's condition
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
    """Build an AgentExecutorResponse from entity response data.

    Shared helper to construct the response object consistently.

    Args:
        executor_id: The ID of the executor that produced the response
        response_text: Plain text response from the agent (if any)
        structured_response: Structured JSON response (if any)
        previous_message: The input message that triggered this response

    Returns:
        AgentExecutorResponse with reconstructed conversation
    """
    final_text = response_text
    if structured_response:
        final_text = json.dumps(structured_response)

    assistant_message = ChatMessage(role="assistant", text=final_text)

    agent_response = AgentResponse(
        messages=[assistant_message],
    )

    # Build conversation history
    full_conversation: list[ChatMessage] = []
    if isinstance(previous_message, AgentExecutorResponse) and previous_message.full_conversation:
        full_conversation.extend(previous_message.full_conversation)
    elif isinstance(previous_message, str):
        full_conversation.append(ChatMessage(role="user", text=previous_message))

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
    context: DurableOrchestrationContext,
    executor_id: str,
    message: Any,
) -> Any:
    """Prepare an agent task for execution.

    Args:
        context: The Durable Functions orchestration context
        executor_id: The agent executor ID (agent name)
        message: The input message for the agent

    Returns:
        A task that can be yielded to execute the agent
    """
    message_content = _extract_message_content(message)
    session_id = AgentSessionId(name=executor_id, key=context.instance_id)
    thread = DurableAgentThread(session_id=session_id)

    az_executor = AzureFunctionsAgentExecutor(context)
    agent = DurableAIAgent(az_executor, executor_id)
    return agent.run(message_content, thread=thread)


def _prepare_activity_task(
    context: DurableOrchestrationContext,
    executor_id: str,
    message: Any,
    source_executor_id: str,
    shared_state_snapshot: dict[str, Any] | None,
) -> Any:
    """Prepare an activity task for execution.

    Args:
        context: The Durable Functions orchestration context
        executor_id: The activity executor ID
        message: The input message for the activity
        source_executor_id: The ID of the executor that sent the message
        shared_state_snapshot: Current shared state snapshot

    Returns:
        A task that can be yielded to execute the activity
    """
    activity_input = {
        "executor_id": executor_id,
        "message": serialize_message(message),
        "shared_state_snapshot": shared_state_snapshot,
        "source_executor_ids": [source_executor_id],
    }
    activity_input_json = json.dumps(activity_input)
    # Use the prefixed activity name that matches the registered function
    activity_name = f"dafx-{executor_id}"
    return context.call_activity(activity_name, activity_input_json)


# ============================================================================
# Result Processing Helpers
# ============================================================================


def _process_agent_response(
    agent_response: AgentResponse,
    executor_id: str,
    message: Any,
) -> ExecutorResult:
    """Process an agent response into an ExecutorResult.

    Args:
        agent_response: The response from the agent
        executor_id: The agent executor ID
        message: The original input message

    Returns:
        ExecutorResult containing the processed response
    """
    response_text = agent_response.text if agent_response else None
    structured_response = None

    if agent_response and agent_response.value is not None:
        if hasattr(agent_response.value, "model_dump"):
            structured_response = agent_response.value.model_dump()
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
    """Process an activity result and apply shared state updates.

    Args:
        result_json: The JSON result from the activity
        executor_id: The activity executor ID
        shared_state: The shared state dict to update (mutated in place)
        workflow_outputs: List to append outputs to (mutated in place)

    Returns:
        ExecutorResult containing the processed result
    """
    result = json.loads(result_json) if result_json else None

    # Apply shared state updates
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

    # Collect outputs
    if result and result.get("outputs"):
        workflow_outputs.extend(result["outputs"])

    return ExecutorResult(
        executor_id=executor_id,
        output_message=None,
        activity_result=result,
        task_type=TaskType.ACTIVITY,
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
    """Route messages from an executor result to their targets.

    Args:
        result: The executor result containing messages to route
        workflow: The workflow definition
        next_pending_messages: Dict to accumulate next iteration's messages (mutated)
        fan_in_pending: Dict tracking fan-in state (mutated)
    """
    executor_id = result.executor_id
    messages_to_route: list[tuple[Any, str | None]] = []

    # Collect messages from agent response
    if result.output_message:
        messages_to_route.append((result.output_message, None))

    # Collect sent_messages from activity results
    if result.activity_result and result.activity_result.get("sent_messages"):
        for msg_data in result.activity_result["sent_messages"]:
            sent_msg = msg_data.get("message")
            target_id = msg_data.get("target_id")
            if sent_msg:
                sent_msg = deserialize_value(sent_msg)
                messages_to_route.append((sent_msg, target_id))

    # Route each message
    for msg_to_route, explicit_target in messages_to_route:
        logger.debug("Routing output from %s", executor_id)

        # If explicit target specified, route directly
        if explicit_target:
            if explicit_target not in next_pending_messages:
                next_pending_messages[explicit_target] = []
            next_pending_messages[explicit_target].append((msg_to_route, executor_id))
            logger.debug("Routed message from %s to explicit target %s", executor_id, explicit_target)
            continue

        # Check for FanInEdgeGroup sources
        for group in workflow.edge_groups:
            if isinstance(group, FanInEdgeGroup) and executor_id in group.source_executor_ids:
                fan_in_pending[group.id][executor_id].append((msg_to_route, executor_id))
                logger.debug("Accumulated message for FanIn group %s from %s", group.id, executor_id)

        # Use MAF's edge group routing for other edge types
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
    """Check if any FanInEdgeGroups are ready and deliver their messages.

    Args:
        workflow: The workflow definition
        fan_in_pending: Dict tracking fan-in state (mutated - cleared when delivered)
        next_pending_messages: Dict to add aggregated messages to (mutated)
    """
    for group in workflow.edge_groups:
        if not isinstance(group, FanInEdgeGroup):
            continue

        pending_sources = fan_in_pending.get(group.id, {})

        # Check if all sources have contributed at least one message
        if not all(src in pending_sources and pending_sources[src] for src in group.source_executor_ids):
            continue

        # Aggregate all messages into a single list
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

        # Clear the pending sources for this group
        fan_in_pending[group.id] = defaultdict(list)


# ============================================================================
# HITL (Human-in-the-Loop) Helpers
# ============================================================================


def _collect_hitl_requests(
    result: ExecutorResult,
    pending_hitl_requests: dict[str, PendingHITLRequest],
) -> None:
    """Collect pending HITL requests from an activity result.

    Args:
        result: The executor result that may contain pending request info events
        pending_hitl_requests: Dict to accumulate pending requests (mutated)
    """
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
    """Route a HITL response back to the source executor's @response_handler.

    The response is packaged as a special HITL response message that the executor
    activity can recognize and route to the appropriate @response_handler method.

    Args:
        hitl_request: The original HITL request
        raw_response: The raw response data from the external event
        pending_messages: Dict to add the response message to (mutated)
    """
    # Create a message structure that the executor can recognize
    # This mimics what the InProcRunnerContext does for request_info responses
    response_message = {
        "__hitl_response__": True,
        "request_id": hitl_request.request_id,
        "original_request": hitl_request.request_data,
        "response": raw_response,
        "response_type": hitl_request.response_type,
    }

    target_id = hitl_request.source_executor_id
    if target_id not in pending_messages:
        pending_messages[target_id] = []

    # Use a special source ID to indicate this is a HITL response
    source_id = f"__hitl_response__{hitl_request.request_id}"
    pending_messages[target_id].append((response_message, source_id))

    logger.debug(
        "Routed HITL response for request %s to executor %s",
        hitl_request.request_id,
        target_id,
    )


# ============================================================================
# Main Orchestrator
# ============================================================================


def run_workflow_orchestrator(
    context: DurableOrchestrationContext,
    workflow: Workflow,
    initial_message: Any,
    shared_state: dict[str, Any] | None = None,
    hitl_timeout_hours: float = DEFAULT_HITL_TIMEOUT_HOURS,
):
    """Traverse and execute the workflow graph using Durable Functions.

    This orchestrator reuses MAF's edge group routing logic while adapting
    execution to the DF generator-based model (yield instead of await).

    Supports:
    - SingleEdgeGroup: Direct 1:1 routing with optional condition
    - SwitchCaseEdgeGroup: First matching condition wins
    - FanOutEdgeGroup: Broadcast to multiple targets - **executed in parallel**
    - FanInEdgeGroup: Aggregates messages from multiple sources before delivery
    - SharedState: Local shared state accessible to all executors
    - HITL: Human-in-the-loop via request_info / @response_handler pattern

    Execution model:
    - All pending executors (agents AND activities) run in parallel via single task_all()
    - Multiple messages to the SAME agent are processed sequentially for conversation coherence
    - SharedState updates are applied in order after parallel tasks complete
    - HITL requests pause the orchestration until external events are received

    Args:
        context: The Durable Functions orchestration context
        workflow: The MAF Workflow instance to execute
        initial_message: The initial message to send to the start executor
        shared_state: Optional dict for cross-executor state sharing (local to orchestration)
        hitl_timeout_hours: Timeout in hours for HITL requests (default: 72 hours)

    Returns:
        List of workflow outputs collected from executor activities
    """
    pending_messages: dict[str, list[tuple[Any, str]]] = {
        workflow.start_executor_id: [(initial_message, "__workflow_start__")]
    }
    workflow_outputs: list[Any] = []
    iteration = 0

    # Track pending sources for FanInEdgeGroups using defaultdict for cleaner access
    fan_in_pending: dict[str, dict[str, list[tuple[Any, str]]]] = {
        group.id: defaultdict(list) for group in workflow.edge_groups if isinstance(group, FanInEdgeGroup)
    }

    # Track pending HITL requests
    pending_hitl_requests: dict[str, PendingHITLRequest] = {}

    while pending_messages and iteration < workflow.max_iterations:
        logger.debug("Orchestrator iteration %d", iteration)
        next_pending_messages: dict[str, list[tuple[Any, str]]] = {}

        # Phase 1: Prepare all tasks (agents and activities unified)
        all_tasks, task_metadata_list, remaining_agent_messages = _prepare_all_tasks(
            context, workflow, pending_messages, shared_state
        )

        # Phase 2: Execute all tasks in parallel (single task_all for true parallelism)
        all_results: list[ExecutorResult] = []
        if all_tasks:
            logger.debug("Executing %d tasks in parallel (agents + activities)", len(all_tasks))
            raw_results = yield context.task_all(all_tasks)
            logger.debug("All %d tasks completed", len(all_tasks))

            # Process results based on task type
            for idx, raw_result in enumerate(raw_results):
                metadata = task_metadata_list[idx]
                if metadata.task_type == TaskType.AGENT:
                    result = _process_agent_response(raw_result, metadata.executor_id, metadata.message)
                else:
                    result = _process_activity_result(raw_result, metadata.executor_id, shared_state, workflow_outputs)
                all_results.append(result)

        # Phase 3: Process sequential agent messages (for same-agent conversation coherence)
        for executor_id, message, _source_executor_id in remaining_agent_messages:
            logger.debug("Processing sequential message for agent: %s", executor_id)
            task = _prepare_agent_task(context, executor_id, message)
            agent_response: AgentResponse = yield task
            logger.debug("Agent %s sequential response completed", executor_id)

            result = _process_agent_response(agent_response, executor_id, message)
            all_results.append(result)

        # Phase 4: Collect pending HITL requests from activity results
        for result in all_results:
            _collect_hitl_requests(result, pending_hitl_requests)

        # Phase 5: Route all results to next iteration
        for result in all_results:
            _route_result_messages(result, workflow, next_pending_messages, fan_in_pending)

        # Phase 6: Check if any FanInEdgeGroups are ready to deliver
        _check_fan_in_ready(workflow, fan_in_pending, next_pending_messages)

        pending_messages = next_pending_messages

        # Phase 7: Handle HITL - if no pending work but HITL requests exist, wait for responses
        if not pending_messages and pending_hitl_requests:
            logger.debug("Workflow paused for HITL - %d pending requests", len(pending_hitl_requests))

            # Update custom status to expose pending requests
            context.set_custom_status({
                "state": "waiting_for_human_input",
                "pending_requests": {
                    req_id: {
                        "request_id": req.request_id,
                        "source_executor_id": req.source_executor_id,
                        "data": req.request_data,
                        "request_type": req.request_type,
                        "response_type": req.response_type,
                    }
                    for req_id, req in pending_hitl_requests.items()
                },
            })

            # Wait for external events for each pending request
            # Process responses one at a time to maintain ordering
            for request_id, hitl_request in list(pending_hitl_requests.items()):
                logger.debug("Waiting for HITL response for request: %s", request_id)

                # Create tasks for approval and timeout
                approval_task = context.wait_for_external_event(request_id)
                timeout_task = context.create_timer(context.current_utc_datetime + timedelta(hours=hitl_timeout_hours))

                winner = yield context.task_any([approval_task, timeout_task])

                if winner == approval_task:
                    # Cancel the timeout
                    timeout_task.cancel()

                    # Get the response
                    raw_response = approval_task.result
                    logger.debug(
                        "Received HITL response for request %s. Type: %s, Value: %s",
                        request_id,
                        type(raw_response).__name__,
                        raw_response,
                    )

                    # Durable Functions may return a JSON string; parse it if so
                    if isinstance(raw_response, str):
                        try:
                            import json

                            raw_response = json.loads(raw_response)
                            logger.debug("Parsed JSON string response to: %s", type(raw_response).__name__)
                        except (json.JSONDecodeError, TypeError):
                            logger.debug("Response is not JSON, keeping as string")

                    # Remove from pending
                    del pending_hitl_requests[request_id]

                    # Route the response back to the source executor's @response_handler
                    _route_hitl_response(
                        hitl_request,
                        raw_response,
                        pending_messages,
                    )
                else:
                    # Timeout occurred
                    logger.warning("HITL request %s timed out after %s hours", request_id, hitl_timeout_hours)
                    raise TimeoutError(
                        f"Human-in-the-loop request '{request_id}' timed out after {hitl_timeout_hours} hours."
                    )

            # Clear custom status after HITL is resolved
            context.set_custom_status({"state": "running"})

        iteration += 1

    # Durable Functions runtime extracts return value from StopIteration
    return workflow_outputs  # noqa: B901


def _prepare_all_tasks(
    context: DurableOrchestrationContext,
    workflow: Workflow,
    pending_messages: dict[str, list[tuple[Any, str]]],
    shared_state: dict[str, Any] | None,
) -> tuple[list[Any], list[TaskMetadata], list[tuple[str, Any, str]]]:
    """Prepare all pending tasks for parallel execution.

    Groups agent messages by executor ID so that only the first message per agent
    runs in the parallel batch. Additional messages to the same agent are returned
    for sequential processing.

    Args:
        context: The Durable Functions orchestration context
        workflow: The workflow definition
        pending_messages: Messages pending for each executor
        shared_state: Current shared state snapshot

    Returns:
        Tuple of (tasks, metadata, remaining_agent_messages):
        - tasks: List of tasks ready for task_all()
        - metadata: TaskMetadata for each task (same order as tasks)
        - remaining_agent_messages: Agent messages requiring sequential processing
    """
    all_tasks: list[Any] = []
    task_metadata_list: list[TaskMetadata] = []
    remaining_agent_messages: list[tuple[str, Any, str]] = []

    # Group agent messages by executor_id for sequential handling of same-agent messages
    agent_messages_by_executor: dict[str, list[tuple[str, Any, str]]] = defaultdict(list)

    # Categorize all pending messages
    for executor_id, messages_with_sources in pending_messages.items():
        executor = workflow.executors[executor_id]
        is_agent = isinstance(executor, AgentExecutor)

        for message, source_executor_id in messages_with_sources:
            if is_agent:
                agent_messages_by_executor[executor_id].append((executor_id, message, source_executor_id))
            else:
                # Activity tasks can all run in parallel
                logger.debug("Preparing activity task: %s", executor_id)
                task = _prepare_activity_task(context, executor_id, message, source_executor_id, shared_state)
                all_tasks.append(task)
                task_metadata_list.append(
                    TaskMetadata(
                        executor_id=executor_id,
                        message=message,
                        source_executor_id=source_executor_id,
                        task_type=TaskType.ACTIVITY,
                    )
                )

    # Process agent messages: first message per agent goes to parallel batch
    for executor_id, messages_list in agent_messages_by_executor.items():
        first_msg = messages_list[0]
        remaining = messages_list[1:]

        logger.debug("Preparing agent task: %s", executor_id)
        task = _prepare_agent_task(context, first_msg[0], first_msg[1])
        all_tasks.append(task)
        task_metadata_list.append(
            TaskMetadata(
                executor_id=first_msg[0],
                message=first_msg[1],
                source_executor_id=first_msg[2],
                task_type=TaskType.AGENT,
            )
        )

        # Queue remaining messages for sequential processing
        remaining_agent_messages.extend(remaining)

    return all_tasks, task_metadata_list, remaining_agent_messages


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
        # Extract text from the last message in the request
        message_content = message.messages[-1].text or ""
    elif isinstance(message, dict):
        message_content = _extract_message_content_from_dict(message)
    elif isinstance(message, str):
        message_content = message

    return message_content


def _extract_message_content_from_dict(message: dict[str, Any]) -> str:
    """Extract text content from serialized message dictionaries."""
    message_content = ""

    if message.get("messages"):
        # AgentExecutorRequest dict - messages is a list of ChatMessage dicts
        last_msg = message["messages"][-1]
        if isinstance(last_msg, dict):
            # ChatMessage serialized via to_dict() has structure:
            # {"type": "chat_message", "contents": [{"type": "text", "text": "..."}], ...}
            if last_msg.get("contents"):
                first_content = last_msg["contents"][0]
                if isinstance(first_content, dict):
                    message_content = first_content.get("text") or ""
            # Fallback to direct text field if not in contents structure
            if not message_content:
                message_content = last_msg.get("text") or last_msg.get("_text") or ""
        elif hasattr(last_msg, "text"):
            message_content = last_msg.text or ""
    elif "agent_response" in message:
        # AgentExecutorResponse dict
        arr = message.get("agent_response", {})
        if isinstance(arr, dict):
            message_content = arr.get("text") or ""
            if not message_content and arr.get("messages"):
                last_msg = arr["messages"][-1]
                if isinstance(last_msg, dict):
                    # Check for contents structure first
                    if last_msg.get("contents"):
                        first_content = last_msg["contents"][0]
                        if isinstance(first_content, dict):
                            message_content = first_content.get("text") or ""
                    if not message_content:
                        message_content = last_msg.get("text") or last_msg.get("_text") or ""

    return message_content
