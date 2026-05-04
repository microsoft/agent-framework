# Copyright (c) Microsoft. All rights reserved.

"""Tests for ``InvokeMcpToolActionExecutor``.

Use a stub :class:`MCPToolHandler` that returns canned :class:`MCPToolResult`s.
No real MCP server or network is exercised. See
``test_default_mcp_tool_handler.py`` for tests that exercise the real
``DefaultMCPToolHandler`` against a mocked ``MCPStreamableHTTPTool``.
"""

import sys
from typing import Any

import httpx
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

from agent_framework import Content, Message  # noqa: E402
from agent_framework.exceptions import ToolExecutionException  # noqa: E402

from agent_framework_declarative._workflows import (  # noqa: E402
    DECLARATIVE_STATE_KEY,
    DeclarativeWorkflowError,
    MCPToolHandler,
    MCPToolInvocation,
    MCPToolResult,
    WorkflowFactory,
)


class StubMcpHandler:
    """Test stub recording the last call and returning a canned result."""

    def __init__(
        self,
        result: MCPToolResult | None = None,
        *,
        raise_exc: BaseException | None = None,
    ) -> None:
        self.result = result
        self.raise_exc = raise_exc
        self.last_invocation: MCPToolInvocation | None = None
        self.invocations: list[MCPToolInvocation] = []
        self.call_count = 0

    async def invoke_tool(self, invocation: MCPToolInvocation) -> MCPToolResult:
        self.call_count += 1
        self.last_invocation = invocation
        self.invocations.append(invocation)
        if self.raise_exc is not None:
            raise self.raise_exc
        assert self.result is not None
        return self.result


def _ok(outputs: list[Content] | None = None) -> MCPToolResult:
    return MCPToolResult(outputs=outputs or [Content.from_text("hello")])


def _err(message: str = "boom") -> MCPToolResult:
    return MCPToolResult(
        outputs=[Content.from_text(f"Error: {message}")],
        is_error=True,
        error_message=message,
    )


def _action(
    *,
    server_url: str = "https://mcp.example/api",
    tool_name: str = "search",
    server_label: str | None = None,
    arguments: dict[str, Any] | None = None,
    headers: dict[str, Any] | None = None,
    require_approval: Any = None,
    connection: dict[str, Any] | None = None,
    conversation_id: str | None = None,
    output: dict[str, Any] | None = None,
) -> dict[str, Any]:
    action: dict[str, Any] = {
        "kind": "InvokeMcpTool",
        "id": "mcp_action",
        "serverUrl": server_url,
        "toolName": tool_name,
    }
    if server_label is not None:
        action["serverLabel"] = server_label
    if arguments is not None:
        action["arguments"] = arguments
    if headers is not None:
        action["headers"] = headers
    if require_approval is not None:
        action["requireApproval"] = require_approval
    if connection is not None:
        action["connection"] = connection
    if conversation_id is not None:
        action["conversationId"] = conversation_id
    if output is not None:
        action["output"] = output
    return action


def _yaml(action: dict[str, Any]) -> dict[str, Any]:
    return {"name": "mcp_test", "actions": [action]}


# ---------- Builder enforcement --------------------------------------------


class TestBuilderEnforcement:
    def test_missing_handler_raises_at_build_time(self) -> None:
        factory = WorkflowFactory()
        with pytest.raises(DeclarativeWorkflowError) as excinfo:
            factory.create_workflow_from_definition(_yaml(_action()))
        assert "InvokeMcpTool" in str(excinfo.value)
        assert "mcp_tool_handler" in str(excinfo.value)

    def test_missing_server_url_fails_validation(self) -> None:
        handler = StubMcpHandler(_ok())
        factory = WorkflowFactory(mcp_tool_handler=handler)
        action = _action()
        del action["serverUrl"]
        with pytest.raises(Exception) as excinfo:
            factory.create_workflow_from_definition(_yaml(action))
        assert "serverUrl" in str(excinfo.value)

    def test_missing_tool_name_fails_validation(self) -> None:
        handler = StubMcpHandler(_ok())
        factory = WorkflowFactory(mcp_tool_handler=handler)
        action = _action()
        del action["toolName"]
        with pytest.raises(Exception) as excinfo:
            factory.create_workflow_from_definition(_yaml(action))
        assert "toolName" in str(excinfo.value)


# ---------- Field forwarding ----------------------------------------------


