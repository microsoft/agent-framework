# Copyright (c) Microsoft. All rights reserved.

"""Workflow Execution for Durable Functions.

This module provides the workflow orchestration engine that executes MAF Workflows
using Azure Durable Functions. It reuses MAF's edge group routing logic while
adapting execution to the DF generator-based model (yield instead of await).

Key components:
- run_workflow_orchestrator: Main orchestration function for workflow execution
- route_message_through_edge_groups: Routing helper using MAF edge group APIs
- build_agent_executor_response: Helper to construct AgentExecutorResponse
"""

from __future__ import annotations

import json
import logging
from typing import Any

from agent_framework import (
    AgentExecutor,
    AgentExecutorRequest,
    AgentExecutorResponse,
    AgentRunResponse,
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
from ._shared_state import DurableSharedState
from ._utils import deserialize_value, serialize_message

logger = logging.getLogger(__name__)


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
            if edge.should_route(message):
                targets.append(edge.target_id)

        elif isinstance(group, FanInEdgeGroup):
            # FanIn is handled separately in the orchestrator loop
            # since it requires aggregation
            pass

        else:
            # Generic EdgeGroup: check each edge's condition
            for edge in group.edges:
                if edge.source_id == source_id and edge.should_route(message):
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

    agent_run_response = AgentRunResponse(
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
        agent_run_response=agent_run_response,
        full_conversation=full_conversation,
    )


def run_workflow_orchestrator(
    context: DurableOrchestrationContext,
    workflow: Workflow,
    initial_message: Any,
    shared_state: DurableSharedState | None = None,
):
    """Traverse and execute the workflow graph using Durable Functions.

    This orchestrator reuses MAF's edge group routing logic while adapting
    execution to the DF generator-based model (yield instead of await).

    Supports:
    - SingleEdgeGroup: Direct 1:1 routing with optional condition
    - SwitchCaseEdgeGroup: First matching condition wins
    - FanOutEdgeGroup: Broadcast to multiple targets - **executed in parallel**
    - FanInEdgeGroup: Aggregates messages from multiple sources before delivery
    - SharedState: Durable shared state accessible to all executors

    Execution model:
    - Different executors pending in the same iteration run in parallel
    - Agent executors (entities): Different agents run in parallel; multiple messages
      to the SAME agent are processed sequentially to maintain conversation coherence
    - Standard executors (activities): All batched and executed in parallel using task_all()

    Note: When running in parallel with shared state, updates are applied
    in order after all tasks complete. This may cause conflicts if multiple
    executors modify the same state keys.

    Args:
        context: The Durable Functions orchestration context
        workflow: The MAF Workflow instance to execute
        initial_message: The initial message to send to the start executor
        shared_state: Optional DurableSharedState for cross-executor state sharing

    Returns:
        List of workflow outputs collected from executor activities
    """
    # pending_messages stores {target_executor_id: [(message, source_executor_id), ...]}
    # This allows executors to know who sent them each message
    pending_messages: dict[str, list[tuple[Any, str]]] = {
        workflow.start_executor_id: [(initial_message, "__workflow_start__")]
    }
    iteration = 0
    max_iterations = workflow.max_iterations
    workflow_outputs: list[Any] = []

    # Track pending sources for FanInEdgeGroups.
    # Maps group_id to a dict of source_id to list of (message, source_executor_id) tuples.
    fan_in_pending: dict[str, dict[str, list[tuple[Any, str]]]] = {}

    # Initialize fan-in tracking for all FanInEdgeGroups
    for group in workflow.edge_groups:
        if isinstance(group, FanInEdgeGroup):
            fan_in_pending[group.id] = {}

    while pending_messages and iteration < max_iterations:
        logger.debug("Orchestrator iteration %d", iteration)
        next_pending_messages: dict[str, list[tuple[Any, str]]] = {}

        # Separate executors into agents (entities) and standard executors (activities)
        # Agents must be processed sequentially due to entity semantics
        # Activities can be processed in parallel
        agent_executor_tasks: list[tuple[str, Any, str]] = []  # (executor_id, message, source_id)
        activity_executor_tasks: list[tuple[str, Any, str]] = []  # (executor_id, message, source_id)

        for executor_id, messages_with_sources in pending_messages.items():
            executor = workflow.executors[executor_id]
            for message, source_executor_id in messages_with_sources:
                if isinstance(executor, AgentExecutor):
                    agent_executor_tasks.append((executor_id, message, source_executor_id))
                else:
                    activity_executor_tasks.append((executor_id, message, source_executor_id))

        # Results collected from all executor types
        # Structure: list of (executor_id, output_message, result_dict_or_none)
        all_results: list[tuple[str, Any | None, dict[str, Any] | None]] = []

        # Process Agent Executors (entities) in parallel when they are different agents
        # Messages to the SAME agent are processed sequentially to maintain conversation coherence
        if agent_executor_tasks:
            # Group tasks by executor_id (agent_name) - same agent needs sequential processing
            agent_groups: dict[str, list[tuple[str, Any, str]]] = {}
            for executor_id, message, source_executor_id in agent_executor_tasks:
                if executor_id not in agent_groups:
                    agent_groups[executor_id] = []
                agent_groups[executor_id].append((executor_id, message, source_executor_id))

            # Process groups - if only one message per agent, can run all in parallel
            # If multiple messages to same agent, need sequential within that agent

            # First pass: create tasks for the first message of each agent (parallel)
            agent_tasks = []
            agent_task_metadata = []  # (executor_id, message, source_executor_id, remaining_messages)

            for executor_id, messages_list in agent_groups.items():
                first_msg = messages_list[0]
                remaining = messages_list[1:]

                message = first_msg[1]
                source_executor_id = first_msg[2]

                agent_name = executor_id
                logger.debug("Preparing agent task for: %s", agent_name)

                message_content = _extract_message_content(message)
                session_id = AgentSessionId(name=agent_name, key=context.instance_id)
                thread = DurableAgentThread(session_id=session_id)

                az_executor = AzureFunctionsAgentExecutor(context)
                agent = DurableAIAgent(az_executor, agent_name)
                task = agent.run(message_content, thread=thread)

                agent_tasks.append(task)
                agent_task_metadata.append((executor_id, message, source_executor_id, remaining))

            # Execute first batch of agent tasks in parallel
            if agent_tasks:
                logger.debug("Executing %d agent tasks in parallel", len(agent_tasks))
                agent_responses = yield context.task_all(agent_tasks)
                logger.debug("All %d agent tasks completed", len(agent_tasks))

                # Process results and handle remaining messages for agents with multiple inputs
                remaining_to_process: list[tuple[str, Any, str]] = []

                for idx, agent_response in enumerate(agent_responses):
                    executor_id, message, source_executor_id, remaining = agent_task_metadata[idx]
                    logger.debug("Durable Entity %s returned: %s", executor_id, agent_response)

                    # Build AgentExecutorResponse from the typed AgentRunResponse
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

                    all_results.append((executor_id, output_message, None))

                    # Queue remaining messages for sequential processing
                    remaining_to_process.extend(remaining)

                # Process remaining messages sequentially (these are additional messages to same agent)
                for executor_id, message, _source_executor_id in remaining_to_process:
                    agent_name = executor_id
                    logger.debug("Processing additional message for agent: %s (sequential)", agent_name)

                    message_content = _extract_message_content(message)
                    session_id = AgentSessionId(name=agent_name, key=context.instance_id)
                    thread = DurableAgentThread(session_id=session_id)

                    az_executor = AzureFunctionsAgentExecutor(context)
                    agent = DurableAIAgent(az_executor, agent_name)
                    agent_response: AgentRunResponse = yield agent.run(message_content, thread=thread)
                    logger.debug("Durable Entity %s returned: %s", agent_name, agent_response)

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

                    all_results.append((executor_id, output_message, None))

        # Process Activity Executors in parallel
        if activity_executor_tasks:
            logger.debug("Processing %d activity executors in parallel", len(activity_executor_tasks))

            # Get shared state snapshot once before all activity executions (if shared_state is available)
            shared_state_snapshot: dict[str, Any] | None = None
            if shared_state:
                shared_state_snapshot = yield from shared_state.get_all()
                logger.debug("[workflow] SharedState snapshot for activities: %s", shared_state_snapshot)

            # Create all activity tasks without yielding (to enable parallel execution)
            activity_tasks = []
            task_metadata = []  # Track which task corresponds to which executor

            for executor_id, message, source_executor_id in activity_executor_tasks:
                logger.debug("Preparing activity task for executor: %s", executor_id)

                activity_input = {
                    "executor_id": executor_id,
                    "message": serialize_message(message),
                    "shared_state_snapshot": shared_state_snapshot,
                    "source_executor_ids": [source_executor_id],
                }

                # Create the task (don't yield yet - this enables parallelism)
                activity_input_json = json.dumps(activity_input)
                task = context.call_activity("ExecuteExecutor", activity_input_json)
                activity_tasks.append(task)
                task_metadata.append((executor_id, message, source_executor_id))

            # Execute all activities in parallel using task_all
            logger.debug("Executing %d activities in parallel", len(activity_tasks))
            results_json_list = yield context.task_all(activity_tasks)
            logger.debug("All %d activities completed", len(activity_tasks))

            # Process results and apply shared state updates
            # Note: When running in parallel, shared state updates may conflict
            # We apply them in order, but this is a limitation of parallel execution
            for idx, result_json in enumerate(results_json_list):
                executor_id, message, source_executor_id = task_metadata[idx]
                result = json.loads(result_json) if result_json else None
                logger.debug("Activity for executor %s returned", executor_id)

                # Apply any shared state updates from the activity result
                if shared_state and result:
                    if result.get("shared_state_updates"):
                        updates = result["shared_state_updates"]
                        logger.debug(
                            "[workflow] Applying SharedState updates from activity %s: %s", executor_id, updates
                        )
                        yield from shared_state.update(updates)
                    if result.get("shared_state_deletes"):
                        deletes = result["shared_state_deletes"]
                        logger.debug(
                            "[workflow] Applying SharedState deletes from activity %s: %s", executor_id, deletes
                        )
                        for key in deletes:
                            yield from shared_state.delete(key)

                # Collect outputs
                if result and result.get("outputs"):
                    workflow_outputs.extend(result["outputs"])

                # Add to results for routing
                all_results.append((executor_id, None, result))

        # Routing phase - process all results
        for executor_id, output_message, result in all_results:
            messages_to_route: list[tuple[Any, str | None]] = []

            if output_message:
                messages_to_route.append((output_message, None))

            # Also route sent_messages from activities
            if result and result.get("sent_messages"):
                for msg_data in result["sent_messages"]:
                    sent_msg = msg_data.get("message")
                    target_id = msg_data.get("target_id")
                    if sent_msg:
                        sent_msg = deserialize_value(sent_msg)
                        messages_to_route.append((sent_msg, target_id))

            for msg_to_route, explicit_target in messages_to_route:
                logger.debug("Routing output from %s", executor_id)

                # If explicit target specified, route directly
                if explicit_target:
                    if explicit_target not in next_pending_messages:
                        next_pending_messages[explicit_target] = []
                    next_pending_messages[explicit_target].append((msg_to_route, executor_id))
                    logger.debug("Routed message from %s to explicit target %s", executor_id, explicit_target)
                    continue

                # Check for FanInEdgeGroup sources first
                for group in workflow.edge_groups:
                    if isinstance(group, FanInEdgeGroup) and executor_id in group.source_executor_ids:
                        if executor_id not in fan_in_pending[group.id]:
                            fan_in_pending[group.id][executor_id] = []
                        fan_in_pending[group.id][executor_id].append((msg_to_route, executor_id))
                        logger.debug("Accumulated message for FanIn group %s from %s", group.id, executor_id)

                # Use MAF's edge group routing for other edge types
                targets = route_message_through_edge_groups(
                    workflow.edge_groups,
                    executor_id,
                    msg_to_route,
                )

                for target_id in targets:
                    logger.debug("Routing to %s", target_id)
                    if target_id not in next_pending_messages:
                        next_pending_messages[target_id] = []
                    next_pending_messages[target_id].append((msg_to_route, executor_id))

        # Check if any FanInEdgeGroups are ready to deliver
        for group in workflow.edge_groups:
            if isinstance(group, FanInEdgeGroup):
                pending_sources = fan_in_pending.get(group.id, {})
                # Check if all sources have contributed at least one message
                if all(src in pending_sources for src in group.source_executor_ids):
                    # Aggregate all messages into a single list (extract just the messages)
                    aggregated: list[Any] = []
                    aggregated_sources: list[str] = []
                    for src in group.source_executor_ids:
                        for msg, msg_source in pending_sources[src]:
                            aggregated.append(msg)
                            aggregated_sources.append(msg_source)

                    target_id = group.target_executor_ids[0]
                    logger.debug(
                        "FanIn group %s ready, delivering %d messages to %s", group.id, len(aggregated), target_id
                    )

                    if target_id not in next_pending_messages:
                        next_pending_messages[target_id] = []
                    # For fan-in, the aggregated list is the message, sources are all contributors
                    # Use first source as representative (or could join them)
                    first_source = aggregated_sources[0] if aggregated_sources else "__fan_in__"
                    next_pending_messages[target_id].append((aggregated, first_source))

                    # Clear the pending sources for this group
                    fan_in_pending[group.id] = {}

        pending_messages = next_pending_messages
        iteration += 1

    # Durable Functions runtime extracts return value from StopIteration
    return workflow_outputs  # noqa: B901


def _extract_message_content(message: Any) -> str:
    """Extract text content from various message types."""
    message_content = ""
    if isinstance(message, AgentExecutorResponse) and message.agent_run_response:
        if message.agent_run_response.text:
            message_content = message.agent_run_response.text
        elif message.agent_run_response.messages:
            message_content = message.agent_run_response.messages[-1].text or ""
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
    elif "agent_run_response" in message:
        # AgentExecutorResponse dict
        arr = message.get("agent_run_response", {})
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
