# Copyright (c) Microsoft. All rights reserved.

"""Tool invocation executors for declarative workflows.

Provides base abstractions and concrete executors for invoking various tool types
(functions, APIs, MCP servers, etc.) with support for approval flows and structured output.

This module is designed for extensibility:
- BaseToolExecutor provides common patterns (registry lookup, approval flow, output formatting)
- Concrete executors (InvokeFunctionToolExecutor) implement tool-specific invocation logic
- New tool types can be added by subclassing BaseToolExecutor
"""

import json
import logging
import uuid
from abc import abstractmethod
from dataclasses import dataclass, field
from inspect import isawaitable
from typing import Any

from agent_framework import (
    Content,
    Message,
    WorkflowContext,
    handler,
    response_handler,
)

from ._declarative_base import (
    ActionComplete,
    DeclarativeActionExecutor,
    DeclarativeWorkflowState,
)
from ._executors_agents import TOOL_REGISTRY_KEY

logger = logging.getLogger(__name__)

# Registry key for function tools in State - reuse existing key so functions registered
# at runtime are discoverable by both agent-based and function-based tool executors.
FUNCTION_TOOL_REGISTRY_KEY = TOOL_REGISTRY_KEY

# State key prefix for storing approval state during yield/resume.
# The executor's ID is appended to create a per-executor key.
TOOL_APPROVAL_STATE_KEY = "_tool_approval_state"


# ============================================================================
# Request/Response Types for Approval Flow
# ============================================================================


@dataclass
class ToolApprovalRequest:
    """Request for approval before invoking a tool.

    Emitted when requireApproval=true, signaling that the workflow should yield
    and wait for user approval before invoking the tool.

    This follows the same pattern as AgentExternalInputRequest from _executors_agents.py,
    allowing consistent handling of human-in-loop scenarios across agents and tools.

    Attributes:
        request_id: Unique identifier for this approval request.
        function_name: Evaluated function name to be invoked.
        arguments: Evaluated arguments to be passed to the function.
    """

    request_id: str
    function_name: str
    arguments: dict[str, Any]


@dataclass
class ToolApprovalResponse:
    """Response to a ToolApprovalRequest.

    Provided by the caller to approve or reject tool invocation.

    Attributes:
        approved: Whether the tool invocation was approved.
        reason: Optional reason for rejection.
    """

    approved: bool
    reason: str | None = None


# ============================================================================
# State Types for Approval Flow
# ============================================================================


@dataclass
class ToolApprovalState:
    """State saved during approval yield for resumption.

    Stored in State under a per-executor key when requireApproval=true.
    Retrieved by handle_approval_response() to continue execution.
    """

    function_name: str
    arguments: dict[str, Any]
    output_messages_var: str | None
    output_result_var: str | None
    auto_send: bool


# ============================================================================
# Result Types
# ============================================================================


@dataclass
class ToolInvocationResult:
    """Result from a tool invocation.

    Attributes:
        success: Whether the invocation succeeded.
        result: The return value from the tool (if successful).
        error: Error message (if failed).
        messages: Message list format for conversation history.
        rejected: Whether the invocation was rejected during approval.
        rejection_reason: Reason for rejection.
    """

    success: bool
    result: Any = None
    error: str | None = None
    messages: list[Message] = field(default_factory=list)
    rejected: bool = False
    rejection_reason: str | None = None


# ============================================================================
# Helper Functions
# ============================================================================


def _normalize_variable_path(variable: str) -> str:
    """Normalize variable names to ensure they have a scope prefix.

    Args:
        variable: Variable name like 'Local.X' or 'weatherResult'

    Returns:
        The variable path with a scope prefix (defaults to Local if none provided)
    """
    if variable.startswith(("Local.", "System.", "Workflow.", "Agent.", "Conversation.")):
        return variable
    if "." in variable:
        return variable
    return "Local." + variable


# ============================================================================
# Base Tool Executor (Abstract)
# ============================================================================


