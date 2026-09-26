# Copyright (c) Microsoft. All rights reserved.

"""Executor for the ``InvokeMcpTool`` declarative action.

Mirrors the .NET ``InvokeMcpToolExecutor``: dispatches an MCP tool call through
the configured :class:`MCPToolHandler`, parses tool outputs, and routes
results to the configured ``output.{result, messages, autoSend}`` paths and
optional conversation history. Supports a human-in-loop approval flow via
``ctx.request_info()`` / :func:`@response_handler` for ``requireApproval=true``.

Security notes:

- Approval requests surface header NAMES only; header values are not echoed,
  matching the posture of :mod:`._executors_http`.
- :class:`MCPToolApprovalRequest` carries the values the resume handler will
  use; header values are re-evaluated and checked against a workflow-local
  keyed binding. Changed or unverifiable headers require fresh approval.
  The key stays in trusted host checkpoint state, never in approval payloads;
  header values are not checkpointed.
- Tool outputs flow back into agent conversations through ``conversationId``
  and through Tool-role messages emitted to ``output.messages``. They share
  the same prompt-injection risk surface as ``HttpRequestAction``: workflow
  authors must trust the MCP server they invoke.
"""

import hmac
import json
import logging
import secrets
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import httpx
from agent_framework import (
    Content,
    Message,
    WorkflowContext,
    handler,
    response_handler,
)
from agent_framework.exceptions import ToolExecutionException

from ._declarative_base import (
    ActionComplete,
    DeclarativeActionExecutor,
    DeclarativeWorkflowState,
)
from ._executors_tools import ToolApprovalResponse
from ._mcp_handler import MCPToolHandler, MCPToolInvocation, MCPToolResult

__all__ = [
    "MCP_ACTION_EXECUTORS",
    "InvokeMcpToolActionExecutor",
    "MCPToolApprovalRequest",
]

logger = logging.getLogger(__name__)
_HEADER_BINDING_KEY = "_declarative_mcp_header_binding_key"


# ---------------------------------------------------------------------------
# Request / state types
# ---------------------------------------------------------------------------


@dataclass
class MCPToolApprovalRequest:
    """Approval request emitted before invoking an MCP tool.

    Attributes:
        request_id: Identifier matching the framework's pending-request key.
        tool_name: Evaluated tool name.
        server_url: Evaluated MCP server URL.
        server_label: Optional human-readable label.
        arguments: Evaluated tool arguments.
        header_names: Outbound header names (values withheld).
        connection_name: Connection identifier the invocation will use.
        metadata: Internal routing data pinned at approval-request time
            (e.g. ``conversation_id``) for use by the resume handler.
        header_binding: Opaque binding of the reviewed headers. The verification
            key is retained separately in trusted workflow state.
    """

    request_id: str
    tool_name: str
    server_url: str
    server_label: str | None
    arguments: dict[str, Any]
    header_names: list[str] = field(default_factory=lambda: [])
    connection_name: str | None = None
    metadata: dict[str, Any] = field(default_factory=lambda: {})
    header_binding: str | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _evaluate_conversation_id(state: DeclarativeWorkflowState, conversation_id_expr: Any) -> str | None:
    """Return the evaluated ``conversationId`` string, or None when empty/unset."""
    if not isinstance(conversation_id_expr, str) or not conversation_id_expr:
        return None
    evaluated = state.eval_if_expression(conversation_id_expr)
    if evaluated is None:
        return None
    text = str(evaluated)
    return text or None


def _get_output_path(action_def: Mapping[str, Any], key: str) -> str | None:
    """Extract a state path from ``output.{key}`` field.

    Supports two YAML shapes:

    - ``output: { result: Local.MyVar }`` — plain string.
    - ``output: { result: { path: Local.MyVar } }`` — object form.
    """
    output: Any = action_def.get("output")
    if not isinstance(output, Mapping):
        return None
    value: Any = output.get(key)  # type: ignore[reportUnknownMemberType]
    if isinstance(value, str):
        return value or None
    if isinstance(value, Mapping):
        path: Any = value.get("path")  # type: ignore[reportUnknownMemberType]
        return path if isinstance(path, str) and path else None
    return None


