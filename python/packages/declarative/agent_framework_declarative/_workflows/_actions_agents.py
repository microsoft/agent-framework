# Copyright (c) Microsoft. All rights reserved.

"""Agent invocation action handlers for declarative workflows.

This module implements handlers for:
- InvokeAzureAgent: Invoke a hosted Azure AI agent
- InvokePromptAgent: Invoke a local prompt-based agent
"""

import json
from collections.abc import AsyncGenerator
from typing import Any, cast

from agent_framework import get_logger
from agent_framework._types import AgentRunResponse, ChatMessage

from ._handlers import (
    ActionContext,
    AgentResponseEvent,
    AgentStreamingChunkEvent,
    WorkflowEvent,
    action_handler,
)
from ._human_input import ExternalLoopEvent, QuestionRequest

logger = get_logger("agent_framework.declarative.workflows.actions")


def _build_messages_from_state(ctx: ActionContext) -> list[ChatMessage]:
    """Build the message list to send to an agent.

    This collects messages from:
    1. Conversation history
    2. Current input (if first agent call)
    3. Additional context from instructions

    Args:
        ctx: The action context

    Returns:
        List of ChatMessage objects to send to the agent
    """
    messages: list[ChatMessage] = []

    # Get conversation history
    history = ctx.state.get("conversation.messages", [])
    if history:
        messages.extend(history)

    return messages


