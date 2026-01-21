# Copyright (c) Microsoft. All rights reserved.

"""Agent invocation executors for declarative workflows.

These executors handle invoking Azure AI Foundry agents and other AI agents,
supporting both streaming responses and human-in-loop patterns.

Aligned with .NET's InvokeAzureAgentExecutor behavior including:
- Structured input with arguments and messages
- External loop support for human-in-loop patterns
- Output with messages and responseObject (JSON parsing)
- AutoSend behavior control
"""

import contextlib
import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, cast

from agent_framework import (
    ChatMessage,
    Content,
    WorkflowContext,
    handler,
    response_handler,
)

from ._declarative_base import (
    ActionComplete,
    DeclarativeActionExecutor,
    DeclarativeWorkflowState,
)

logger = logging.getLogger(__name__)


def _extract_json_from_response(text: str) -> Any:
    r"""Extract and parse JSON from an agent response.

    Agents often return JSON wrapped in markdown code blocks or with
    explanatory text. This function attempts to extract and parse the
    JSON content from various formats:

    1. Pure JSON: {"key": "value"}
    2. Markdown code block: ```json\n{"key": "value"}\n```
    3. Markdown code block (no language): ```\n{"key": "value"}\n```
    4. JSON with leading/trailing text: Here's the result: {"key": "value"}
    5. Multiple JSON objects: Returns the LAST valid JSON object

    When multiple JSON objects are present (e.g., streaming agent responses
    that emit partial then final results), this returns the last complete
    JSON object, which is typically the final/complete result.

    Args:
        text: The raw text response from an agent

    Returns:
        Parsed JSON as a Python dict/list, or None if parsing fails

    Raises:
        json.JSONDecodeError: If no valid JSON can be extracted
    """
    import re

    if not text:
        return None

    text = text.strip()

    if not text:
        return None

    # Try parsing as pure JSON first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try extracting from markdown code blocks: ```json ... ``` or ``` ... ```
    # Use the last code block if there are multiple
    code_block_patterns = [
        r"```json\s*\n?(.*?)\n?```",  # ```json ... ```
        r"```\s*\n?(.*?)\n?```",  # ``` ... ```
    ]
    for pattern in code_block_patterns:
        matches = list(re.finditer(pattern, text, re.DOTALL))
        if matches:
            # Try the last match first (most likely to be the final result)
            for match in reversed(matches):
                try:
                    return json.loads(match.group(1).strip())
                except json.JSONDecodeError:
                    continue

    # Find ALL JSON objects {...} or arrays [...] in the text and return the last valid one
    # This handles cases where agents stream multiple JSON objects (partial, then final)
    all_json_objects: list[Any] = []

    pos = 0
    while pos < len(text):
        # Find next { or [
        json_start = -1
        bracket_char = None
        for i in range(pos, len(text)):
            if text[i] == "{":
                json_start = i
                bracket_char = "{"
                break
            if text[i] == "[":
                json_start = i
                bracket_char = "["
                break

        if json_start < 0:
            break  # No more JSON objects

        # Find matching closing bracket
        open_bracket = bracket_char
        close_bracket = "}" if open_bracket == "{" else "]"
        depth = 0
        in_string = False
        escape_next = False
        found_end = False

        for i in range(json_start, len(text)):
            char = text[i]

            if escape_next:
                escape_next = False
                continue

            if char == "\\":
                escape_next = True
                continue

            if char == '"' and not escape_next:
                in_string = not in_string
                continue

            if in_string:
                continue

            if char == open_bracket:
                depth += 1
            elif char == close_bracket:
                depth -= 1
                if depth == 0:
                    # Found the end
                    potential_json = text[json_start : i + 1]
                    try:
                        parsed = json.loads(potential_json)
                        all_json_objects.append(parsed)
                    except json.JSONDecodeError:
                        pass
                    pos = i + 1
                    found_end = True
                    break

        if not found_end:
            # Malformed JSON, move past the start character
            pos = json_start + 1

    # Return the last valid JSON object (most likely to be the final/complete result)
    if all_json_objects:
        return all_json_objects[-1]

    # Unable to extract JSON
    raise json.JSONDecodeError("No valid JSON found in response", text, 0)