class TestFieldForwarding:
    @pytest.mark.asyncio
    async def test_basic_invocation_forwards_required_fields(self) -> None:
        handler = StubMcpHandler(_ok())
        factory = WorkflowFactory(mcp_tool_handler=handler)
        workflow = factory.create_workflow_from_definition(_yaml(_action()))
        await workflow.run({})
        assert handler.call_count == 1
        inv = handler.last_invocation
        assert inv is not None
        assert inv.server_url == "https://mcp.example/api"
        assert inv.tool_name == "search"
        assert inv.server_label is None
        assert inv.headers == {}
        assert inv.arguments == {}
        assert inv.connection_name is None

    @pytest.mark.asyncio
    async def test_arguments_evaluated_and_preserves_none(self) -> None:
        handler = StubMcpHandler(_ok())
        factory = WorkflowFactory(mcp_tool_handler=handler)
        workflow = factory.create_workflow_from_definition(
            _yaml(
                _action(
                    arguments={
                        "query": "weather today",
                        "limit": 5,
                        "fresh": True,
                        "missing": None,
                    }
                )
            )
        )
        await workflow.run({})
        inv = handler.last_invocation
        assert inv is not None
        # ``None`` is preserved (parity with .NET) — caller decides.
        assert inv.arguments == {
            "query": "weather today",
            "limit": 5,
            "fresh": True,
            "missing": None,
        }

    @pytest.mark.asyncio
    async def test_headers_drop_empty_values(self) -> None:
        handler = StubMcpHandler(_ok())
        factory = WorkflowFactory(mcp_tool_handler=handler)
        workflow = factory.create_workflow_from_definition(
            _yaml(
                _action(
                    headers={
                        "Authorization": "Bearer token-123",
                        "X-Trace": "trace-id",
                        "X-Empty": "",
                    }
                )
            )
        )
        await workflow.run({})
        inv = handler.last_invocation
        assert inv is not None
        assert inv.headers == {
            "Authorization": "Bearer token-123",
            "X-Trace": "trace-id",
        }

    @pytest.mark.asyncio
    async def test_server_label_and_connection_name_forwarded(self) -> None:
        handler = StubMcpHandler(_ok())
        factory = WorkflowFactory(mcp_tool_handler=handler)
        workflow = factory.create_workflow_from_definition(
            _yaml(
                _action(
                    server_label="docs-mcp",
                    connection={"name": "azure-conn"},
                )
            )
        )
        await workflow.run({})
        inv = handler.last_invocation
        assert inv is not None
        assert inv.server_label == "docs-mcp"
        assert inv.connection_name == "azure-conn"


# ---------- Output handling ------------------------------------------------


class TestOutput:
    @pytest.mark.asyncio
    async def test_output_result_parses_json_text(self) -> None:
        handler = StubMcpHandler(_ok([Content.from_text('{"k":"v","n":1}')]))
        factory = WorkflowFactory(mcp_tool_handler=handler)
        workflow = factory.create_workflow_from_definition(_yaml(_action(output={"result": "Local.Result"})))
        await workflow.run({})
        decl = workflow._state.get(DECLARATIVE_STATE_KEY)
        assert decl["Local"]["Result"] == [{"k": "v", "n": 1}]

    @pytest.mark.asyncio
    async def test_output_result_falls_back_to_raw_text(self) -> None:
        handler = StubMcpHandler(_ok([Content.from_text("plain text not json")]))
        factory = WorkflowFactory(mcp_tool_handler=handler)
        workflow = factory.create_workflow_from_definition(_yaml(_action(output={"result": "Local.Result"})))
        await workflow.run({})
        decl = workflow._state.get(DECLARATIVE_STATE_KEY)
        assert decl["Local"]["Result"] == ["plain text not json"]

    @pytest.mark.asyncio
    async def test_output_messages_writes_single_tool_role_message(self) -> None:
        handler = StubMcpHandler(_ok([Content.from_text("hi"), Content.from_text("there")]))
        factory = WorkflowFactory(mcp_tool_handler=handler)
        workflow = factory.create_workflow_from_definition(_yaml(_action(output={"messages": "Local.Messages"})))
        await workflow.run({})
        decl = workflow._state.get(DECLARATIVE_STATE_KEY)
        msg = decl["Local"]["Messages"]
        # Single Tool-role message containing both contents (parity with .NET).
        assert isinstance(msg, Message)
        assert str(msg.role).lower() == "tool"
        assert len(msg.contents) == 2

    @pytest.mark.asyncio
    async def test_uri_content_serialised_as_uri_string(self) -> None:
        uri_content = Content.from_uri("https://example.com/file.txt", media_type="text/plain")
        handler = StubMcpHandler(_ok([uri_content]))
        factory = WorkflowFactory(mcp_tool_handler=handler)
        workflow = factory.create_workflow_from_definition(_yaml(_action(output={"result": "Local.Result"})))
        await workflow.run({})
        decl = workflow._state.get(DECLARATIVE_STATE_KEY)
        assert decl["Local"]["Result"] == ["https://example.com/file.txt"]

    @pytest.mark.asyncio
    async def test_output_path_object_form(self) -> None:
        handler = StubMcpHandler(_ok([Content.from_text("ok")]))
        factory = WorkflowFactory(mcp_tool_handler=handler)
        workflow = factory.create_workflow_from_definition(_yaml(_action(output={"result": {"path": "Local.Result"}})))
        await workflow.run({})
        decl = workflow._state.get(DECLARATIVE_STATE_KEY)
        assert decl["Local"]["Result"] == ["ok"]