class BaseToolExecutor(DeclarativeActionExecutor):
    """Base class for tool invocation executors.

    Provides common functionality for all tool-like executors:
    - Tool registry lookup (State + WorkflowFactory registration)
    - Approval flow (request_info pattern with yield/resume)
    - Output formatting (messages as Message list + result variable)
    - Error handling (stores error in output, doesn't raise)

    Subclasses must implement:
    - _invoke_tool(): Perform the actual tool invocation

    YAML Schema (common fields):
        kind: <ToolKind>
        id: unique_id
        functionName: function_to_call  # required, supports =expression syntax
        requireApproval: true  # optional, default=false
        arguments:  # optional dictionary
          param1: value1
          param2: =Local.dynamicValue
        output:
          messages: Local.toolCallMessages  # Message list
          result: Local.toolResult
          autoSend: true  # optional, default=true
    """

    def __init__(
        self,
        action_def: dict[str, Any],
        *,
        id: str | None = None,
        tools: dict[str, Any] | None = None,
    ):
        """Initialize the tool executor.

        Args:
            action_def: The action definition from YAML
            id: Optional executor ID
            tools: Registry of tool instances by name (from WorkflowFactory)
        """
        super().__init__(action_def, id=id)
        self._tools = tools or {}

    @abstractmethod
    async def _invoke_tool(
        self,
        tool: Any,
        function_name: str,
        arguments: dict[str, Any],
        state: DeclarativeWorkflowState,
    ) -> Any:
        """Invoke the tool with the given arguments.

        Args:
            tool: The tool instance to invoke
            function_name: Function/method name to call
            arguments: Arguments to pass
            state: Workflow state

        Returns:
            The result from the tool invocation

        Raises:
            Any exception from the tool invocation
        """
        pass

    def _get_tool(
        self,
        function_name: str,
        ctx: WorkflowContext[Any, Any],
    ) -> Any | None:
        """Get tool from registry.

        Checks both WorkflowFactory registry (self._tools) and State registry.

        Args:
            function_name: Name of the function
            ctx: Workflow context

        Returns:
            The tool/function, or None if not found
        """
        # Check WorkflowFactory registry first (passed in constructor)
        tool = self._tools.get(function_name)
        if tool is not None:
            return tool

        # Check State registry (for runtime registration)
        try:
            tool_registry: dict[str, Any] | None = ctx.state.get(FUNCTION_TOOL_REGISTRY_KEY)
            if tool_registry:
                return tool_registry.get(function_name)
        except KeyError:
            logger.debug(
                "%s: tool registry key '%s' not found in state "
                "(this is normal if tools are only registered via WorkflowFactory)",
                self.__class__.__name__,
                FUNCTION_TOOL_REGISTRY_KEY,
            )

        return None

    def _get_output_config(self) -> tuple[str | None, str | None, bool]:
        """Parse output configuration from action definition.

        Returns:
            Tuple of (messages_var, result_var, auto_send)
        """
        output_config = self._action_def.get("output", {})

        if not isinstance(output_config, dict):
            return None, None, True

        messages_var = output_config.get("messages")
        result_var = output_config.get("result")
        auto_send = bool(output_config.get("autoSend", True))

        return (
            str(messages_var) if messages_var else None,
            str(result_var) if result_var else None,
            auto_send,
        )

    def _store_result(
        self,
        result: ToolInvocationResult,
        state: DeclarativeWorkflowState,
        messages_var: str | None,
        result_var: str | None,
    ) -> None:
        """Store tool invocation result in workflow state.

        Args:
            result: The tool invocation result
            state: Workflow state
            messages_var: Variable path for messages output
            result_var: Variable path for result output
        """
        # Store messages if variable specified
        if messages_var:
            path = _normalize_variable_path(messages_var)
            state.set(path, result.messages)

        # Store result if variable specified
        if result_var:
            path = _normalize_variable_path(result_var)
            if result.rejected:
                state.set(
                    path,
                    {
                        "approved": False,
                        "rejected": True,
                        "reason": result.rejection_reason,
                    },
                )
            elif result.success:
                state.set(path, result.result)
            else:
                state.set(
                    path,
                    {
                        "error": result.error,
                    },
                )

    async def _format_messages(
        self,
        function_name: str,
        arguments: dict[str, Any],
        result: Any,
    ) -> list[Message]:
        """Format tool invocation as Message list.

        Creates tool call + tool result message pair for conversation history,
        following the same format as agent tool calls.

        Args:
            function_name: Function name invoked
            arguments: Arguments passed
            result: Result from invocation

        Returns:
            List of Message objects [tool_call_message, tool_result_message]
        """
        call_id = str(uuid.uuid4())

        # Safely serialize arguments to JSON
        try:
            arguments_str = json.dumps(arguments) if isinstance(arguments, dict) else str(arguments)
        except (TypeError, ValueError) as e:
            logger.warning(f"Failed to serialize arguments to JSON: {e}")
            arguments_str = str(arguments)

        # Tool call message (from assistant)
        tool_call_content = Content.from_function_call(
            call_id=call_id,
            name=function_name,
            arguments=arguments_str,
        )
        tool_call_message = Message(
            role="assistant",
            contents=[tool_call_content],
        )

        # Safely serialize result to JSON
        try:
            result_str = json.dumps(result) if not isinstance(result, str) else result
        except (TypeError, ValueError) as e:
            logger.warning(f"Failed to serialize result to JSON: {e}")
            result_str = str(result)

        tool_result_content = Content.from_function_result(
            call_id=call_id,
            result=result_str,
        )
        tool_result_message = Message(
            role="tool",
            contents=[tool_result_content],
        )

        return [tool_call_message, tool_result_message]

    async def _execute_tool_invocation(
        self,
        function_name: str,
        arguments: dict[str, Any],
        state: DeclarativeWorkflowState,
        ctx: WorkflowContext[Any, Any],
    ) -> ToolInvocationResult:
        """Execute the tool invocation.

        Args:
            function_name: Function to invoke
            arguments: Arguments to pass
            state: Workflow state
            ctx: Workflow context

        Returns:
            ToolInvocationResult with outcome
        """
        # Get tool from registry
        tool = self._get_tool(function_name, ctx)
        if tool is None:
            error_msg = f"Function '{function_name}' not found in registry"
            logger.error(f"{self.__class__.__name__}: {error_msg}")
            return ToolInvocationResult(
                success=False,
                error=error_msg,
            )

        try:
            # Invoke the tool (subclass implements this)
            result_value = await self._invoke_tool(
                tool=tool,
                function_name=function_name,
                arguments=arguments,
                state=state,
            )

            # Format as messages for conversation history
            messages = await self._format_messages(
                function_name=function_name,
                arguments=arguments,
                result=result_value,
            )

            return ToolInvocationResult(
                success=True,
                result=result_value,
                messages=messages,
            )

        except Exception as e:
            logger.error(
                "%s: error invoking function '%s': %s: %s",
                self.__class__.__name__,
                function_name,
                type(e).__name__,
                e,
                exc_info=True,
            )
            return ToolInvocationResult(
                success=False,
                error=f"{type(e).__name__}: {e}",
            )

    @handler
    async def handle_action(
        self,
        trigger: Any,
        ctx: WorkflowContext[ActionComplete, str],
    ) -> None:
        """Handle the tool invocation with optional approval flow.

        When requireApproval=true:
        1. Saves invocation state to State (keyed by executor ID)
        2. Emits ToolApprovalRequest via ctx.request_info()
        3. Workflow yields (returns without ActionComplete)
        4. Resumes in handle_approval_response() when user responds
        """
        state = await self._ensure_state_initialized(ctx, trigger)

        # Parse output configuration early so we can store errors
        messages_var, result_var, auto_send = self._get_output_config()

        # Get and evaluate function name (required)
        function_name_expr = self._action_def.get("functionName")
        if not function_name_expr:
            error_msg = f"Action '{self.id}' is missing required 'functionName' field"
            logger.error(f"{self.__class__.__name__}: {error_msg}")
            if result_var:
                state.set(_normalize_variable_path(result_var), {"error": error_msg})
            await ctx.send_message(ActionComplete())
            return

        function_name = state.eval_if_expression(function_name_expr)
        if not function_name:
            error_msg = f"Action '{self.id}': functionName expression evaluated to empty"
            logger.error(f"{self.__class__.__name__}: {error_msg}")
            if result_var:
                state.set(_normalize_variable_path(result_var), {"error": error_msg})
            await ctx.send_message(ActionComplete())
            return
        function_name = str(function_name)

        # Evaluate arguments
        arguments_def = self._action_def.get("arguments", {})
        arguments: dict[str, Any] = {}
        if arguments_def is not None and not isinstance(arguments_def, dict):
            logger.warning(
                "%s: 'arguments' must be a dictionary, got %s - ignoring",
                self.__class__.__name__,
                type(arguments_def).__name__,
            )
        elif isinstance(arguments_def, dict):
            for key, value in arguments_def.items():
                arguments[key] = state.eval_if_expression(value)

        # Check if approval is required
        require_approval = self._action_def.get("requireApproval", False)

        if require_approval:
            # Save state for resumption (keyed by executor ID to avoid collisions)
            approval_state = ToolApprovalState(
                function_name=function_name,
                arguments=arguments,
                output_messages_var=messages_var,
                output_result_var=result_var,
                auto_send=auto_send,
            )
            approval_key = f"{TOOL_APPROVAL_STATE_KEY}_{self.id}"
            ctx.state.set(approval_key, approval_state)

            # Emit approval request - workflow yields here
            request = ToolApprovalRequest(
                request_id=str(uuid.uuid4()),
                function_name=function_name,
                arguments=arguments,
            )
            logger.info(f"{self.__class__.__name__}: requesting approval for '{function_name}'")
            await ctx.request_info(request, ToolApprovalResponse)
            # Workflow yields - will resume in handle_approval_response
            return

        # No approval required - invoke directly
        result = await self._execute_tool_invocation(
            function_name=function_name,
            arguments=arguments,
            state=state,
            ctx=ctx,
        )

        self._store_result(result, state, messages_var, result_var)
        if auto_send and result.success and result.result is not None:
            await ctx.yield_output(str(result.result))
        await ctx.send_message(ActionComplete())

    @response_handler
    async def handle_approval_response(
        self,
        original_request: ToolApprovalRequest,
        response: ToolApprovalResponse,
        ctx: WorkflowContext[ActionComplete, str],
    ) -> None:
        """Handle response to a ToolApprovalRequest.

        Called when the workflow resumes after yielding for approval.
        Either executes the tool (if approved) or stores rejection status.
        """
        state = self._get_state(ctx.state)
        approval_key = f"{TOOL_APPROVAL_STATE_KEY}_{self.id}"

        # Retrieve saved invocation state
        try:
            approval_state: ToolApprovalState = ctx.state.get(approval_key)
        except KeyError:
            error_msg = "Approval state not found, cannot resume tool invocation"
            logger.error(f"{self.__class__.__name__}: {error_msg}")
            # Try to store error - get output config from action def as fallback
            _, result_var, _ = self._get_output_config()
            if result_var and state:
                state.set(_normalize_variable_path(result_var), {"error": error_msg})
            await ctx.send_message(ActionComplete())
            return

        # Clean up approval state
        try:
            ctx.state.delete(approval_key)
        except KeyError:
            logger.warning(f"{self.__class__.__name__}: approval state already deleted")

        function_name = approval_state.function_name
        arguments = approval_state.arguments
        messages_var = approval_state.output_messages_var
        result_var = approval_state.output_result_var
        auto_send = approval_state.auto_send

        # Check if approved
        if not response.approved:
            logger.info(f"{self.__class__.__name__}: tool invocation rejected: {response.reason}")

            # Store rejection status (don't raise error)
            result = ToolInvocationResult(
                success=False,
                rejected=True,
                rejection_reason=response.reason,
                messages=[
                    Message(
                        role="assistant",
                        text=f"Function '{function_name}' was rejected: {response.reason or 'No reason provided'}",
                    )
                ],
            )
            self._store_result(result, state, messages_var, result_var)
            await ctx.send_message(ActionComplete())
            return

        # Approved - execute the invocation
        result = await self._execute_tool_invocation(
            function_name=function_name,
            arguments=arguments,
            state=state,
            ctx=ctx,
        )

        self._store_result(result, state, messages_var, result_var)
        if auto_send and result.success and result.result is not None:
            await ctx.yield_output(str(result.result))
        await ctx.send_message(ActionComplete())