def _validate_conversation_history(messages: list[ChatMessage], agent_name: str) -> None:
    """Validate that conversation history has matching tool calls and results.

    This helps catch issues where tool call messages are stored without their
    corresponding tool result messages, which would cause API errors.

    Args:
        messages: The conversation history to validate.
        agent_name: Name of the agent for logging purposes.

    Logs a warning if orphaned tool calls are found.
    """
    # Collect all tool call IDs and tool result IDs
    tool_call_ids: set[str] = set()
    tool_result_ids: set[str] = set()

    for i, msg in enumerate(messages):
        if not hasattr(msg, "contents") or msg.contents is None:
            continue
        for content in msg.contents:
            if content.type == "function_call" and content.call_id:
                tool_call_ids.add(content.call_id)
                logger.debug(
                    "Agent '%s': Found tool call '%s' (id=%s) in message %d",
                    agent_name,
                    content.name,
                    content.call_id,
                    i,
                )
            elif content.type == "function_result" and content.call_id:
                tool_result_ids.add(content.call_id)
                logger.debug(
                    "Agent '%s': Found tool result for call_id=%s in message %d",
                    agent_name,
                    content.call_id,
                    i,
                )

    # Find orphaned tool calls (calls without results)
    orphaned_calls = tool_call_ids - tool_result_ids
    if orphaned_calls:
        logger.warning(
            "Agent '%s': Conversation history has %d orphaned tool call(s) without results: %s. "
            "Total messages: %d, tool calls: %d, tool results: %d",
            agent_name,
            len(orphaned_calls),
            orphaned_calls,
            len(messages),
            len(tool_call_ids),
            len(tool_result_ids),
        )
        # Log message structure for debugging
        for i, msg in enumerate(messages):
            role = getattr(msg, "role", "unknown")
            content_types = []
            if hasattr(msg, "contents") and msg.contents:
                content_types = [type(c).__name__ for c in msg.contents]
            logger.warning(
                "Agent '%s': Message %d - role=%s, contents=%s",
                agent_name,
                i,
                role,
                content_types,
            )


# Keys for agent-related state
AGENT_REGISTRY_KEY = "_agent_registry"
TOOL_REGISTRY_KEY = "_tool_registry"
# Key to store external loop state for resumption
EXTERNAL_LOOP_STATE_KEY = "_external_loop_state"


class AgentInvocationError(Exception):
    """Raised when an agent invocation fails.

    Attributes:
        agent_name: Name of the agent that failed
        message: Error description
    """

    def __init__(self, agent_name: str, message: str) -> None:
        self.agent_name = agent_name
        super().__init__(f"Agent '{agent_name}' invocation failed: {message}")


@dataclass
class AgentResult:
    """Result from an agent invocation."""

    success: bool
    response: str
    agent_name: str
    messages: list[ChatMessage] = field(default_factory=lambda: cast(list[ChatMessage], []))
    tool_calls: list[Content] = field(default_factory=lambda: cast(list[Content], []))
    error: str | None = None


@dataclass
class AgentExternalInputRequest:
    """Request for external input during agent invocation.

    Emitted when externalLoop.when condition evaluates to true,
    signaling that the workflow should yield and wait for user input.

    This is the request type used with ctx.request_info() to implement
    the Yield/Resume pattern for human-in-loop workflows.

    Examples:
        .. code-block:: python

            from agent_framework import run_context
            from agent_framework_declarative import (
                ExternalInputRequest,
                ExternalInputResponse,
                WorkflowFactory,
            )

            factory = WorkflowFactory()
            workflow = factory.create_workflow_from_yaml_path("hitl_workflow.yaml")


            async def run_with_hitl():
                # Set up external input handler
                async def on_request(request: AgentExternalInputRequest) -> ExternalInputResponse:
                    print(f"Agent '{request.agent_name}' needs input:")
                    print(f"  Response: {request.agent_response}")
                    user_input = input("Your response: ")
                    return AgentExternalInputResponse(user_input=user_input)

                async with run_context(request_handler=on_request) as ctx:
                    async for event in workflow.run_stream(ctx=ctx):
                        print(event)
    """

    request_id: str
    agent_name: str
    agent_response: str
    iteration: int = 0
    messages: list[ChatMessage] = field(default_factory=lambda: cast(list[ChatMessage], []))
    function_calls: list[Content] = field(default_factory=lambda: cast(list[Content], []))