@action_handler("InvokeAzureAgent")
async def handle_invoke_azure_agent(ctx: ActionContext) -> AsyncGenerator[WorkflowEvent, None]:
    """Invoke a hosted Azure AI agent.

    Supports both Python-style and .NET-style YAML schemas:

    Python-style schema:
        kind: InvokeAzureAgent
        agent: agentName
        input: =expression or literal input
        outputPath: turn.response

    .NET-style schema:
        kind: InvokeAzureAgent
        agent:
          name: AgentName
        conversationId: =System.ConversationId
        input:
          arguments:
            param1: value1
          messages: =expression
        output:
          messages: Local.Response
          responseObject: Local.StructuredResponse
    """
    # Get agent name - support both formats
    agent_config: dict[str, Any] | str | None = ctx.action.get("agent")
    agent_name: str | None = None
    if isinstance(agent_config, dict):
        agent_name = str(agent_config.get("name")) if agent_config.get("name") else None
        # Support dynamic agent name from expression
        if agent_name and isinstance(agent_name, str) and agent_name.startswith("="):
            evaluated = ctx.state.eval_if_expression(agent_name)
            agent_name = str(evaluated) if evaluated is not None else None
    elif isinstance(agent_config, str):
        agent_name = agent_config

    if not agent_name:
        logger.warning("InvokeAzureAgent action missing 'agent' or 'agent.name' property")
        return

    # Get input configuration
    input_config: dict[str, Any] | Any = ctx.action.get("input", {})
    input_arguments: dict[str, Any] = {}
    input_messages: Any = None
    external_loop_when: str | None = None
    if isinstance(input_config, dict):
        input_config_typed = cast(dict[str, Any], input_config)
        input_arguments = cast(dict[str, Any], input_config_typed.get("arguments") or {})
        input_messages = input_config_typed.get("messages")
        # Extract external loop configuration
        external_loop = input_config_typed.get("externalLoop")
        if isinstance(external_loop, dict):
            external_loop_typed = cast(dict[str, Any], external_loop)
            external_loop_when = str(external_loop_typed.get("when")) if external_loop_typed.get("when") else None
    else:
        input_messages = input_config  # Treat as message directly

    # Get output configuration (.NET style)
    output_config: dict[str, Any] | Any = ctx.action.get("output", {})
    output_messages_var: str | None = None
    output_response_obj_var: str | None = None
    if isinstance(output_config, dict):
        output_config_typed = cast(dict[str, Any], output_config)
        output_messages_var = str(output_config_typed.get("messages")) if output_config_typed.get("messages") else None
        output_response_obj_var = (
            str(output_config_typed.get("responseObject")) if output_config_typed.get("responseObject") else None
        )
        # auto_send is defined but not used currently
        _auto_send: bool = bool(output_config_typed.get("autoSend", True))

    # Legacy Python style output path
    output_path = ctx.action.get("outputPath")

    # Other properties
    conversation_id = ctx.action.get("conversationId")
    instructions = ctx.action.get("instructions")
    tools_config: list[dict[str, Any]] = ctx.action.get("tools", [])

    # Get the agent from registry
    agent = ctx.agents.get(agent_name)
    if agent is None:
        logger.error(f"InvokeAzureAgent: agent '{agent_name}' not found in registry")
        return

    # Evaluate conversation ID
    if conversation_id:
        evaluated_conv_id = ctx.state.eval_if_expression(conversation_id)
        ctx.state.set("system.ConversationId", evaluated_conv_id)

    # Evaluate instructions (unused currently but may be used for prompting)
    _ = ctx.state.eval_if_expression(instructions) if instructions else None

    # Build messages
    messages = _build_messages_from_state(ctx)

    # Handle input messages from .NET style
    if input_messages:
        evaluated_input = ctx.state.eval_if_expression(input_messages)
        if evaluated_input:
            if isinstance(evaluated_input, str):
                messages.append(ChatMessage(role="user", text=evaluated_input))
            elif isinstance(evaluated_input, list):
                for msg_item in evaluated_input:  # type: ignore
                    if isinstance(msg_item, str):
                        messages.append(ChatMessage(role="user", text=msg_item))
                    elif isinstance(msg_item, ChatMessage):
                        messages.append(msg_item)
                    elif isinstance(msg_item, dict) and "content" in msg_item:
                        item_dict = cast(dict[str, Any], msg_item)
                        role: str = str(item_dict.get("role", "user"))
                        content: str = str(item_dict.get("content", ""))
                        if role == "user":
                            messages.append(ChatMessage(role="user", text=content))
                        elif role == "assistant":
                            messages.append(ChatMessage(role="assistant", text=content))
                        elif role == "system":
                            messages.append(ChatMessage(role="system", text=content))

    # Evaluate and include input arguments
    evaluated_args: dict[str, Any] = {}
    for arg_key, arg_value in input_arguments.items():
        evaluated_args[arg_key] = ctx.state.eval_if_expression(arg_value)

    # Prepare tool bindings
    tool_bindings: dict[str, dict[str, Any]] = {}
    for tool_config in tools_config:
        tool_name: str | None = str(tool_config.get("name")) if tool_config.get("name") else None
        bindings: list[dict[str, Any]] = list(tool_config.get("bindings", []))  # type: ignore[arg-type]
        if tool_name and bindings:
            tool_bindings[tool_name] = {
                str(b.get("name")): ctx.state.eval_if_expression(b.get("input")) for b in bindings if b.get("name")
            }

    logger.debug(f"InvokeAzureAgent: calling '{agent_name}' with {len(messages)} messages")

    # External loop iteration counter
    iteration = 0
    max_iterations = 100  # Safety limit

    # Start external loop if configured
    while True:
        # Invoke the agent
        try:
            # Check if agent supports streaming
            if hasattr(agent, "run_stream"):
                updates: list[Any] = []
                tool_calls: list[Any] = []

                async for chunk in agent.run_stream(messages):
                    updates.append(chunk)

                    # Yield streaming events for text chunks
                    if hasattr(chunk, "text") and chunk.text:
                        yield AgentStreamingChunkEvent(
                            agent_name=str(agent_name),
                            chunk=chunk.text,
                        )

                    # Collect tool calls
                    if hasattr(chunk, "tool_calls"):
                        tool_calls.extend(chunk.tool_calls)

                # Build consolidated response from updates
                response = AgentRunResponse.from_agent_run_response_updates(updates)
                text = response.text
                response_messages = response.messages

                # Update state with result
                ctx.state.set_agent_result(
                    text=text,
                    messages=response_messages,
                    tool_calls=tool_calls if tool_calls else None,
                )

                # Add to conversation history
                if text:
                    ctx.state.add_conversation_message(ChatMessage(role="assistant", text=text))

                # Store in output variables (.NET style)
                if output_messages_var:
                    output_path_mapped = _map_variable_to_path(output_messages_var)
                    ctx.state.set(output_path_mapped, response_messages if response_messages else text)

                if output_response_obj_var:
                    output_path_mapped = _map_variable_to_path(output_response_obj_var)
                    # Try to parse as JSON if it looks like structured output
                    try:
                        parsed = json.loads(text) if text else None
                        ctx.state.set(output_path_mapped, parsed)
                    except (json.JSONDecodeError, TypeError):
                        ctx.state.set(output_path_mapped, text)

                # Store in output path (Python style)
                if output_path:
                    ctx.state.set(output_path, text)

                yield AgentResponseEvent(
                    agent_name=str(agent_name),
                    text=text,
                    messages=response_messages,
                    tool_calls=tool_calls if tool_calls else None,
                )

            elif hasattr(agent, "run"):
                # Non-streaming invocation
                response = await agent.run(messages)

                text = response.text
                response_messages = response.messages
                response_tool_calls: list[Any] | None = getattr(response, "tool_calls", None)

                # Update state with result
                ctx.state.set_agent_result(
                    text=text,
                    messages=response_messages,
                    tool_calls=response_tool_calls,
                )

                # Add to conversation history
                if text:
                    ctx.state.add_conversation_message(ChatMessage(role="assistant", text=text))

                # Store in output variables (.NET style)
                if output_messages_var:
                    output_path_mapped = _map_variable_to_path(output_messages_var)
                    ctx.state.set(output_path_mapped, response_messages if response_messages else text)

                if output_response_obj_var:
                    output_path_mapped = _map_variable_to_path(output_response_obj_var)
                    try:
                        parsed = json.loads(text) if text else None
                        ctx.state.set(output_path_mapped, parsed)
                    except (json.JSONDecodeError, TypeError):
                        ctx.state.set(output_path_mapped, text)

                # Store in output path (Python style)
                if output_path:
                    ctx.state.set(output_path, text)

                yield AgentResponseEvent(
                    agent_name=str(agent_name),
                    text=text,
                    messages=response_messages,
                    tool_calls=response_tool_calls,
                )
            else:
                logger.error(f"InvokeAzureAgent: agent '{agent_name}' has no run or run_stream method")
                break

        except Exception as e:
            logger.error(f"InvokeAzureAgent: error invoking agent '{agent_name}': {e}")
            raise

        # Check external loop condition
        if external_loop_when:
            # Evaluate the loop condition
            should_continue = ctx.state.eval(external_loop_when)
            should_continue = bool(should_continue) if should_continue is not None else False

            logger.debug(
                f"InvokeAzureAgent: external loop condition '{str(external_loop_when)[:50]}' = "
                f"{should_continue} (iteration {iteration})"
            )

            if should_continue and iteration < max_iterations:
                # Emit event to signal waiting for external input
                action_id: str = str(ctx.action.get("id", f"agent_{agent_name}"))
                yield ExternalLoopEvent(
                    action_id=action_id,
                    iteration=iteration,
                    condition_expression=str(external_loop_when),
                )

                # The workflow executor should:
                # 1. Pause execution
                # 2. Wait for external input
                # 3. Update state with input
                # 4. Resume this generator

                # For now, we request input via QuestionRequest
                yield QuestionRequest(
                    request_id=f"{action_id}_input_{iteration}",
                    prompt="Waiting for user input...",
                    variable="turn.userInput",
                )

                iteration += 1

                # Clear messages for next iteration (start fresh with conversation)
                messages = _build_messages_from_state(ctx)
                continue
            elif iteration >= max_iterations:
                logger.warning(f"InvokeAzureAgent: external loop exceeded max iterations ({max_iterations})")

        # No external loop or condition is false - exit
        break


