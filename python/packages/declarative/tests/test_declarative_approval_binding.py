# Copyright (c) Microsoft. All rights reserved.
# pyright: reportUnknownParameterType=false, reportUnknownArgumentType=false
# pyright: reportMissingParameterType=false, reportUnknownMemberType=false
# pyright: reportPrivateUsage=false, reportUnknownVariableType=false
# pyright: reportGeneralTypeIssues=false

"""Regression tests pinning the approval-flow binding contract.

The resumed invocation MUST come from the framework-delivered
``original_request`` payload (the data the reviewer approved) for both
``InvokeFunctionTool`` and ``InvokeMcpTool``. These tests verify that:

* Invocation parameters come from ``original_request``, not from any prior
  side-channel state.
* Concurrent pending approvals on the same executor do not swap.
* Pre-existing state at old approval keys is ignored entirely.
* Resume works on a freshly constructed executor (checkpoint-restore
  simulation), without any prior ``ctx.state`` write.
* For MCP, ``connection_name`` is sourced from the approval payload and
  ``headers`` are re-evaluated from the action definition on resume.
"""

import sys
from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

try:
    import powerfx  # noqa: F401

    _powerfx_available = True
except (ImportError, RuntimeError):
    _powerfx_available = False

pytestmark = pytest.mark.skipif(
    not _powerfx_available or sys.version_info >= (3, 14),
    reason="PowerFx engine not available (requires dotnet runtime)",
)

from agent_framework import Content  # noqa: E402