# ---------- Conversation append --------------------------------------------


class TestConversation:
    @pytest.mark.asyncio
    async def test_conversation_id_appends_assistant_message(self) -> None:
        handler = StubMcpHandler(_ok([Content.from_text("answer")]))
        factory = WorkflowFactory(mcp_tool_handler=handler)
        workflow = factory.create_workflow_from_definition(
            _yaml(
                _action(
                    conversation_id="conv-42",
                    output={"result": "Local.Result"},
                )
            )
        )
        await workflow.run({})
        decl = workflow._state.get(DECLARATIVE_STATE_KEY)
        conv = decl["System"]["conversations"]["conv-42"]
        msgs = conv["messages"] if isinstance(conv, dict) else conv.messages
        assert len(msgs) == 1
        appended = msgs[0]
        assert str(appended.role).lower() == "assistant"
        # Same contents as the tool output.
        assert len(appended.contents) == 1

    @pytest.mark.asyncio
    async def test_empty_conversation_id_does_not_append(self) -> None:
        handler = StubMcpHandler(_ok([Content.from_text("answer")]))
        factory = WorkflowFactory(mcp_tool_handler=handler)
        workflow = factory.create_workflow_from_definition(
            _yaml(
                _action(
                    conversation_id="",
                    output={"result": "Local.Result"},
                )
            )
        )
        await workflow.run({})
        decl = workflow._state.get(DECLARATIVE_STATE_KEY)
        # Empty conversation id must not produce a `""` entry under System.conversations.
        conversations = decl.get("System", {}).get("conversations", {})
        assert "" not in conversations


# ---------- Approval flow --------------------------------------------------


@pytest.fixture
def mock_state():  # type: ignore[no-untyped-def]
    from unittest.mock import MagicMock

    state = MagicMock()
    state._data = {}

    def _get(key: str, default: Any = None) -> Any:
        if key not in state._data:
            if default is not None:
                return default
            raise KeyError(key)
        return state._data[key]

    def _set(key: str, value: Any) -> None:
        state._data[key] = value

    def _delete(key: str) -> None:
        if key in state._data:
            del state._data[key]
        else:
            raise KeyError(key)

    state.get = MagicMock(side_effect=_get)
    state.set = MagicMock(side_effect=_set)
    state.delete = MagicMock(side_effect=_delete)
    return state


@pytest.fixture
def mock_context(mock_state):  # type: ignore[no-untyped-def]
    from unittest.mock import AsyncMock, MagicMock

    ctx = MagicMock()
    ctx.state = mock_state
    ctx.send_message = AsyncMock()
    ctx.yield_output = AsyncMock()
    ctx.request_info = AsyncMock()
    return ctx


def _seed_state(mock_state) -> None:  # type: ignore[no-untyped-def]
    """Pre-seed the declarative state container as the executors expect."""
    from agent_framework_declarative._workflows import DECLARATIVE_STATE_KEY

    mock_state._data[DECLARATIVE_STATE_KEY] = {
        "Local": {},
        "Custom": {},
        "Workflow": {},
        "System": {
            "ConversationId": "00000000-0000-0000-0000-000000000000",
            "LastMessage": {"Id": "", "Text": ""},
            "LastMessageText": "",
            "LastMessageId": "",
        },
        "Agent": {},
        "Conversation": {"messages": [], "history": []},
        "Inputs": {},
    }