def _map_variable_to_path(variable: str) -> str:
    """Map .NET-style variable names to state paths.

    Args:
        variable: Variable name like 'Local.X' or 'System.ConversationId'

    Returns:
        State path like 'turn.X' or 'system.ConversationId'
    """
    if variable.startswith("Local."):
        return "turn." + variable[6:]
    if variable.startswith("System."):
        return "system." + variable[7:]
    if variable.startswith("Workflow."):
        return "workflow." + variable[9:]
    if "." in variable:
        return variable
    return "turn." + variable


@action_handler("InvokePromptAgent")
async def handle_invoke_prompt_agent(ctx: ActionContext) -> AsyncGenerator[WorkflowEvent, None]:
    """Invoke a local prompt-based agent (similar to InvokeAzureAgent but for local agents).

    Action schema:
        kind: InvokePromptAgent
        agent: agentName  # name of the agent in the agents registry
        input: =expression or literal input
        instructions: =expression or literal prompt/instructions
        outputPath: turn.response  # optional path to store result
    """
    # Implementation is similar to InvokeAzureAgent
    # The difference is primarily in how the agent is configured
    agent_name_raw = ctx.action.get("agent")
    if not isinstance(agent_name_raw, str):
        logger.warning("InvokePromptAgent action missing 'agent' property")
        return
    agent_name: str = agent_name_raw
    input_expr = ctx.action.get("input")
    instructions = ctx.action.get("instructions")
    output_path = ctx.action.get("outputPath")

    # Get the agent from registry
    agent = ctx.agents.get(agent_name)
    if agent is None:
        logger.error(f"InvokePromptAgent: agent '{agent_name}' not found in registry")
        return

    # Evaluate input
    input_value = ctx.state.eval_if_expression(input_expr) if input_expr else None

    # Evaluate instructions (unused currently but may be used for prompting)
    _ = ctx.state.eval_if_expression(instructions) if instructions else None

    # Build messages
    messages = _build_messages_from_state(ctx)

    # Add input as user message if provided
    if input_value:
        if isinstance(input_value, str):
            messages.append(ChatMessage(role="user", text=input_value))
        elif isinstance(input_value, ChatMessage):
            messages.append(input_value)

    logger.debug(f"InvokePromptAgent: calling '{agent_name}' with {len(messages)} messages")

    # Invoke the agent
    try:
        if hasattr(agent, "run_stream"):
            updates: list[Any] = []

            async for chunk in agent.run_stream(messages):
                updates.append(chunk)

                if hasattr(chunk, "text") and chunk.text:
                    yield AgentStreamingChunkEvent(
                        agent_name=agent_name,
                        chunk=chunk.text,
                    )

            # Build consolidated response from updates
            response = AgentRunResponse.from_agent_run_response_updates(updates)
            text = response.text
            response_messages = response.messages

            ctx.state.set_agent_result(text=text, messages=response_messages)

            if text:
                ctx.state.add_conversation_message(ChatMessage(role="assistant", text=text))

            if output_path:
                ctx.state.set(output_path, text)

            yield AgentResponseEvent(
                agent_name=agent_name,
                text=text,
                messages=response_messages,
            )

        elif hasattr(agent, "run"):
            response = await agent.run(messages)
            text = response.text
            response_messages = response.messages

            ctx.state.set_agent_result(text=text, messages=response_messages)

            if text:
                ctx.state.add_conversation_message(ChatMessage(role="assistant", text=text))

            if output_path:
                ctx.state.set(output_path, text)

            yield AgentResponseEvent(
                agent_name=agent_name,
                text=text,
                messages=response_messages,
            )
        else:
            logger.error(f"InvokePromptAgent: agent '{agent_name}' has no run or run_stream method")

    except Exception as e:
        logger.error(f"InvokePromptAgent: error invoking agent '{agent_name}': {e}")
        raise
