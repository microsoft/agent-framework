# Copyright (c) Microsoft. All rights reserved.

"""Agent invocation executors for declarative workflows.

These executors handle invoking Microsoft Foundry agents and other AI agents,
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
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any, cast

from agent_framework import (
    Content,
    Message,
    WorkflowContext,
    handler,
    response_handler,
)
from agent_framework.exceptions import AgentInvalidRequestException, AgentInvalidResponseException

from ._declarative_base import (
    ActionComplete,
    DeclarativeActionExecutor,
    DeclarativeWorkflowState,
)

logger = logging.getLogger(__name__)

_CODE_FENCE = "```"
_JSON_CODE_FENCE_QUALIFIER = "json"
_MAX_JSON_DECODE_BUDGET_MULTIPLIER = 4
_NO_JSON = object()


def _iter_fenced_blocks(text: str, *, require_json_qualifier: bool) -> Iterator[str]:
    """Yield non-overlapping fenced blocks in source order."""
    search_start = 0
    while True:
        opening_index = text.find(_CODE_FENCE, search_start)
        if opening_index < 0:
            return

        content_start = opening_index + len(_CODE_FENCE)
        if require_json_qualifier:
            if not text.startswith(_JSON_CODE_FENCE_QUALIFIER, content_start):
                search_start = content_start
                continue

            qualifier_end = content_start + len(_JSON_CODE_FENCE_QUALIFIER)
            if (
                qualifier_end < len(text)
                and not text[qualifier_end].isspace()
                and text[qualifier_end] not in "{["
                and not text.startswith(_CODE_FENCE, qualifier_end)
            ):
                search_start = content_start
                continue
            content_start = qualifier_end

        while content_start < len(text) and text[content_start].isspace():
            content_start += 1

        closing_index = text.find(_CODE_FENCE, content_start)
        if closing_index < 0:
            return

        yield text[content_start:closing_index].strip()
        search_start = closing_index + len(_CODE_FENCE)


def _index_escaped_quotes(text: str) -> bytearray:
    """Index quote characters preceded by an odd-length backslash run."""
    escaped_quotes = bytearray(len(text))
    backslash_count = 0

    for index, char in enumerate(text):
        if char == "\\":
            backslash_count += 1
            continue

        if char == '"' and backslash_count % 2 == 1:
            escaped_quotes[index] = 1
        backslash_count = 0

    return escaped_quotes


def _index_json_candidates_forward(text: str, escaped_quotes: bytearray) -> set[tuple[int, int]]:
    """Index JSON candidate ranges from left to right."""
    candidates: set[tuple[int, int]] = set()
    object_openings: list[int] = []
    array_openings: list[int] = []
    in_string = False

    for index, char in enumerate(text):
        if not object_openings and not array_openings:
            if char in "{[":
                (object_openings if char == "{" else array_openings).append(index)
            continue

        if char == '"' and not escaped_quotes[index]:
            in_string = not in_string
            continue

        if in_string:
            continue

        if char in "{[":
            (object_openings if char == "{" else array_openings).append(index)
        elif char == "}" and object_openings:
            candidates.add((object_openings.pop(), index))
        elif char == "]" and array_openings:
            candidates.add((array_openings.pop(), index))

    return candidates


def _index_json_candidates_reverse(text: str, escaped_quotes: bytearray) -> set[tuple[int, int]]:
    """Index JSON candidate ranges from right to left."""
    candidates: set[tuple[int, int]] = set()
    object_closings: list[int] = []
    array_closings: list[int] = []
    in_string = False

    for index in range(len(text) - 1, -1, -1):
        char = text[index]
        if not object_closings and not array_closings:
            if char in "}]":
                (object_closings if char == "}" else array_closings).append(index)
            continue

        if char == '"' and not escaped_quotes[index]:
            in_string = not in_string
            continue

        if in_string:
            continue

        if char in "}]":
            (object_closings if char == "}" else array_closings).append(index)
        elif char == "{" and object_closings:
            candidates.add((index, object_closings.pop()))
        elif char == "[" and array_closings:
            candidates.add((index, array_closings.pop()))

    return candidates


def _find_last_decodable_json(text: str) -> Any:
    """Find the last decodable JSON object or array within text."""
    escaped_quotes = _index_escaped_quotes(text)
    candidates = _index_json_candidates_forward(text, escaped_quotes)
    candidates.update(_index_json_candidates_reverse(text, escaped_quotes))

    candidate_groups: list[tuple[int, int, list[tuple[int, int]]]] = []
    for candidate in sorted(candidates):
        json_start, json_end = candidate
        if not candidate_groups or json_start > candidate_groups[-1][1]:
            candidate_groups.append((json_start, json_end, [candidate]))
            continue

        group_start, group_end, group_candidates = candidate_groups[-1]
        group_candidates.append(candidate)
        candidate_groups[-1] = (group_start, max(group_end, json_end), group_candidates)

    for group_start, group_end, group_candidates in reversed(candidate_groups):
        group_span = group_end - group_start + 1
        primary_decode_budget = group_span * (_MAX_JSON_DECODE_BUDGET_MULTIPLIER // 2)
        recovery_decode_budget = group_span * (
            _MAX_JSON_DECODE_BUDGET_MULTIPLIER - (_MAX_JSON_DECODE_BUDGET_MULTIPLIER // 2)
        )
        attempted_candidates: set[tuple[int, int]] = set()
        last_json: Any = _NO_JSON
        consumed_end = -1
        candidate_index = 0

        while candidate_index < len(group_candidates) and primary_decode_budget > 0:
            json_start, json_end = group_candidates[candidate_index]
            candidate_index += 1
            if json_start <= consumed_end:
                continue

            candidate_length = json_end - json_start + 1
            if candidate_length > primary_decode_budget:
                continue

            primary_decode_budget -= candidate_length
            attempted_candidates.add((json_start, json_end))
            try:
                last_json = json.loads(text[json_start : json_end + 1])
            except json.JSONDecodeError:
                continue

            consumed_end = json_end
            while candidate_index < len(group_candidates) and group_candidates[candidate_index][0] <= consumed_end:
                candidate_index += 1

        recovery_candidates = sorted(
            group_candidates,
            key=lambda candidate: (candidate[1] - candidate[0], -candidate[0]),
        )
        recovered_json: Any = _NO_JSON
        recovered_range: tuple[int, int] | None = None
        for json_start, json_end in recovery_candidates:
            if recovery_decode_budget == 0:
                break
            if (json_start, json_end) in attempted_candidates or json_start <= consumed_end:
                continue

            candidate_length = json_end - json_start + 1
            if candidate_length > recovery_decode_budget:
                continue

            recovery_decode_budget -= candidate_length
            try:
                candidate_json = json.loads(text[json_start : json_end + 1])
            except json.JSONDecodeError:
                continue

            candidate_contains_recovered = (
                recovered_range is not None and json_start <= recovered_range[0] and json_end >= recovered_range[1]
            )
            recovered_contains_candidate = (
                recovered_range is not None and recovered_range[0] <= json_start and recovered_range[1] >= json_end
            )
            if (
                recovered_range is None
                or candidate_contains_recovered
                or (not recovered_contains_candidate and json_start > recovered_range[0])
            ):
                recovered_json = candidate_json
                recovered_range = (json_start, json_end)

        if recovered_json is not _NO_JSON:
            return recovered_json
        if last_json is not _NO_JSON:
            return last_json

    raise json.JSONDecodeError("No valid JSON found in response", text, 0)


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
        Parsed JSON, or None if the response is empty.

    Raises:
        json.JSONDecodeError: If no valid JSON can be extracted
    """
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

    # Exactly-qualified JSON fences take precedence over plain fences.
    for require_json_qualifier in (True, False):
        last_fenced_json: Any = _NO_JSON
        for block in _iter_fenced_blocks(text, require_json_qualifier=require_json_qualifier):
            try:
                last_fenced_json = json.loads(block)
            except json.JSONDecodeError:
                continue
        if last_fenced_json is not _NO_JSON:
            return last_fenced_json

    return _find_last_decodable_json(text)