class TestApprovalFlow:
    @pytest.mark.asyncio
    async def test_approval_required_emits_request_and_yields(self, mock_state, mock_context) -> None:  # type: ignore[no-untyped-def]
        from agent_framework_declarative._workflows._declarative_base import ActionTrigger
        from agent_framework_declarative._workflows._executors_mcp import (
            _MCP_APPROVAL_STATE_KEY,
            InvokeMcpToolActionExecutor,
            MCPToolApprovalRequest,
        )

        _seed_state(mock_state)
        handler = StubMcpHandler(_ok())
        executor = InvokeMcpToolActionExecutor(
            _action(
                require_approval=True,
                arguments={"q": "x"},
                headers={"Authorization": "Bearer SECRET"},
                output={"result": "Local.Result"},
            ),
            mcp_tool_handler=handler,
        )
        await executor.handle_action(ActionTrigger(), mock_context)

        # Approval request emitted.
        mock_context.request_info.assert_called_once()
        request = mock_context.request_info.call_args[0][0]
        assert isinstance(request, MCPToolApprovalRequest)
        assert request.tool_name == "search"
        assert request.arguments == {"q": "x"}
        assert request.header_names == ["Authorization"]

        # NEVER expose the actual auth token in any field of the approval payload.
        for value in request.__dict__.values():
            assert "SECRET" not in str(value)

        # Workflow should yield (no ActionComplete sent yet).
        mock_context.send_message.assert_not_called()

        # Handler not invoked yet.
        assert handler.call_count == 0

        # Approval state stored.
        approval_key = f"{_MCP_APPROVAL_STATE_KEY}_mcp_action"
        assert approval_key in mock_state._data

    @pytest.mark.asyncio
    async def test_approval_response_approved_invokes_handler(self, mock_state, mock_context) -> None:  # type: ignore[no-untyped-def]
        from agent_framework_declarative._workflows import ActionComplete, ToolApprovalResponse
        from agent_framework_declarative._workflows._executors_mcp import (
            _MCP_APPROVAL_STATE_KEY,
            InvokeMcpToolActionExecutor,
            MCPToolApprovalRequest,
            _MCPToolApprovalState,
        )

        _seed_state(mock_state)
        handler = StubMcpHandler(_ok([Content.from_text('{"ok":true}')]))
        executor = InvokeMcpToolActionExecutor(
            _action(
                require_approval=True,
                output={"result": "Local.Result"},
            ),
            mcp_tool_handler=handler,
        )
        # Pre-populate approval state.
        approval_key = f"{_MCP_APPROVAL_STATE_KEY}_mcp_action"
        mock_state._data[approval_key] = _MCPToolApprovalState(
            server_url="https://mcp.example/api",
            tool_name="search",
            server_label=None,
            arguments={"q": "x"},
            connection_name=None,
            headers_def={"Authorization": "Bearer tk"},
            auto_send=False,
            conversation_id_expr=None,
            output_messages_path=None,
            output_result_path="Local.Result",
        )
        await executor.handle_approval_response(
            MCPToolApprovalRequest(
                request_id="req-1",
                tool_name="search",
                server_url="https://mcp.example/api",
                server_label=None,
                arguments={"q": "x"},
            ),
            ToolApprovalResponse(approved=True),
            mock_context,
        )

        assert handler.call_count == 1
        inv = handler.last_invocation
        assert inv is not None
        # Headers are re-evaluated from headers_def.
        assert inv.headers == {"Authorization": "Bearer tk"}
        # Approval state was cleaned up.
        assert approval_key not in mock_state._data
        # ActionComplete was sent.
        mock_context.send_message.assert_called_once()
        sent = mock_context.send_message.call_args[0][0]
        assert isinstance(sent, ActionComplete)

    @pytest.mark.asyncio
    async def test_approval_response_rejected_assigns_error(self, mock_state, mock_context) -> None:  # type: ignore[no-untyped-def]
        from agent_framework_declarative._workflows import ToolApprovalResponse
        from agent_framework_declarative._workflows._executors_mcp import (
            _MCP_APPROVAL_STATE_KEY,
            InvokeMcpToolActionExecutor,
            MCPToolApprovalRequest,
            _MCPToolApprovalState,
        )

        _seed_state(mock_state)
        handler = StubMcpHandler(_ok())
        executor = InvokeMcpToolActionExecutor(
            _action(
                require_approval=True,
                output={"result": "Local.Result"},
            ),
            mcp_tool_handler=handler,
        )
        approval_key = f"{_MCP_APPROVAL_STATE_KEY}_mcp_action"
        mock_state._data[approval_key] = _MCPToolApprovalState(
            server_url="https://mcp.example/api",
            tool_name="search",
            server_label=None,
            arguments={},
            connection_name=None,
            headers_def=None,
            auto_send=True,
            conversation_id_expr=None,
            output_messages_path=None,
            output_result_path="Local.Result",
        )
        await executor.handle_approval_response(
            MCPToolApprovalRequest(
                request_id="req-2",
                tool_name="search",
                server_url="https://mcp.example/api",
                server_label=None,
                arguments={},
            ),
            ToolApprovalResponse(approved=False, reason="not authorized"),
            mock_context,
        )

        assert handler.call_count == 0
        # Error string assigned at output.result.
        from agent_framework_declarative._workflows import DECLARATIVE_STATE_KEY

        result = mock_state._data[DECLARATIVE_STATE_KEY]["Local"]["Result"]
        assert result == "Error: MCP tool invocation was not approved by user."