# ============================================================================
# Function Tool Executor (Concrete)
# ============================================================================


class InvokeFunctionToolExecutor(BaseToolExecutor):
    """Executor that invokes a Python function as a tool.

    This executor supports invoking registered Python functions with:
    - Expression evaluation for functionName and arguments
    - Optional approval flow (yield/resume pattern)
    - Async function support
    - Message list output for conversation history

    YAML Schema:
        kind: InvokeFunctionTool
        id: invoke_function_example
        functionName: get_weather  # required, supports =expression syntax
        requireApproval: true  # optional, default=false
        arguments:  # optional dictionary
          location: =Local.location
          unit: F
        output:
          messages: Local.weatherToolCallItems  # Message list
          result: Local.WeatherInfo
          autoSend: true  # optional, default=true

    Tool Registration:
        Tools can be registered via:
        1. WorkflowFactory.register_tool("name", func) - preferred
        2. Setting FUNCTION_TOOL_REGISTRY_KEY in State at runtime

    Examples:
        .. code-block:: python

            from agent_framework_declarative import WorkflowFactory


            def get_weather(location: str, unit: str = "F") -> dict:
                return {"temp": 72, "unit": unit, "location": location}


            async def fetch_data(url: str) -> dict:
                # async function example
                return {"data": "..."}


            factory = (
                WorkflowFactory().register_tool("get_weather", get_weather).register_tool("fetch_data", fetch_data)
            )

            workflow = factory.create_workflow_from_yaml_path("workflow.yaml")
    """

    async def _invoke_tool(
        self,
        tool: Any,
        function_name: str,
        arguments: dict[str, Any],
        state: DeclarativeWorkflowState,
    ) -> Any:
        """Invoke the function tool.

        Supports:
        - Direct callable functions
        - Async functions (via inspect.isawaitable)

        Args:
            tool: The tool/function to invoke
            function_name: Name of the function (for error messages)
            arguments: Arguments to pass to the function
            state: Workflow state (not used for function tools)

        Returns:
            The result from the function invocation

        Raises:
            ValueError: If the tool is not callable
        """
        if not callable(tool):
            raise ValueError(f"Function '{function_name}' is not callable")

        # Invoke the function
        result = tool(**arguments)

        # Handle async functions
        if isawaitable(result):
            result = await result

        return result


# ============================================================================
# Executor Registry Export
# ============================================================================

TOOL_ACTION_EXECUTORS: dict[str, type[DeclarativeActionExecutor]] = {
    "InvokeFunctionTool": InvokeFunctionToolExecutor,
}