from agent_framework_declarative._workflows import (  # noqa: E402
    DECLARATIVE_STATE_KEY,
    ActionComplete,
    InvokeFunctionToolExecutor,
    MCPToolApprovalRequest,
    MCPToolHandler,
    MCPToolInvocation,
    MCPToolResult,
    ToolApprovalRequest,
    ToolApprovalResponse,
)
from agent_framework_declarative._workflows._declarative_base import DeclarativeWorkflowState  # noqa: E402
from agent_framework_declarative._workflows._executors_mcp import (  # noqa: E402
    InvokeMcpToolActionExecutor,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_state() -> MagicMock:
    """In-memory mock of the underlying State."""
    state = MagicMock()
    state._data = {}

    def _get(key: str, default: Any = None) -> Any:
        return state._data.get(key, default)

    def _set(key: str, value: Any) -> None:
        state._data[key] = value

    def _has(key: str) -> bool:
        return key in state._data

    def _delete(key: str) -> None:
        state._data.pop(key, None)

    state.get = MagicMock(side_effect=_get)
    state.set = MagicMock(side_effect=_set)
    state.has = MagicMock(side_effect=_has)
    state.delete = MagicMock(side_effect=_delete)
    return state


@pytest.fixture
def mock_context(mock_state: MagicMock) -> MagicMock:
    ctx = MagicMock()
    ctx.state = mock_state
    ctx.send_message = AsyncMock()
    ctx.yield_output = AsyncMock()
    ctx.request_info = AsyncMock()
    return ctx


def _seed_state(mock_state: MagicMock) -> None:
    mock_state._data[DECLARATIVE_STATE_KEY] = {
        "Inputs": {},
        "Outputs": {},
        "Local": {},
        "Custom": {},
        "System": {
            "ConversationId": "00000000-0000-0000-0000-000000000000",
            "LastMessage": {"Text": "", "Id": ""},
            "LastMessageText": "",
            "LastMessageId": "",
        },
        "Agent": {},
        "Conversation": {"messages": [], "history": []},
    }


class _RecordingMcpHandler(MCPToolHandler):
    def __init__(self, result: MCPToolResult | None = None) -> None:
        self.result = result or MCPToolResult(outputs=[Content.from_text("ok")])
        self.invocations: list[MCPToolInvocation] = []

    @property
    def call_count(self) -> int:
        return len(self.invocations)

    @property
    def last(self) -> MCPToolInvocation | None:
        return self.invocations[-1] if self.invocations else None

    async def invoke_tool(self, invocation: MCPToolInvocation) -> MCPToolResult:
        self.invocations.append(invocation)
        return self.result


# ---------------------------------------------------------------------------
# InvokeFunctionTool: approval-binding regression
# ---------------------------------------------------------------------------


class TestFunctionToolApprovalBinding:
    def _action(self, *, fn_name: str = "my_tool") -> dict[str, Any]:
        return {
            "kind": "InvokeFunctionTool",
            "id": "fn_action",
            "functionName": fn_name,
            "requireApproval": True,
            "output": {"result": "Local.result"},
        }

    @pytest.mark.asyncio
    async def test_request_id_matches_framework_pending_key(self, mock_state, mock_context) -> None:
        """The id on the emitted ToolApprovalRequest must match the framework's pending-request key."""
        from agent_framework_declarative._workflows._declarative_base import ActionTrigger

        _seed_state(mock_state)

        def my_tool(x: int) -> int:
            return x

        executor = InvokeFunctionToolExecutor(self._action(), tools={"my_tool": my_tool})
        await executor.handle_action(ActionTrigger(), mock_context)

        mock_context.request_info.assert_called_once()
        emitted_request = mock_context.request_info.call_args[0][0]
        framework_request_id = mock_context.request_info.call_args.kwargs["request_id"]
        assert isinstance(emitted_request, ToolApprovalRequest)
        assert emitted_request.request_id == framework_request_id

    @pytest.mark.asyncio
    async def test_resume_uses_request_payload_arguments(self, mock_state, mock_context) -> None:
        _seed_state(mock_state)
        call_log: list[int] = []

        def my_tool(x: int) -> int:
            call_log.append(x)
            return x

        executor = InvokeFunctionToolExecutor(self._action(), tools={"my_tool": my_tool})

        request = ToolApprovalRequest(request_id="r-1", function_name="my_tool", arguments={"x": 1})
        await executor.handle_approval_response(request, ToolApprovalResponse(approved=True), mock_context)

        assert call_log == [1]

    @pytest.mark.asyncio
    async def test_concurrent_pending_approvals_do_not_swap(self, mock_state, mock_context) -> None:
        """Two pending approvals, responses delivered out of order — each invocation uses its own payload."""
        _seed_state(mock_state)
        call_log: list[int] = []

        def my_tool(x: int) -> int:
            call_log.append(x)
            return x

        executor = InvokeFunctionToolExecutor(self._action(), tools={"my_tool": my_tool})

        request_a = ToolApprovalRequest(request_id="r-A", function_name="my_tool", arguments={"x": 1})
        request_b = ToolApprovalRequest(request_id="r-B", function_name="my_tool", arguments={"x": 999})

        # Deliver response for B first, then for A. Each invocation must use its own payload.
        await executor.handle_approval_response(request_b, ToolApprovalResponse(approved=True), mock_context)
        await executor.handle_approval_response(request_a, ToolApprovalResponse(approved=True), mock_context)

        assert call_log == [999, 1]

    @pytest.mark.asyncio
    async def test_resume_ignores_stale_state_at_old_approval_key(self, mock_state, mock_context) -> None:
        """Pre-existing state at the OLD approval key is ignored — payload wins."""
        _seed_state(mock_state)
        call_log: list[int] = []

        def my_tool(x: int) -> int:
            call_log.append(x)
            return x

        executor = InvokeFunctionToolExecutor(self._action(), tools={"my_tool": my_tool})

        # Poison the old key shape (no longer read by the executor).
        mock_state._data["_tool_approval_state_fn_action"] = {"function_name": "other", "arguments": {"x": 999}}

        request = ToolApprovalRequest(request_id="r-3", function_name="my_tool", arguments={"x": 7})
        await executor.handle_approval_response(request, ToolApprovalResponse(approved=True), mock_context)

        assert call_log == [7]
        # The poison was never read or deleted by the executor.
        assert "_tool_approval_state_fn_action" in mock_state._data

    @pytest.mark.asyncio
    async def test_fresh_executor_resume_works(self, mock_state, mock_context) -> None:
        """Simulates checkpoint restore: a brand-new executor instance handles the approval response."""
        _seed_state(mock_state)
        call_log: list[int] = []

        def my_tool(x: int) -> int:
            call_log.append(x)
            return x

        # Pretend the executor that emitted the request is gone; a fresh one handles the response.
        fresh = InvokeFunctionToolExecutor(self._action(), tools={"my_tool": my_tool})

        request = ToolApprovalRequest(request_id="r-4", function_name="my_tool", arguments={"x": 42})
        await fresh.handle_approval_response(request, ToolApprovalResponse(approved=True), mock_context)

        assert call_log == [42]
        mock_context.send_message.assert_called_once()
        sent = mock_context.send_message.call_args[0][0]
        assert isinstance(sent, ActionComplete)

    @pytest.mark.asyncio
    async def test_rejection_uses_request_payload_function_name(self, mock_state, mock_context) -> None:
        _seed_state(mock_state)

        def my_tool(x: int) -> int:
            raise AssertionError("should not be called when rejected")

        executor = InvokeFunctionToolExecutor(self._action(), tools={"my_tool": my_tool})

        request = ToolApprovalRequest(request_id="r-5", function_name="my_tool", arguments={"x": 3})
        await executor.handle_approval_response(
            request, ToolApprovalResponse(approved=False, reason="not authorized"), mock_context
        )

        # The rejection message references the function name from the request payload.
        local = mock_state._data[DECLARATIVE_STATE_KEY]["Local"]
        assert local["result"]["rejected"] is True
        assert local["result"]["reason"] == "not authorized"


# ---------------------------------------------------------------------------
# InvokeMcpTool: approval-binding regression
# ---------------------------------------------------------------------------


class TestMcpToolApprovalBinding:
    def _action(self, *, headers: dict[str, Any] | None = None) -> dict[str, Any]:
        action: dict[str, Any] = {
            "kind": "InvokeMcpTool",
            "id": "mcp_action",
            "serverUrl": "https://mcp.example/api",
            "toolName": "search",
            "requireApproval": True,
            "output": {"result": "Local.Result"},
        }
        if headers is not None:
            action["headers"] = headers
        return action

    @pytest.mark.asyncio
    async def test_request_id_matches_framework_pending_key(self, mock_state, mock_context) -> None:
        """The id on the emitted MCPToolApprovalRequest must match the framework's pending-request key."""
        from agent_framework_declarative._workflows._declarative_base import ActionTrigger

        _seed_state(mock_state)
        executor = InvokeMcpToolActionExecutor(self._action(), mcp_tool_handler=_RecordingMcpHandler())
        await executor.handle_action(ActionTrigger(), mock_context)

        mock_context.request_info.assert_called_once()
        emitted_request = mock_context.request_info.call_args[0][0]
        framework_request_id = mock_context.request_info.call_args.kwargs["request_id"]
        assert isinstance(emitted_request, MCPToolApprovalRequest)
        assert emitted_request.request_id == framework_request_id

    @pytest.mark.asyncio
    async def test_resume_uses_request_payload_fields(self, mock_state, mock_context) -> None:
        _seed_state(mock_state)
        handler = _RecordingMcpHandler()
        executor = InvokeMcpToolActionExecutor(self._action(), mcp_tool_handler=handler)

        request = MCPToolApprovalRequest(
            request_id="r-1",
            tool_name="search",
            server_url="https://mcp.example/api",
            server_label="prod",
            arguments={"q": "x"},
            connection_name="conn-A",
        )
        await executor.handle_approval_response(request, ToolApprovalResponse(approved=True), mock_context)

        assert handler.call_count == 1
        inv = handler.last
        assert inv is not None
        assert inv.tool_name == "search"
        assert inv.server_url == "https://mcp.example/api"
        assert inv.server_label == "prod"
        assert inv.arguments == {"q": "x"}
        assert inv.connection_name == "conn-A"

    @pytest.mark.asyncio
    async def test_concurrent_pending_mcp_approvals_do_not_swap(self, mock_state, mock_context) -> None:
        _seed_state(mock_state)
        handler = _RecordingMcpHandler()
        executor = InvokeMcpToolActionExecutor(self._action(), mcp_tool_handler=handler)

        request_a = MCPToolApprovalRequest(
            request_id="r-A",
            tool_name="search",
            server_url="https://mcp.example/api",
            server_label=None,
            arguments={"q": "alpha"},
            connection_name="conn-A",
        )
        request_b = MCPToolApprovalRequest(
            request_id="r-B",
            tool_name="search",
            server_url="https://mcp.example/api",
            server_label=None,
            arguments={"q": "beta"},
            connection_name="conn-B",
        )

        await executor.handle_approval_response(request_b, ToolApprovalResponse(approved=True), mock_context)
        await executor.handle_approval_response(request_a, ToolApprovalResponse(approved=True), mock_context)

        assert handler.call_count == 2
        assert handler.invocations[0].arguments == {"q": "beta"}
        assert handler.invocations[0].connection_name == "conn-B"
        assert handler.invocations[1].arguments == {"q": "alpha"}
        assert handler.invocations[1].connection_name == "conn-A"

    @pytest.mark.asyncio
    async def test_headers_reevaluated_from_action_def_on_resume(self, mock_state, mock_context) -> None:
        """Headers come from the action definition (re-evaluated) so secrets are not in the payload."""
        _seed_state(mock_state)
        handler = _RecordingMcpHandler()
        executor = InvokeMcpToolActionExecutor(
            self._action(headers={"Authorization": "Bearer tk"}),
            mcp_tool_handler=handler,
        )

        request = MCPToolApprovalRequest(
            request_id="r-1",
            tool_name="search",
            server_url="https://mcp.example/api",
            server_label=None,
            arguments={"q": "x"},
            connection_name=None,
        )
        await executor.handle_approval_response(request, ToolApprovalResponse(approved=True), mock_context)

        assert handler.last is not None
        assert handler.last.headers == {"Authorization": "Bearer tk"}

    @pytest.mark.asyncio
    async def test_mcp_resume_ignores_stale_state_at_old_approval_key(self, mock_state, mock_context) -> None:
        _seed_state(mock_state)
        handler = _RecordingMcpHandler()
        executor = InvokeMcpToolActionExecutor(self._action(), mcp_tool_handler=handler)

        mock_state._data["_mcp_tool_approval_state_mcp_action"] = {"poison": True}

        request = MCPToolApprovalRequest(
            request_id="r-1",
            tool_name="search",
            server_url="https://mcp.example/api",
            server_label=None,
            arguments={"q": "real"},
            connection_name=None,
        )
        await executor.handle_approval_response(request, ToolApprovalResponse(approved=True), mock_context)

        assert handler.call_count == 1
        assert handler.last is not None
        assert handler.last.arguments == {"q": "real"}
        # The poison was never read or deleted by the executor.
        assert "_mcp_tool_approval_state_mcp_action" in mock_state._data

    @pytest.mark.asyncio
    async def test_fresh_mcp_executor_resume_works(self, mock_state, mock_context) -> None:
        """Checkpoint-restore simulation: fresh executor handles the response."""
        _seed_state(mock_state)
        handler = _RecordingMcpHandler()
        fresh = InvokeMcpToolActionExecutor(self._action(), mcp_tool_handler=handler)

        request = MCPToolApprovalRequest(
            request_id="r-1",
            tool_name="search",
            server_url="https://mcp.example/api",
            server_label=None,
            arguments={"q": "fresh"},
            connection_name=None,
        )
        await fresh.handle_approval_response(request, ToolApprovalResponse(approved=True), mock_context)

        assert handler.call_count == 1
        assert handler.last is not None
        assert handler.last.arguments == {"q": "fresh"}

    @pytest.mark.asyncio
    async def test_request_payload_carries_connection_name(self, mock_state, mock_context) -> None:
        """When emitting the approval request, connection_name flows into MCPToolApprovalRequest."""
        from agent_framework_declarative._workflows._declarative_base import ActionTrigger

        _seed_state(mock_state)
        action = self._action()
        action["connection"] = {"name": "conn-from-action"}
        executor = InvokeMcpToolActionExecutor(action, mcp_tool_handler=_RecordingMcpHandler())

        await executor.handle_action(ActionTrigger(), mock_context)

        mock_context.request_info.assert_called_once()
        request = mock_context.request_info.call_args[0][0]
        assert isinstance(request, MCPToolApprovalRequest)
        assert request.connection_name == "conn-from-action"

    @pytest.mark.asyncio
    async def test_request_payload_pins_conversation_id(self, mock_state, mock_context) -> None:
        """Evaluated ``conversationId`` is pinned in ``metadata`` at request-emit time."""
        from agent_framework_declarative._workflows._declarative_base import ActionTrigger

        _seed_state(mock_state)
        state = DeclarativeWorkflowState(mock_state)
        state.set("Local.targetConversation", "conv-original")
        action = self._action()
        action["conversationId"] = "=Local.targetConversation"
        executor = InvokeMcpToolActionExecutor(action, mcp_tool_handler=_RecordingMcpHandler())

        await executor.handle_action(ActionTrigger(), mock_context)

        mock_context.request_info.assert_called_once()
        request = mock_context.request_info.call_args[0][0]
        assert isinstance(request, MCPToolApprovalRequest)
        assert request.metadata.get("conversation_id") == "conv-original"

    @pytest.mark.asyncio
    async def test_resume_routes_output_to_pinned_conversation_not_mutated_state(
        self, mock_state, mock_context
    ) -> None:
        """Output appends to the conversation pinned on ``original_request``, not the
        current state evaluation."""
        _seed_state(mock_state)
        state = DeclarativeWorkflowState(mock_state)
        state.set("System.conversations.conv-original.messages", [])
        state.set("System.conversations.conv-mutated.messages", [])
        state.set("Local.targetConversation", "conv-mutated")

        handler = _RecordingMcpHandler(MCPToolResult(outputs=[Content.from_text("approved-output")]))
        action = self._action()
        action["conversationId"] = "=Local.targetConversation"
        executor = InvokeMcpToolActionExecutor(action, mcp_tool_handler=handler)

        original_request = MCPToolApprovalRequest(
            request_id="r-1",
            tool_name="search",
            server_url="https://mcp.example/api",
            server_label=None,
            arguments={"q": "x"},
            connection_name=None,
            metadata={"conversation_id": "conv-original"},
        )
        await executor.handle_approval_response(original_request, ToolApprovalResponse(approved=True), mock_context)

        assert len(state.get("System.conversations.conv-original.messages") or []) == 1
        assert state.get("System.conversations.conv-mutated.messages") == []

    @pytest.mark.asyncio
    async def test_resume_handles_legacy_request_without_new_fields(self, mock_state, mock_context) -> None:
        """Resume tolerates payloads lacking ``connection_name`` / ``metadata`` (legacy pickle shape)."""

        @dataclass
        class _LegacyMCPApprovalRequest:
            request_id: str
            tool_name: str
            server_url: str
            server_label: str | None
            arguments: dict[str, Any]
            header_names: list[str]

        _seed_state(mock_state)
        handler = _RecordingMcpHandler()
        executor = InvokeMcpToolActionExecutor(self._action(), mcp_tool_handler=handler)

        legacy_request = _LegacyMCPApprovalRequest(
            request_id="r-1",
            tool_name="search",
            server_url="https://mcp.example/api",
            server_label=None,
            arguments={"q": "x"},
            header_names=[],
        )
        await executor.handle_approval_response(
            legacy_request,  # type: ignore[arg-type]
            ToolApprovalResponse(approved=True),
            mock_context,
        )

        assert handler.call_count == 1
        assert handler.last is not None
        assert handler.last.connection_name is None