# ---------- Error handling -------------------------------------------------


class TestErrorHandling:
    @pytest.mark.asyncio
    async def test_handler_returns_error_result_assigns_error_string(self) -> None:
        handler = StubMcpHandler(_err("server down"))
        factory = WorkflowFactory(mcp_tool_handler=handler)
        workflow = factory.create_workflow_from_definition(_yaml(_action(output={"result": "Local.Result"})))
        await workflow.run({})
        decl = workflow._state.get(DECLARATIVE_STATE_KEY)
        assert decl["Local"]["Result"] == "Error: server down"

    @pytest.mark.asyncio
    async def test_tool_execution_exception_becomes_error_result(self) -> None:
        handler = StubMcpHandler(raise_exc=ToolExecutionException("invalid arguments"))
        factory = WorkflowFactory(mcp_tool_handler=handler)
        workflow = factory.create_workflow_from_definition(_yaml(_action(output={"result": "Local.Result"})))
        await workflow.run({})
        decl = workflow._state.get(DECLARATIVE_STATE_KEY)
        assert decl["Local"]["Result"] == "Error: invalid arguments"

    @pytest.mark.asyncio
    async def test_httpx_error_becomes_error_result(self) -> None:
        handler = StubMcpHandler(raise_exc=httpx.ConnectError("dns fail"))
        factory = WorkflowFactory(mcp_tool_handler=handler)
        workflow = factory.create_workflow_from_definition(_yaml(_action(output={"result": "Local.Result"})))
        await workflow.run({})
        decl = workflow._state.get(DECLARATIVE_STATE_KEY)
        result = decl["Local"]["Result"]
        assert isinstance(result, str)
        assert result.startswith("Error:")
        assert "ConnectError" in result

    @pytest.mark.asyncio
    async def test_unexpected_exception_propagates(self) -> None:
        """Programmer bugs (TypeError etc.) must NOT be swallowed."""
        handler = StubMcpHandler(raise_exc=TypeError("bad type"))
        factory = WorkflowFactory(mcp_tool_handler=handler)
        workflow = factory.create_workflow_from_definition(_yaml(_action()))
        with pytest.raises(Exception) as excinfo:
            await workflow.run({})
        # Either the TypeError reaches us or it gets wrapped by the runner —
        # either way the message must surface.
        assert "bad type" in str(excinfo.value)


# ---------- autoSend -------------------------------------------------------


class TestAutoSend:
    @pytest.mark.asyncio
    async def test_auto_send_default_true_yields_output(self) -> None:
        handler = StubMcpHandler(_ok([Content.from_text("hello")]))
        factory = WorkflowFactory(mcp_tool_handler=handler)
        workflow = factory.create_workflow_from_definition(_yaml(_action()))
        events = await workflow.run({})
        outputs = events.get_outputs()
        assert len(outputs) == 1

    @pytest.mark.asyncio
    async def test_auto_send_false_suppresses_yield(self) -> None:
        handler = StubMcpHandler(_ok([Content.from_text("hello")]))
        factory = WorkflowFactory(mcp_tool_handler=handler)
        workflow = factory.create_workflow_from_definition(_yaml(_action(output={"autoSend": False})))
        events = await workflow.run({})
        outputs = events.get_outputs()
        assert outputs == []


# ---------- Protocol structure --------------------------------------------


class TestProtocol:
    def test_stub_handler_satisfies_protocol(self) -> None:
        handler = StubMcpHandler(_ok())
        assert isinstance(handler, MCPToolHandler)