@dataclass
class AgentExternalInputResponse:
    """Response to an ExternalInputRequest.

    Provided by the caller to resume agent execution with new user input.
    This is the response type expected by the response_handler.

    Examples:
        .. code-block:: python

            from agent_framework_declarative import ExternalInputResponse

            # Basic response with user text input
            response = AgentExternalInputResponse(user_input="Yes, please proceed with the order.")

        .. code-block:: python

            from agent_framework_declarative import ExternalInputResponse

            # Response with additional message history
            response = AgentExternalInputResponse(
                user_input="Approved",
                messages=[],  # Additional context messages if needed
            )
    """

    user_input: str
    messages: list[ChatMessage] = field(default_factory=lambda: cast(list[ChatMessage], []))
    function_results: dict[str, Content] = field(default_factory=lambda: cast(dict[str, Content], {}))


@dataclass
class ExternalLoopState:
    """State saved for external loop resumption.

    Stored in shared_state to allow the response_handler to
    continue the loop with the same configuration.
    """

    agent_name: str
    iteration: int
    external_loop_when: str
    messages_var: str | None
    response_obj_var: str | None
    result_property: str | None
    auto_send: bool
    messages_path: str = "Conversation.messages"
    max_iterations: int = 100


def _normalize_variable_path(variable: str) -> str:
    """Normalize variable names to ensure they have a scope prefix.

    Args:
        variable: Variable name like 'Local.X' or 'System.ConversationId'

    Returns:
        The variable path with a scope prefix (defaults to Local if none provided)
    """
    if variable.startswith(("Local.", "System.", "Workflow.", "Agent.", "Conversation.")):
        # Already has a proper namespace
        return variable
    if "." in variable:
        # Has some namespace, use as-is
        return variable
    # Default to Local scope
    return "Local." + variable


