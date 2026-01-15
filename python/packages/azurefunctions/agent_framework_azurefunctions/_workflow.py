# Copyright (c) Microsoft. All rights reserved.

"""Workflow Execution for Durable Functions

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
    - FanOutEdgeGroup: Broadcast to multiple targets (with optional selection)
    - FanInEdgeGroup: Aggregates messages from multiple sources before delivery
    - SharedState: Durable shared state accessible to all executors

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

    # Track pending sources for FanInEdgeGroups
    # Structure: {group_id: {source_id: [(message, source_executor_id)]}}
    fan_in_pending: dict[str, dict[str, list[tuple[Any, str]]]] = {}

    # Initialize fan-in tracking for all FanInEdgeGroups
    for group in workflow.edge_groups:
        if isinstance(group, FanInEdgeGroup):
            fan_in_pending[group.id] = {}

    while pending_messages and iteration < max_iterations:
        logger.debug("Orchestrator iteration %d", iteration)
        next_pending_messages: dict[str, list[tuple[Any, str]]] = {}

        for executor_id, messages_with_sources in pending_messages.items():
            logger.debug("Processing executor: %s with %d messages", executor_id, len(messages_with_sources))
            executor = workflow.executors[executor_id]

            for message, source_executor_id in messages_with_sources:
                output_message: Any | None = None
                result: dict[str, Any] | None = None  # Activity result (only set for standard executors)

                # Execute
                if isinstance(executor, AgentExecutor):
                    # Durable Agent Execution
                    # Use executor.id which equals agent.name (set during AgentExecutor construction)
                    agent_name = executor.id
                    logger.debug("Calling Durable Entity: %s", agent_name)

                    # Extract message content
                    message_content = _extract_message_content(message)

                    # Create unique session for this orchestration instance
                    session_id = AgentSessionId(name=agent_name, key=context.instance_id)

                    # Create a durable thread with the session ID using proper class
                    thread = DurableAgentThread(session_id=session_id)

                    # Create DurableAIAgent wrapper to call the entity
                    executor = AzureFunctionsAgentExecutor(context)
                    agent = DurableAIAgent(executor, agent_name)
                    agent_response: AgentRunResponse = yield agent.run(
                        message_content,
                        thread=thread,
                    )
                    logger.debug("Durable Entity %s returned: %s", agent_name, agent_response)

                    # Build AgentExecutorResponse from the typed AgentRunResponse
                    # AgentRunResponse has .text property for response text and .value for structured response
                    response_text = agent_response.text if agent_response else None
                    structured_response = None
                    if agent_response and agent_response.value is not None:
                        # If value is a Pydantic model, convert to dict
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

                else:
                    # Standard Executor Execution via Activity
                    logger.debug("Calling Activity for executor: %s", executor_id)

                    # Get shared state snapshot before activity execution (if shared_state is available)
                    # Only needed for activities since they can access SharedState
                    shared_state_snapshot: dict[str, Any] | None = None
                    if shared_state:
                        shared_state_snapshot = yield from shared_state.get_all()
                        logger.debug("[workflow] SharedState snapshot for activity: %s", shared_state_snapshot)

                    activity_input = {
                        "executor_id": executor_id,
                        "message": serialize_message(message),
                        "shared_state_snapshot": shared_state_snapshot,
                        "source_executor_ids": [source_executor_id],
                    }

                    # Serialize to JSON string to work around Azure Functions type validation issues
                    activity_input_json = json.dumps(activity_input)
                    result_json = yield context.call_activity("ExecuteExecutor", activity_input_json)
                    result = json.loads(result_json) if result_json else None
                    logger.debug("Activity for executor %s returned", executor_id)

                    # Apply any shared state updates from the activity result
                    if shared_state and result:
                        if result.get("shared_state_updates"):
                            updates = result["shared_state_updates"]
                            logger.debug("[workflow] Applying SharedState updates from activity: %s", updates)
                            yield from shared_state.update(updates)
                        if result.get("shared_state_deletes"):
                            deletes = result["shared_state_deletes"]
                            logger.debug("[workflow] Applying SharedState deletes from activity: %s", deletes)
                            for key in deletes:
                                yield from shared_state.delete(key)

                    # Collect outputs
                    if result and result.get("outputs"):
                        workflow_outputs.extend(result["outputs"])

                # Routing - handles both agent output_message and activity sent_messages
                messages_to_route: list[tuple[Any, str | None]] = []  # List of (message, explicit_target_or_none)

                if output_message:
                    messages_to_route.append((output_message, None))

                # Also route sent_messages from activities
                if result and result.get("sent_messages"):
                    for msg_data in result["sent_messages"]:
                        sent_msg = msg_data.get("message")
                        target_id = msg_data.get("target_id")
                        if sent_msg:
                            # Deserialize the message to reconstruct typed objects
                            # This is needed for condition functions that check message types
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
                            # Accumulate message for fan-in
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

    return workflow_outputs


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