def _validate_conversation_history(messages: list[Message], agent_name: str) -> None:
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
        if not (contents := getattr(msg, "contents", None)):
            continue
        for content in contents:
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


@dataclass
class AgentResult:
    """Result from an agent invocation."""

    success: bool
    response: str
    agent_name: str
    messages: list[Message] = field(default_factory=lambda: cast(list[Message], []))
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
                    async for event in workflow.run(ctx=ctx, stream=True):
                        print(event)
    """

    request_id: str
    agent_name: str
    agent_response: str
    iteration: int = 0
    messages: list[Message] = field(default_factory=lambda: cast(list[Message], []))
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
    messages: list[Message] = field(default_factory=lambda: cast(list[Message], []))
    function_results: dict[str, Content] = field(default_factory=lambda: cast(dict[str, Content], {}))


@dataclass
class ExternalLoopState:
    """State saved for external loop resumption.

    Stored in workflow state to allow the response_handler to
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
    """Executor that invokes a Microsoft Foundry agent.

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
            if agent_config.startswith("="):
                evaluated = state.eval_if_expression(agent_config)
                return str(evaluated) if evaluated is not None else None
            return agent_config

        if isinstance(agent_config, dict):
            agent_dict = cast(dict[str, Any], agent_config)
            name = agent_dict.get("name")
            if name is not None and isinstance(name, str):
                if name.startswith("="):
                    evaluated = state.eval_if_expression(name)
                    return str(evaluated) if evaluated is not None else None
                return str(name)

        agent_name = self._action_def.get("agentName")
        if isinstance(agent_name, str):
            if agent_name.startswith("="):
                evaluated = state.eval_if_expression(agent_name)
                return str(evaluated) if evaluated is not None else None
            return agent_name
        return None

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
        evaluated_id = state.eval_if_expression(conversation_id_expr)
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
            evaluated_args[key] = state.eval_if_expression(value)

        # Evaluate messages/input
        if messages_expr:
            evaluated_input: Any = state.eval_if_expression(messages_expr)
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
        input_text: str = str(state.get("Local.input") or state.get("Local.userInput") or "")
        if not input_text:
            # Try System.LastMessage.Text (used by external loop and agent chaining)
            last_message: Any = state.get("System.LastMessage")
            if isinstance(last_message, dict):
                last_msg_dict = cast(dict[str, Any], last_message)
                text_val: Any = last_msg_dict.get("Text", "")
                input_text = str(text_val) if text_val else ""
        if not input_text:
            # Fall back to workflow inputs (for first agent in chain)
            inputs: Any = state.get("Workflow.Inputs")
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
        all_messages: list[Message] = []
        tool_calls: list[Content] = []

        # Add user input to conversation history first (via state.append only)
        if input_text:
            user_message = Message(role="user", contents=[input_text])
            state.append(messages_path, user_message)

        # Get conversation history from state AFTER adding user message
        # Note: We get a fresh copy to avoid mutation issues
        conversation_history: list[Message] = state.get(messages_path) or []

        # Build messages list for agent (use history if available, otherwise just input)
        messages_for_agent: list[Message] | str = conversation_history if conversation_history else input_text

        # Validate conversation history before invoking agent
        if isinstance(messages_for_agent, list) and messages_for_agent:
            _validate_conversation_history(messages_for_agent, agent_name)

        # Retrieve kwargs passed to workflow.run() so they propagate to agent tools
        from agent_framework._workflows._const import WORKFLOW_RUN_KWARGS_KEY

        run_kwargs: dict[str, Any] = ctx.get_state(WORKFLOW_RUN_KWARGS_KEY, {})
        options: dict[str, Any] | None = None
        if run_kwargs:
            # Merge caller-provided options to avoid duplicate keyword argument
            options = dict(run_kwargs.get("options") or {})
            options["additional_function_arguments"] = run_kwargs
            # Exclude 'options' from splat to avoid TypeError on duplicate keyword
            run_kwargs = {k: v for k, v in run_kwargs.items() if k != "options"}

        # Use run() method to get properly structured messages (including tool calls and results)
        # This is critical for multi-turn conversations where tool calls must be followed
        # by their results in the message history
        result: Any = await agent.run(messages_for_agent, options=options, **run_kwargs)
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
                all_messages = list(cast(list[Message], result_messages))
            result_tool_calls: Any = getattr(result, "tool_calls", None)
            if result_tool_calls is not None:
                tool_calls = list(cast(list[Content], result_tool_calls))

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
                state.append(messages_path, msg)
        elif accumulated_response:
            # No messages returned, create a simple assistant message
            logger.debug(
                "Agent '%s': No messages in response, creating simple assistant message",
                agent_name,
            )
            assistant_message = Message(role="assistant", contents=[accumulated_response])
            state.append(messages_path, assistant_message)

        # Store results in state - support both schema formats:
        # - Graph mode: Agent.response, Agent.name
        # - Interpreter mode: Agent.text, Agent.messages, Agent.toolCalls
        state.set("Agent.response", accumulated_response)
        state.set("Agent.name", agent_name)
        state.set("Agent.text", accumulated_response)
        state.set("Agent.messages", all_messages if all_messages else [])
        state.set("Agent.toolCalls", tool_calls if tool_calls else [])

        # Store System.LastMessage for externalLoop.when condition evaluation
        state.set("System.LastMessage", {"Text": accumulated_response})

        # Store in output variables (.NET style)
        if messages_var:
            output_path = _normalize_variable_path(messages_var)
            state.set(output_path, all_messages if all_messages else accumulated_response)

        if response_obj_var:
            output_path = _normalize_variable_path(response_obj_var)
            # Try to extract and parse JSON from the response
            try:
                parsed = _extract_json_from_response(accumulated_response) if accumulated_response else None
                logger.debug(f"InvokeAzureAgent: parsed responseObject for '{output_path}': type={type(parsed)}")
                state.set(output_path, parsed)
            except (json.JSONDecodeError, TypeError) as e:
                logger.warning(f"InvokeAzureAgent: failed to parse JSON for '{output_path}': {e}, storing as string")
                state.set(output_path, accumulated_response)

        # Store in result property (Python style)
        if result_property:
            state.set(result_property, accumulated_response)

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
        run(responses=..., stream=True), the handle_external_input_response handler
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
                agent_registry: dict[str, Any] | None = ctx.state.get(AGENT_REGISTRY_KEY)
            except KeyError:
                agent_registry = {}
            agent = agent_registry.get(agent_name) if agent_registry else None

        if agent is None:
            error_msg = f"Agent '{agent_name}' not found in registry"
            logger.error(f"InvokeAzureAgent: {error_msg}")
            state.set("Agent.error", error_msg)
            if result_property:
                state.set(result_property, {"error": error_msg})
            raise AgentInvalidRequestException(f"Agent '{agent_name}' invocation failed: not found in registry")

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
        except (AgentInvalidRequestException, AgentInvalidResponseException):
            raise  # Re-raise our own errors
        except Exception as e:
            logger.error(f"InvokeAzureAgent: error invoking agent '{agent_name}': {e}")
            state.set("Agent.error", str(e))
            if result_property:
                state.set(result_property, {"error": str(e)})
            raise AgentInvalidResponseException(f"Agent '{agent_name}' invocation failed: {e}") from e

        # Check external loop condition
        if external_loop_when:
            should_continue = state.eval(external_loop_when)
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
                ctx.state.set(EXTERNAL_LOOP_STATE_KEY, loop_state)

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
        state = self._get_state(ctx.state)

        # Retrieve saved loop state
        loop_state: ExternalLoopState | None = ctx.state.get(EXTERNAL_LOOP_STATE_KEY)
        if loop_state is None:
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
        state.set("Local.userInput", input_text)
        state.set("System.LastMessage", {"Text": input_text})

        # Check if we should continue BEFORE invoking the agent
        # This matches .NET behavior where the condition checks the user's input
        should_continue = state.eval(external_loop_when)
        should_continue = bool(should_continue) if should_continue is not None else False

        logger.debug(
            f"InvokeAzureAgent: external loop condition '{str(external_loop_when)[:50]}' = "
            f"{should_continue} (iteration {iteration}) for input '{input_text[:30]}...'"
        )

        if not should_continue:
            # User input caused loop to exit - clean up and complete
            with contextlib.suppress(KeyError):
                ctx.state.delete(EXTERNAL_LOOP_STATE_KEY)
            await ctx.send_message(ActionComplete())
            return

        # Get agent from registry
        agent: Any = self._agents.get(agent_name) if self._agents else None
        if agent is None:
            try:
                agent_registry: dict[str, Any] | None = ctx.state.get(AGENT_REGISTRY_KEY)
            except KeyError:
                agent_registry = {}
            agent = agent_registry.get(agent_name) if agent_registry else None

        if agent is None:
            logger.error(f"InvokeAzureAgent: agent '{agent_name}' not found during loop resumption")
            raise AgentInvalidRequestException(
                f"Agent '{agent_name}' invocation failed: not found during loop resumption"
            )

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
        except (AgentInvalidRequestException, AgentInvalidResponseException):
            raise  # Re-raise our own errors
        except Exception as e:
            logger.error(f"InvokeAzureAgent: error invoking agent '{agent_name}' during loop: {e}")
            state.set("Agent.error", str(e))
            raise AgentInvalidResponseException(f"Agent '{agent_name}' invocation failed: {e}") from e

        # Re-evaluate the condition AFTER the agent responds
        # This is critical: the agent's response may have set NeedsTicket=true or IsResolved=true
        should_continue = state.eval(external_loop_when)
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
                ctx.state.delete(EXTERNAL_LOOP_STATE_KEY)
            await ctx.send_message(ActionComplete())
            return

        # Continue the loop - condition still true
        if iteration < max_iterations:
            # Update loop state for next iteration
            loop_state.iteration = iteration + 1
            ctx.state.set(EXTERNAL_LOOP_STATE_KEY, loop_state)

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
            ctx.state.delete(EXTERNAL_LOOP_STATE_KEY)

        await ctx.send_message(ActionComplete())


# Mapping of agent action kinds to executor classes
AGENT_ACTION_EXECUTORS: dict[str, type[DeclarativeActionExecutor]] = {
    "InvokeAzureAgent": InvokeAzureAgentExecutor,
}