def _format_outputs_for_send(parsed_results: list[Any]) -> str:
    """Render parsed MCP outputs to a string for ``ctx.yield_output(...)``.

    - Empty list → ``""``.
    - All-string list → newline-joined.
    - Single element (any type — scalar, dict, list) → JSON-dumped element.
      This avoids surprising ``"[42]"`` / ``"[true]"`` / ``"[null]"`` when
      an MCP tool returns a single scalar JSON value.
    - Multi-element non-string list → JSON-dump the whole list.
    """
    if not parsed_results:
        return ""
    if all(isinstance(item, str) for item in parsed_results):
        return "\n".join(parsed_results)
    if len(parsed_results) == 1:
        return json.dumps(parsed_results[0], ensure_ascii=False)
    return json.dumps(parsed_results, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Executor
# ---------------------------------------------------------------------------


class InvokeMcpToolActionExecutor(DeclarativeActionExecutor):
    """Executor for the ``InvokeMcpTool`` declarative action.

    Dispatches through the supplied :class:`MCPToolHandler` and:

    - Evaluates ``serverUrl`` / ``toolName`` / ``serverLabel`` / ``arguments``
      / ``headers`` / ``connection.name`` from the action definition.
    - When ``requireApproval=true``: emits a :class:`MCPToolApprovalRequest`
      via ``ctx.request_info()`` and yields. On resume, the response is
      checked; on rejection, ``output.result`` is set to ``"Error: ..."`` and
      no tool call is made. Changed headers, legacy unbound headers, or a
      missing verification state require another approval.
    - On success: parses each :class:`agent_framework.Content` output (text →
      JSON-first / data / uri → URI string) and assigns the parsed list to
      ``output.result``. Builds a single Tool-role :class:`Message`
      containing all output contents and assigns it to ``output.messages``.
      When ``output.autoSend`` is true (default), emits the rendered string
      via ``ctx.yield_output(...)``. When ``conversationId`` is configured,
      appends an Assistant-role :class:`Message` with the same contents to
      ``System.conversations.{id}.messages``.
    - On error returned by the handler (``is_error=True``): assigns
      ``"Error: <message>"`` to ``output.result`` and completes normally
      (parity with .NET ``AssignErrorAsync``).

    .. note::

       ``output.messages`` receives a SINGLE Tool-role :class:`Message`
       (containing the full tool output as ``contents``), unlike
       :class:`agent_framework_declarative.InvokeFunctionToolExecutor` which
       writes a list of two messages (assistant call + tool result). This
       matches the .NET ``InvokeMcpToolExecutor`` output contract.
    """

    def __init__(
        self,
        action_def: dict[str, Any],
        *,
        id: str | None = None,
        mcp_tool_handler: MCPToolHandler,
    ) -> None:
        """Create an MCP tool action executor.

        Args:
            action_def: Parsed ``InvokeMcpTool`` YAML dict.
            id: Optional executor id (defaults to action id or generated).
            mcp_tool_handler: Handler used to dispatch MCP tool calls.
                Required: the builder enforces presence at workflow-build
                time.
        """
        super().__init__(action_def, id=id)
        self._mcp_tool_handler = mcp_tool_handler

    # ----- Main handler --------------------------------------------------------

    @handler
    async def handle_action(
        self,
        trigger: Any,
        ctx: WorkflowContext[ActionComplete, str],
    ) -> None:
        """Execute the MCP tool action."""
        state = await self._ensure_state_initialized(ctx, trigger)

        server_url = self._get_server_url(state)
        tool_name = self._get_tool_name(state)
        server_label = self._get_server_label(state)
        arguments = self._get_arguments(state)
        headers = self._get_headers(state)
        connection_name = self._get_connection_name(state)
        require_approval = self._get_require_approval(state)
        auto_send = self._get_auto_send(state)
        conversation_id_expr = self._action_def.get("conversationId")
        output_messages_path = _get_output_path(self._action_def, "messages")
        output_result_path = _get_output_path(self._action_def, "result")

        invocation = MCPToolInvocation(
            server_url=server_url,
            tool_name=tool_name,
            server_label=server_label,
            arguments=arguments,
            headers=headers,
            connection_name=connection_name,
        )
        if require_approval:
            await self._request_approval(
                invocation, {"conversation_id": _evaluate_conversation_id(state, conversation_id_expr)}, ctx
            )
            return

        result = await self._invoke_with_narrow_catch(invocation)
        await self._process_result(
            ctx=ctx,
            state=state,
            result=result,
            auto_send=auto_send,
            conversation_id=_evaluate_conversation_id(state, conversation_id_expr),
            output_messages_path=output_messages_path,
            output_result_path=output_result_path,
        )
        await ctx.send_message(ActionComplete())

    # ----- Approval response handler ------------------------------------------

    def _bind_headers(
        self,
        ctx: WorkflowContext[ActionComplete, str],
        request_id: str,
        headers: Mapping[str, str],
        *,
        create_key: bool = False,
    ) -> str | None:
        key = ctx.state.get(_HEADER_BINDING_KEY, None)
        if key is None:
            if not create_key:
                return None
            key = secrets.token_hex(32)
            ctx.state.set(_HEADER_BINDING_KEY, key)
        if not isinstance(key, str) or len(key) != 64 or any(char not in "0123456789abcdef" for char in key):
            raise ValueError("Invalid MCP approval header binding state.")
        # Stable sorting preserves the order of duplicate case-insensitive names.
        canonical_headers = sorted(((name.lower(), value) for name, value in headers.items()), key=lambda item: item[0])
        payload = json.dumps(
            [request_id, canonical_headers],
            ensure_ascii=True,
            separators=(",", ":"),
        ).encode()
        return hmac.digest(key.encode(), payload, "sha256").hex()

    async def _request_approval(
        self,
        invocation: MCPToolInvocation,
        metadata: dict[str, Any],
        ctx: WorkflowContext[ActionComplete, str],
    ) -> None:
        request_id = str(uuid.uuid4())
        request = MCPToolApprovalRequest(
            request_id=request_id,
            tool_name=invocation.tool_name,
            server_url=invocation.server_url,
            server_label=invocation.server_label,
            arguments=invocation.arguments,
            header_names=sorted(invocation.headers),
            connection_name=invocation.connection_name,
            metadata=metadata,
            header_binding=(
                self._bind_headers(ctx, request_id, invocation.headers, create_key=True) if invocation.headers else None
            ),
        )
        logger.info("%s: requesting approval for MCP tool '%s'", self.__class__.__name__, invocation.tool_name)
        await ctx.request_info(request, ToolApprovalResponse, request_id=request_id)

    @response_handler
    async def handle_approval_response(
        self,
        original_request: MCPToolApprovalRequest,
        response: ToolApprovalResponse,
        ctx: WorkflowContext[ActionComplete, str],
    ) -> None:
        """Resume the pinned operation only with the reviewed header context."""
        state = self._get_state(ctx.state)

        tool_name = original_request.tool_name
        metadata: dict[str, Any] = getattr(original_request, "metadata", None) or {}
        raw_conversation_id = metadata.get("conversation_id")
        conversation_id = raw_conversation_id if isinstance(raw_conversation_id, str) and raw_conversation_id else None

        auto_send = self._get_auto_send(state)
        output_messages_path = _get_output_path(self._action_def, "messages")
        output_result_path = _get_output_path(self._action_def, "result")

        if response.approved is not True:
            logger.info(
                "%s: MCP tool '%s' rejected: %s",
                self.__class__.__name__,
                tool_name,
                response.reason,
            )
            self._assign_error(state, output_result_path, "MCP tool invocation was not approved by user.")
            await ctx.send_message(ActionComplete())
            return

        invocation = MCPToolInvocation(
            server_url=original_request.server_url,
            tool_name=tool_name,
            server_label=original_request.server_label,
            arguments=original_request.arguments,
            headers=self._evaluate_headers(state, self._action_def.get("headers")),
            connection_name=getattr(original_request, "connection_name", None),
        )
        if invocation.headers or original_request.header_names:
            binding = getattr(original_request, "header_binding", None)
            expected_binding = self._bind_headers(ctx, original_request.request_id, invocation.headers)
            if (
                not isinstance(binding, str)
                or expected_binding is None
                or not hmac.compare_digest(binding.encode(), expected_binding.encode())
            ):
                logger.warning(
                    "%s: MCP header context changed or could not be verified; requesting fresh approval.",
                    self.__class__.__name__,
                )
                await self._request_approval(invocation, dict(metadata), ctx)
                return
        result = await self._invoke_with_narrow_catch(invocation)
        await self._process_result(
            ctx=ctx,
            state=state,
            result=result,
            auto_send=auto_send,
            conversation_id=conversation_id,
            output_messages_path=output_messages_path,
            output_result_path=output_result_path,
        )
        await ctx.send_message(ActionComplete())

    # ----- Field resolution ----------------------------------------------------

    def _get_server_url(self, state: DeclarativeWorkflowState) -> str:
        raw = self._action_def.get("serverUrl")
        if raw is None:
            raise ValueError("InvokeMcpTool requires a 'serverUrl' field.")
        evaluated = state.eval_if_expression(raw)
        if not isinstance(evaluated, str) or not evaluated:
            raise ValueError("InvokeMcpTool 'serverUrl' evaluated to an empty value.")
        return evaluated

    def _get_tool_name(self, state: DeclarativeWorkflowState) -> str:
        raw = self._action_def.get("toolName")
        if raw is None:
            raise ValueError("InvokeMcpTool requires a 'toolName' field.")
        evaluated = state.eval_if_expression(raw)
        if not isinstance(evaluated, str) or not evaluated:
            raise ValueError("InvokeMcpTool 'toolName' evaluated to an empty value.")
        return evaluated

    def _get_server_label(self, state: DeclarativeWorkflowState) -> str | None:
        raw = self._action_def.get("serverLabel")
        if raw is None:
            return None
        evaluated = state.eval_if_expression(raw)
        if evaluated is None:
            return None
        text = str(evaluated)
        return text or None

    def _get_arguments(self, state: DeclarativeWorkflowState) -> dict[str, Any]:
        """Evaluate ``arguments`` map. Preserves ``None`` values (parity with .NET)."""
        raw = self._action_def.get("arguments")
        if raw is None:
            return {}
        if not isinstance(raw, Mapping) or not raw:
            return {}
        result: dict[str, Any] = {}
        for key, value in raw.items():  # type: ignore[reportUnknownVariableType]
            if not isinstance(key, str) or not key:
                continue
            result[key] = state.eval_if_expression(value)
        return result

    def _get_headers(self, state: DeclarativeWorkflowState) -> dict[str, str]:
        return self._evaluate_headers(state, self._action_def.get("headers"))

    @staticmethod
    def _evaluate_headers(state: DeclarativeWorkflowState, headers_def: Any) -> dict[str, str]:
        """Evaluate the ``headers`` map. Empty string values are skipped."""
        if not isinstance(headers_def, Mapping) or not headers_def:
            return {}
        result: dict[str, str] = {}
        for key, value in headers_def.items():  # type: ignore[reportUnknownVariableType]
            if not isinstance(key, str) or not key:
                continue
            evaluated = state.eval_if_expression(value)
            if evaluated is None:
                continue
            text = str(evaluated)
            if not text:
                continue
            result[key] = text
        return result

    def _get_connection_name(self, state: DeclarativeWorkflowState) -> str | None:
        connection = self._action_def.get("connection")
        if not isinstance(connection, Mapping):
            return None
        name_expr: Any = connection.get("name")  # type: ignore[reportUnknownMemberType]
        if name_expr is None:
            return None
        evaluated = state.eval_if_expression(name_expr)
        if evaluated is None:
            return None
        text = str(evaluated)
        return text or None

    def _get_require_approval(self, state: DeclarativeWorkflowState) -> bool:
        raw = self._action_def.get("requireApproval")
        if raw is None:
            return False
        evaluated = state.eval_if_expression(raw)
        if isinstance(evaluated, bool):
            return evaluated
        if isinstance(evaluated, str):
            return evaluated.strip().lower() in {"true", "1", "yes"}
        return bool(evaluated)

    def _get_auto_send(self, state: DeclarativeWorkflowState) -> bool:
        output: Any = self._action_def.get("output")
        if not isinstance(output, Mapping):
            return True
        raw: Any = output.get("autoSend")  # type: ignore[reportUnknownMemberType]
        if raw is None:
            return True
        evaluated = state.eval_if_expression(raw)
        if isinstance(evaluated, bool):
            return evaluated
        if isinstance(evaluated, str):
            return evaluated.strip().lower() in {"true", "1", "yes"}
        return bool(evaluated)

    # ----- Invocation + error handling ----------------------------------------

    async def _invoke_with_narrow_catch(self, invocation: MCPToolInvocation) -> MCPToolResult:
        """Invoke the handler with a narrow exception catch.

        Only known transport / tool exceptions are normalised to an error
        result. Programmer bugs (TypeError, ValueError from misuse, etc.)
        propagate so they fail loudly.

        ``asyncio.CancelledError`` is a ``BaseException``, not ``Exception``,
        so it is not caught here and propagates unchanged for workflow
        cancellation.
        """
        try:
            return await self._mcp_tool_handler.invoke_tool(invocation)
        except ToolExecutionException as exc:
            message = str(exc) or type(exc).__name__
            return MCPToolResult(
                outputs=[Content.from_text(f"Error: {message}")],
                is_error=True,
                error_message=message,
            )
        except httpx.HTTPError as exc:
            message = f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__
            return MCPToolResult(
                outputs=[Content.from_text(f"Error: {message}")],
                is_error=True,
                error_message=message,
            )
        except Exception as exc:
            try:
                from mcp.shared.exceptions import McpError
            except ImportError:  # pragma: no cover - mcp is a hard dep
                raise
            if isinstance(exc, McpError):
                message = str(exc) or type(exc).__name__
                return MCPToolResult(
                    outputs=[Content.from_text(f"Error: {message}")],
                    is_error=True,
                    error_message=message,
                )
            raise

    # ----- Result handling -----------------------------------------------------

    async def _process_result(
        self,
        *,
        ctx: WorkflowContext[ActionComplete, str],
        state: DeclarativeWorkflowState,
        result: MCPToolResult,
        auto_send: bool,
        conversation_id: str | None,
        output_messages_path: str | None,
        output_result_path: str | None,
    ) -> None:
        """Apply ``result`` to workflow state per the configured output paths."""
        if result.is_error:
            # Error path mirrors .NET ``AssignErrorAsync`` — only the result
            # path is touched; messages / autoSend / conversation are not.
            self._assign_error(
                state,
                output_result_path,
                result.error_message or "MCP tool invocation failed.",
            )
            return

        parsed_results = _parse_outputs(result.outputs)
        if output_result_path is not None and parsed_results:
            state.set(output_result_path, parsed_results)

        # Single Tool-role message (matches .NET line 178 contract). Differs
        # from InvokeFunctionTool's two-message [assistant call, tool result]
        # convention.
        tool_message = Message(role="tool", contents=list(result.outputs))
        if output_messages_path is not None:
            state.set(output_messages_path, tool_message)

        if auto_send and parsed_results:
            await ctx.yield_output(_format_outputs_for_send(parsed_results))

        if conversation_id:
            messages_path = f"System.conversations.{conversation_id}.messages"
            assistant_message = Message(role="assistant", contents=list(result.outputs))
            state.append(messages_path, assistant_message)

    @staticmethod
    def _assign_error(
        state: DeclarativeWorkflowState,
        output_result_path: str | None,
        error_message: str,
    ) -> None:
        """Mirror .NET ``AssignErrorAsync``: store ``"Error: <msg>"`` at the result path."""
        if output_result_path is None:
            return
        state.set(output_result_path, f"Error: {error_message}")


def _parse_outputs(outputs: list[Content]) -> list[Any]:
    """Parse :class:`Content` outputs into Python values for ``output.result``.

    Mirrors .NET ``AssignResultAsync``:

    - ``TextContent`` → JSON-parse text; on failure use the raw text.
    - ``DataContent`` / ``UriContent`` → ``content.uri``.
    - Other content kinds → ``str(content)``.
    """
    parsed: list[Any] = []
    for content in outputs:
        kind = getattr(content, "type", None)
        if kind == "text":
            text_value = getattr(content, "text", None)
            text_str = "" if text_value is None else str(text_value)
            try:
                parsed.append(json.loads(text_str))
            except (json.JSONDecodeError, ValueError):
                parsed.append(text_str)
            continue
        if kind in ("data", "uri"):
            uri_value = getattr(content, "uri", None)
            parsed.append("" if uri_value is None else str(uri_value))
            continue
        parsed.append(str(content))
    return parsed


MCP_ACTION_EXECUTORS: dict[str, type[DeclarativeActionExecutor]] = {
    "InvokeMcpTool": InvokeMcpToolActionExecutor,
}