class InvokeAzureAgentExecutor(DeclarativeActionExecutor):
    """Executor that invokes an Azure AI Foundry agent.

    This executor supports both Python-style and .NET-style YAML schemas:

    Python-style (simple):
        kind: InvokeAzureAgent
        agent: MenuAgent
        input: =Local.userInput
        resultProperty: Local.agentResponse

    .NET-style (full featured):
        kind: InvokeAzureAgent
        agent:
          name: AgentName
        conversationId: =System.ConversationId
        input:
          arguments:
            param1: =Local.value1
            param2: literal value
          messages: =Conversation.messages
          externalLoop:
            when: =Local.needsMoreInput
        output:
          messages: Local.ResponseMessages
          responseObject: Local.StructuredResponse
          autoSend: true

    Features:
    - Structured input with arguments and messages
    - External loop support for human-in-loop patterns
    - Output with messages and responseObject (JSON parsing)
    - AutoSend behavior control for streaming output
    """

    def __init__(
        self,
        action_def: dict[str, Any],
        *,
        id: str | None = None,
        agents: dict[str, Any] | None = None,
    ):
        """Initialize the agent executor.

        Args:
            action_def: The action definition from YAML
            id: Optional executor ID
            agents: Registry of agent instances by name
        """
        super().__init__(action_def, id=id)
        self._agents = agents or {}

    def _get_agent_name(self, state: Any) -> str | None:
        """Extract agent name from action definition.

        Supports both simple string and nested object formats.
        """
        agent_config = self._action_def.get("agent")

        if isinstance(agent_config, str):
            return agent_config

        if isinstance(agent_config, dict):
            agent_dict = cast(dict[str, Any], agent_config)
            name = agent_dict.get("name")
            if name is not None and isinstance(name, str):
                # Support dynamic agent name from expression (would need async eval)
                return str(name)

        agent_name = self._action_def.get("agentName")
        return str(agent_name) if isinstance(agent_name, str) else None

    def _get_input_config(self) -> tuple[dict[str, Any], Any, str | None, int]:
        """Parse input configuration.

        Returns:
            Tuple of (arguments dict, messages expression, externalLoop.when expression, maxIterations)
        """
        input_config = self._action_def.get("input", {})

        if not isinstance(input_config, dict):
            # Simple input - treat as message directly
            return {}, input_config, None, 100

        input_dict = cast(dict[str, Any], input_config)
        arguments: dict[str, Any] = cast(dict[str, Any], input_dict.get("arguments", {}))
        messages: Any = input_dict.get("messages")

        # Extract external loop configuration
        external_loop_when: str | None = None
        max_iterations: int = 100  # Default safety limit
        external_loop = input_dict.get("externalLoop")
        if isinstance(external_loop, dict):
            loop_dict = cast(dict[str, Any], external_loop)
            when_val = loop_dict.get("when")
            external_loop_when = str(when_val) if when_val is not None else None
            max_iter_val = loop_dict.get("maxIterations")
            if max_iter_val is not None:
                max_iterations = int(max_iter_val)

        return arguments, messages, external_loop_when, max_iterations

    def _get_output_config(self) -> tuple[str | None, str | None, str | None, bool]:
        """Parse output configuration.

        Returns:
            Tuple of (messages var, responseObject var, resultProperty, autoSend)
        """
        output_config = self._action_def.get("output", {})

        # Legacy Python-style
        result_property: str | None = cast(str | None, self._action_def.get("resultProperty"))

        if not isinstance(output_config, dict):
            return None, None, result_property, True

        output_dict = cast(dict[str, Any], output_config)
        messages_var_val: Any = output_dict.get("messages")
        messages_var: str | None = str(messages_var_val) if messages_var_val is not None else None
        response_obj_val: Any = output_dict.get("responseObject")
        response_obj_var: str | None = str(response_obj_val) if response_obj_val is not None else None
        property_val: Any = output_dict.get("property")
        property_var: str | None = str(property_val) if property_val is not None else None
        auto_send_val: Any = output_dict.get("autoSend", True)
        auto_send: bool = bool(auto_send_val)

        return messages_var, response_obj_var, property_var or result_property, auto_send

    def _get_conversation_id(self) -> str | None:
        """Get the conversation ID expression from action definition.

        Returns:
            The conversationId expression/value, or None if not specified
        """
        return self._action_def.get("conversationId")

    async def _get_conversation_messages_path(
        self, state: DeclarativeWorkflowState, conversation_id_expr: str | None
    ) -> str:
        """Get the state path for conversation messages.

        Args:
            state: Workflow state for expression evaluation
            conversation_id_expr: The conversationId expression from action definition

        Returns:
            State path for messages (e.g., "Conversation.messages" or "System.conversations.{id}.messages")
        """
        if not conversation_id_expr:
            return "Conversation.messages"

        # Evaluate the conversation ID expression
        evaluated_id = await state.eval_if_expression(conversation_id_expr)
        if not evaluated_id:
            return "Conversation.messages"

        # Use conversation-specific messages path
        return f"System.conversations.{evaluated_id}.messages"

    async def _build_input_text(self, state: Any, arguments: dict[str, Any], messages_expr: Any) -> str:
        """Build input text from arguments and messages.

        Args:
            state: Workflow state for expression evaluation
            arguments: Input arguments to evaluate
            messages_expr: Messages expression or direct input

        Returns:
            Input text for the agent
        """
        # Evaluate arguments
        evaluated_args: dict[str, Any] = {}
        for key, value in arguments.items():
            evaluated_args[key] = await state.eval_if_expression(value)

        # Evaluate messages/input
        if messages_expr:
            evaluated_input: Any = await state.eval_if_expression(messages_expr)
            if isinstance(evaluated_input, str):
                return evaluated_input
            if isinstance(evaluated_input, list) and evaluated_input:
                # Extract text from last message
                last: Any = evaluated_input[-1]  # type: ignore
                if isinstance(last, str):
                    return last
                if isinstance(last, dict):
                    last_dict = cast(dict[str, Any], last)
                    content_val: Any = last_dict.get("content", last_dict.get("text", ""))
                    return str(content_val) if content_val else ""
                if last is not None and hasattr(last, "text"):  # type: ignore
                    return str(getattr(last, "text", ""))  # type: ignore
            if evaluated_input:
                return str(cast(Any, evaluated_input))
            return ""

        # Fallback chain for implicit input (like .NET conversationId pattern):
        # 1. Local.input / Local.userInput (explicit turn state)
        # 2. System.LastMessage.Text (previous agent's response)
        # 3. Workflow.Inputs (first agent gets workflow inputs)
        input_text: str = str(await state.get("Local.input") or await state.get("Local.userInput") or "")
        if not input_text:
            # Try System.LastMessage.Text (used by external loop and agent chaining)
            last_message: Any = await state.get("System.LastMessage")
            if isinstance(last_message, dict):
                last_msg_dict = cast(dict[str, Any], last_message)
                text_val: Any = last_msg_dict.get("Text", "")
                input_text = str(text_val) if text_val else ""
        if not input_text:
            # Fall back to workflow inputs (for first agent in chain)
            inputs: Any = await state.get("Workflow.Inputs")
            if isinstance(inputs, dict):
                inputs_dict = cast(dict[str, Any], inputs)
                # If single input, use its value directly
                if len(inputs_dict) == 1:
                    input_text = str(next(iter(inputs_dict.values())))
                else:
                    # Multiple inputs - format as key: value pairs
                    input_text = "\n".join(f"{k}: {v}" for k, v in inputs_dict.items())
        return input_text if input_text else ""

    def _get_agent(self, agent_name: str, ctx: WorkflowContext[Any, Any]) -> Any:
        """Get agent from registry (sync helper for response handler)."""
        return self._agents.get(agent_name) if self._agents else None

    async def _invoke_agent_and_store_results(
        self,
        agent: Any,
        agent_name: str,
        input_text: str,
        state: DeclarativeWorkflowState,
        ctx: WorkflowContext[ActionComplete, str],
        messages_var: str | None,
        response_obj_var: str | None,
        result_property: str | None,
        auto_send: bool,
        messages_path: str = "Conversation.messages",
    ) -> tuple[str, list[Any], list[Any]]:
        """Invoke agent and store results in state.

        Args:
            agent: The agent instance to invoke
            agent_name: Name of the agent for logging
            input_text: User input text
            state: Workflow state
            ctx: Workflow context
            messages_var: Output variable for messages
            response_obj_var: Output variable for parsed response object
            result_property: Output property for result
            auto_send: Whether to auto-send output to context
            messages_path: State path for conversation messages (default: "Conversation.messages")

        Returns:
            Tuple of (accumulated_response, all_messages, tool_calls)
        """
        accumulated_response = ""
        all_messages: list[ChatMessage] = []
        tool_calls: list[Content] = []

        # Add user input to conversation history first (via state.append only)
        if input_text:
            user_message = ChatMessage(role="user", text=input_text)
            await state.append(messages_path, user_message)

        # Get conversation history from state AFTER adding user message
        # Note: We get a fresh copy to avoid mutation issues
        conversation_history: list[ChatMessage] = await state.get(messages_path) or []

        # Build messages list for agent (use history if available, otherwise just input)
        messages_for_agent: list[ChatMessage] | str = conversation_history if conversation_history else input_text

        # Validate conversation history before invoking agent
        if isinstance(messages_for_agent, list) and messages_for_agent:
            _validate_conversation_history(messages_for_agent, agent_name)

        # Use run() method to get properly structured messages (including tool calls and results)
        # This is critical for multi-turn conversations where tool calls must be followed
        # by their results in the message history
        if hasattr(agent, "run"):
            result: Any = await agent.run(messages_for_agent)
            if hasattr(result, "text") and result.text:
                accumulated_response = str(result.text)
                if auto_send:
                    await ctx.yield_output(str(result.text))
            elif isinstance(result, str):
                accumulated_response = result
                if auto_send:
                    await ctx.yield_output(result)

            if not isinstance(result, str):
                result_messages: Any = getattr(result, "messages", None)
                if result_messages is not None:
                    all_messages = list(cast(list[ChatMessage], result_messages))
                result_tool_calls: Any = getattr(result, "tool_calls", None)
                if result_tool_calls is not None:
                    tool_calls = list(cast(list[Content], result_tool_calls))

        else:
            raise RuntimeError(f"Agent '{agent_name}' has no run or run_stream method")

        # Add messages to conversation history
        # We need to include ALL messages from the agent run (including tool calls and tool results)
        # to maintain proper conversation state for the next agent invocation
        if all_messages:
            # Agent returned full message history - use it
            logger.debug(
                "Agent '%s': Storing %d messages to conversation history at '%s'",
                agent_name,
                len(all_messages),
                messages_path,
            )
            for i, msg in enumerate(all_messages):
                role = getattr(msg, "role", "unknown")
                content_types = []
                if hasattr(msg, "contents") and msg.contents:
                    content_types = [type(c).__name__ for c in msg.contents]
                logger.debug(
                    "Agent '%s': Storing message %d - role=%s, contents=%s",
                    agent_name,
                    i,
                    role,
                    content_types,
                )
                await state.append(messages_path, msg)
        elif accumulated_response:
            # No messages returned, create a simple assistant message
            logger.debug(
                "Agent '%s': No messages in response, creating simple assistant message",
                agent_name,
            )
            assistant_message = ChatMessage(role="assistant", text=accumulated_response)
            await state.append(messages_path, assistant_message)

        # Store results in state - support both schema formats:
        # - Graph mode: Agent.response, Agent.name
        # - Interpreter mode: Agent.text, Agent.messages, Agent.toolCalls
        await state.set("Agent.response", accumulated_response)
        await state.set("Agent.name", agent_name)
        await state.set("Agent.text", accumulated_response)
        await state.set("Agent.messages", all_messages if all_messages else [])
        await state.set("Agent.toolCalls", tool_calls if tool_calls else [])

        # Store System.LastMessage for externalLoop.when condition evaluation
        await state.set("System.LastMessage", {"Text": accumulated_response})

        # Store in output variables (.NET style)
        if messages_var:
            output_path = _normalize_variable_path(messages_var)
            await state.set(output_path, all_messages if all_messages else accumulated_response)

        if response_obj_var:
            output_path = _normalize_variable_path(response_obj_var)
            # Try to extract and parse JSON from the response
            try:
                parsed = _extract_json_from_response(accumulated_response) if accumulated_response else None
                logger.debug(f"InvokeAzureAgent: parsed responseObject for '{output_path}': type={type(parsed)}")
                await state.set(output_path, parsed)
            except (json.JSONDecodeError, TypeError) as e:
                logger.warning(f"InvokeAzureAgent: failed to parse JSON for '{output_path}': {e}, storing as string")
                await state.set(output_path, accumulated_response)

        # Store in result property (Python style)
        if result_property:
            await state.set(result_property, accumulated_response)

        return accumulated_response, all_messages, tool_calls

    @handler
    async def handle_action(
        self,
        trigger: Any,
        ctx: WorkflowContext[ActionComplete, str],
    ) -> None:
        """Handle the agent invocation with full .NET feature parity.

        When externalLoop.when is configured and evaluates to true after agent response,
        this method emits an ExternalInputRequest via ctx.request_info() and returns.
        The workflow will yield, and when the caller provides a response via
        send_responses_streaming(), the handle_external_input_response handler
        will continue the loop.
        """
        state = await self._ensure_state_initialized(ctx, trigger)

        # Parse configuration
        agent_name = self._get_agent_name(state)
        if not agent_name:
            logger.warning("InvokeAzureAgent action missing 'agent' or 'agent.name' property")
            await ctx.send_message(ActionComplete())
            return

        logger.debug("handle_action: starting agent '%s'", agent_name)

        arguments, messages_expr, external_loop_when, max_iterations = self._get_input_config()
        messages_var, response_obj_var, result_property, auto_send = self._get_output_config()

        # Get conversation-specific messages path if conversationId is specified
        conversation_id_expr = self._get_conversation_id()
        messages_path = await self._get_conversation_messages_path(state, conversation_id_expr)
        logger.debug("handle_action: agent='%s', messages_path='%s'", agent_name, messages_path)

        # Build input
        input_text = await self._build_input_text(state, arguments, messages_expr)

        # Get agent from registry
        agent: Any = self._agents.get(agent_name) if self._agents else None
        if agent is None:
            try:
                agent_registry: dict[str, Any] | None = await ctx.shared_state.get(AGENT_REGISTRY_KEY)
            except KeyError:
                agent_registry = {}
            agent = agent_registry.get(agent_name) if agent_registry else None

        if agent is None:
            error_msg = f"Agent '{agent_name}' not found in registry"
            logger.error(f"InvokeAzureAgent: {error_msg}")
            await state.set("Agent.error", error_msg)
            if result_property:
                await state.set(result_property, {"error": error_msg})
            raise AgentInvocationError(agent_name, "not found in registry")

        iteration = 0

        try:
            accumulated_response, all_messages, tool_calls = await self._invoke_agent_and_store_results(
                agent=agent,
                agent_name=agent_name,
                input_text=input_text,
                state=state,
                ctx=ctx,
                messages_var=messages_var,
                response_obj_var=response_obj_var,
                result_property=result_property,
                auto_send=auto_send,
                messages_path=messages_path,
            )
        except AgentInvocationError:
            raise  # Re-raise our own errors
        except Exception as e:
            logger.error(f"InvokeAzureAgent: error invoking agent '{agent_name}': {e}")
            await state.set("Agent.error", str(e))
            if result_property:
                await state.set(result_property, {"error": str(e)})
            raise AgentInvocationError(agent_name, str(e)) from e

        # Check external loop condition
        if external_loop_when:
            should_continue = await state.eval(external_loop_when)
            should_continue = bool(should_continue) if should_continue is not None else False

            logger.debug(
                f"InvokeAzureAgent: external loop condition '{str(external_loop_when)[:50]}' = "
                f"{should_continue} (iteration {iteration})"
            )

            if should_continue:
                # Save loop state for resumption
                loop_state = ExternalLoopState(
                    agent_name=agent_name,
                    iteration=iteration + 1,
                    external_loop_when=external_loop_when,
                    messages_var=messages_var,
                    response_obj_var=response_obj_var,
                    result_property=result_property,
                    auto_send=auto_send,
                    messages_path=messages_path,
                    max_iterations=max_iterations,
                )
                await ctx.shared_state.set(EXTERNAL_LOOP_STATE_KEY, loop_state)

                # Emit request for external input - workflow will yield here
                request = AgentExternalInputRequest(
                    request_id=str(uuid.uuid4()),
                    agent_name=agent_name,
                    agent_response=accumulated_response,
                    iteration=iteration,
                    messages=all_messages,
                    function_calls=tool_calls,
                )
                logger.info(f"InvokeAzureAgent: yielding for external input (iteration {iteration})")
                await ctx.request_info(request, AgentExternalInputResponse)
                # Return without sending ActionComplete - workflow yields
                return

        # No external loop or condition is false - complete the action
        await ctx.send_message(ActionComplete())

    @response_handler
    async def handle_external_input_response(
        self,
        original_request: AgentExternalInputRequest,
        response: AgentExternalInputResponse,
        ctx: WorkflowContext[ActionComplete, str],
    ) -> None:
        """Handle response to an ExternalInputRequest and continue the loop.

        This is called when the workflow resumes after yielding for external input.
        It continues the agent invocation loop with the user's new input.
        """
        logger.debug(
            "handle_external_input_response: resuming with user_input='%s'",
            response.user_input[:100] if response.user_input else None,
        )
        state = self._get_state(ctx.shared_state)

        # Retrieve saved loop state
        try:
            loop_state: ExternalLoopState = await ctx.shared_state.get(EXTERNAL_LOOP_STATE_KEY)
        except KeyError:
            logger.error("InvokeAzureAgent: external loop state not found, cannot resume")
            await ctx.send_message(ActionComplete())
            return

        agent_name = loop_state.agent_name
        iteration = loop_state.iteration
        external_loop_when = loop_state.external_loop_when
        max_iterations = loop_state.max_iterations
        messages_path = loop_state.messages_path

        logger.debug(
            "handle_external_input_response: agent='%s', iteration=%d, messages_path='%s'",
            agent_name,
            iteration,
            messages_path,
        )

        # Get the user's new input
        input_text = response.user_input

        # Store the user input in state for condition evaluation
        await state.set("Local.userInput", input_text)
        await state.set("System.LastMessage", {"Text": input_text})

        # Check if we should continue BEFORE invoking the agent
        # This matches .NET behavior where the condition checks the user's input
        should_continue = await state.eval(external_loop_when)
        should_continue = bool(should_continue) if should_continue is not None else False

        logger.debug(
            f"InvokeAzureAgent: external loop condition '{str(external_loop_when)[:50]}' = "
            f"{should_continue} (iteration {iteration}) for input '{input_text[:30]}...'"
        )

        if not should_continue:
            # User input caused loop to exit - clean up and complete
            with contextlib.suppress(KeyError):
                await ctx.shared_state.delete(EXTERNAL_LOOP_STATE_KEY)
            await ctx.send_message(ActionComplete())
            return

        # Get agent from registry
        agent: Any = self._agents.get(agent_name) if self._agents else None
        if agent is None:
            try:
                agent_registry: dict[str, Any] | None = await ctx.shared_state.get(AGENT_REGISTRY_KEY)
            except KeyError:
                agent_registry = {}
            agent = agent_registry.get(agent_name) if agent_registry else None

        if agent is None:
            logger.error(f"InvokeAzureAgent: agent '{agent_name}' not found during loop resumption")
            raise AgentInvocationError(agent_name, "not found during loop resumption")

        try:
            accumulated_response, all_messages, tool_calls = await self._invoke_agent_and_store_results(
                agent=agent,
                agent_name=agent_name,
                input_text=input_text,
                state=state,
                ctx=ctx,
                messages_var=loop_state.messages_var,
                response_obj_var=loop_state.response_obj_var,
                result_property=loop_state.result_property,
                auto_send=loop_state.auto_send,
                messages_path=loop_state.messages_path,
            )
        except AgentInvocationError:
            raise  # Re-raise our own errors
        except Exception as e:
            logger.error(f"InvokeAzureAgent: error invoking agent '{agent_name}' during loop: {e}")
            await state.set("Agent.error", str(e))
            raise AgentInvocationError(agent_name, str(e)) from e

        # Re-evaluate the condition AFTER the agent responds
        # This is critical: the agent's response may have set NeedsTicket=true or IsResolved=true
        should_continue = await state.eval(external_loop_when)
        should_continue = bool(should_continue) if should_continue is not None else False

        logger.debug(
            f"InvokeAzureAgent: external loop condition after response '{str(external_loop_when)[:50]}' = "
            f"{should_continue} (iteration {iteration})"
        )

        if not should_continue:
            # Agent response caused loop to exit (e.g., NeedsTicket=true or IsResolved=true)
            logger.info(
                "InvokeAzureAgent: external loop exited due to condition=false "
                "(sending ActionComplete to continue workflow)"
            )
            with contextlib.suppress(KeyError):
                await ctx.shared_state.delete(EXTERNAL_LOOP_STATE_KEY)
            await ctx.send_message(ActionComplete())
            return

        # Continue the loop - condition still true
        if iteration < max_iterations:
            # Update loop state for next iteration
            loop_state.iteration = iteration + 1
            await ctx.shared_state.set(EXTERNAL_LOOP_STATE_KEY, loop_state)

            # Emit another request for external input
            request = AgentExternalInputRequest(
                request_id=str(uuid.uuid4()),
                agent_name=agent_name,
                agent_response=accumulated_response,
                iteration=iteration,
                messages=all_messages,
                function_calls=tool_calls,
            )
            logger.info(f"InvokeAzureAgent: yielding for external input (iteration {iteration})")
            await ctx.request_info(request, AgentExternalInputResponse)
            return

        logger.warning(f"InvokeAzureAgent: external loop exceeded max iterations ({max_iterations})")

        # Loop complete - clean up and send completion
        with contextlib.suppress(KeyError):
            await ctx.shared_state.delete(EXTERNAL_LOOP_STATE_KEY)

        await ctx.send_message(ActionComplete())


class InvokeToolExecutor(DeclarativeActionExecutor):
    """Executor that invokes a registered tool/function.

    Tools are simpler than agents - they take input, perform an action,
    and return a result synchronously (or with a simple async call).
    """

    @handler
    async def handle_action(
        self,
        trigger: Any,
        ctx: WorkflowContext[ActionComplete],
    ) -> None:
        """Handle the tool invocation."""
        state = await self._ensure_state_initialized(ctx, trigger)

        tool_name = self._action_def.get("tool") or self._action_def.get("toolName", "")
        input_expr = self._action_def.get("input")
        output_property = self._action_def.get("output", {}).get("property") or self._action_def.get("resultProperty")
        parameters = self._action_def.get("parameters", {})

        # Get tools registry
        try:
            tool_registry: dict[str, Any] | None = await ctx.shared_state.get(TOOL_REGISTRY_KEY)
        except KeyError:
            tool_registry = {}

        tool: Any = tool_registry.get(tool_name) if tool_registry else None

        if tool is None:
            error_msg = f"Tool '{tool_name}' not found in registry"
            if output_property:
                await state.set(output_property, {"error": error_msg})
            await ctx.send_message(ActionComplete())
            return

        # Build parameters
        params: dict[str, Any] = {}
        for param_name, param_expression in parameters.items():
            params[param_name] = await state.eval_if_expression(param_expression)

        # Add main input if specified
        if input_expr:
            params["input"] = await state.eval_if_expression(input_expr)

        try:
            # Invoke the tool
            if callable(tool):
                from inspect import isawaitable

                result = tool(**params)
                if isawaitable(result):
                    result = await result

                # Store result
                if output_property:
                    await state.set(output_property, result)

        except Exception as e:
            if output_property:
                await state.set(output_property, {"error": str(e)})
            await ctx.send_message(ActionComplete())
            return

        await ctx.send_message(ActionComplete())


# Mapping of agent action kinds to executor classes
AGENT_ACTION_EXECUTORS: dict[str, type[DeclarativeActionExecutor]] = {
    "InvokeAzureAgent": InvokeAzureAgentExecutor,
    "InvokeTool": InvokeToolExecutor,
}
