# Copyright (c) Microsoft. All rights reserved.

"""Tests for ``InvokeMcpToolActionExecutor``.

Use a stub :class:`MCPToolHandler` that returns canned :class:`MCPToolResult`s.
No real MCP server or network is exercised. See
``test_default_mcp_tool_handler.py`` for tests that exercise the real
``DefaultMCPToolHandler`` against a mocked ``MCPStreamableHTTPTool``.
"""

import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx2 as httpx
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

from agent_framework import AgentSession, Content, Message  # noqa: E402
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
        assert inv.workflow_session_id

    @pytest.mark.asyncio
    async def test_separate_workflows_receive_separate_session_ids(self) -> None:
        handler = StubMcpHandler(_ok())
        factory = WorkflowFactory(mcp_tool_handler=handler)
        first = factory.create_workflow_from_definition(_yaml(_action()))
        second = factory.create_workflow_from_definition(_yaml(_action()))

        await first.run({})
        await second.run({})

        assert len(handler.invocations) == 2
        assert handler.invocations[0].workflow_session_id
        assert handler.invocations[1].workflow_session_id
        assert handler.invocations[0].workflow_session_id != handler.invocations[1].workflow_session_id

    @pytest.mark.parametrize("message_list", [False, True])
    @pytest.mark.parametrize("streaming", [False, True])
    async def test_fresh_runs_on_same_workflow_receive_separate_session_ids(
        self, message_list: bool, streaming: bool
    ) -> None:
        handler = StubMcpHandler(_ok())
        factory = WorkflowFactory(mcp_tool_handler=handler)
        workflow = factory.create_workflow_from_definition(_yaml(_action()))

        for text in ("first run", "second run"):
            inputs: list[Message] | dict[str, Any] = (
                [Message(role="user", contents=[Content.from_text(text)])] if message_list else {}
            )
            if streaming:
                await workflow.run(inputs, stream=True).get_final_response()
            else:
                await workflow.run(inputs)

        assert len(handler.invocations) == 2
        assert handler.invocations[0].workflow_session_id
        assert handler.invocations[0].workflow_session_id != handler.invocations[1].workflow_session_id

    @pytest.mark.parametrize("streaming", [False, True])
    async def test_as_agent_continuation_reuses_workflow_session_id(self, streaming: bool) -> None:
        handler = StubMcpHandler(_ok())
        factory = WorkflowFactory(mcp_tool_handler=handler)
        workflow = factory.create_workflow_from_definition(_yaml(_action()))
        agent = workflow.as_agent(name="mcp-agent")

        for text in ("first turn", "second turn"):
            if streaming:
                await agent.run(text, stream=True).get_final_response()
            else:
                await agent.run(text)

        assert len(handler.invocations) == 2
        assert handler.invocations[0].workflow_session_id
        assert handler.invocations[0].workflow_session_id == handler.invocations[1].workflow_session_id

    @pytest.mark.parametrize("pause_kind", ["Question", "RequestExternalInput"])
    @pytest.mark.parametrize("streaming", [False, True])
    async def test_response_only_agent_checkpoint_resume_preserves_workflow_session_id(
        self, pause_kind: str, streaming: bool
    ) -> None:
        from agent_framework import InMemoryCheckpointStorage

        from agent_framework_declarative._workflows import ExternalInputResponse

        storage = InMemoryCheckpointStorage()
        handler = StubMcpHandler(_ok())
        factory = WorkflowFactory(mcp_tool_handler=handler)
        definition = {
            "name": "mcp_continuation",
            "actions": [
                {**_action(tool_name="before"), "id": "before"},
                {
                    "kind": pause_kind,
                    "id": "pause",
                    "question" if pause_kind == "Question" else "prompt": "Continue?",
                    "variable": "Local.answer",
                },
                {**_action(tool_name="after"), "id": "after"},
            ],
        }
        workflow = factory.create_workflow_from_definition(definition)
        agent = workflow.as_agent()
        original_session = AgentSession()
        if streaming:
            response = await agent.run(
                "first turn", session=original_session, stream=True, checkpoint_storage=storage
            ).get_final_response()
        else:
            response = await agent.run("first turn", session=original_session, checkpoint_storage=storage)

        [request] = (await workflow._runner_context.get_pending_request_info_events()).values()
        [function_call] = [
            content for message in response.messages for content in message.contents if content.type == "function_call"
        ]
        assert function_call.call_id == request.request_id
        checkpoint_id = workflow.get_last_checkpoint_id()
        assert checkpoint_id is not None
        workflow = factory.create_workflow_from_definition(definition)
        agent = workflow.as_agent()
        resumed_session = AgentSession()
        assert resumed_session.session_id != original_session.session_id
        reply = Message(
            role="user",
            contents=[
                Content(
                    "function_result",
                    call_id=request.request_id,
                    result=ExternalInputResponse(user_input="continue"),
                )
            ],
        )
        if streaming:
            await agent.run(
                reply,
                session=resumed_session,
                stream=True,
                checkpoint_id=checkpoint_id,
                checkpoint_storage=storage,
            ).get_final_response()
        else:
            await agent.run(reply, session=resumed_session, checkpoint_id=checkpoint_id, checkpoint_storage=storage)

        [original, resumed] = handler.invocations
        assert original.tool_name == "before"
        assert resumed.tool_name == "after"
        assert original.workflow_session_id
        assert resumed.workflow_session_id == original.workflow_session_id
        assert not await workflow._runner_context.get_pending_request_info_events()

    @pytest.mark.parametrize("pause_kind", ["Question", "RequestExternalInput"])
    @pytest.mark.parametrize("streaming", [False, True])
    @pytest.mark.parametrize("restore", [False, True])
    async def test_pending_external_input_restores_originating_workflow_session_id(
        self, pause_kind: str, streaming: bool, restore: bool
    ) -> None:
        from agent_framework import InMemoryCheckpointStorage, WorkflowEvent

        from agent_framework_declarative._workflows import ExternalInputResponse

        storage = InMemoryCheckpointStorage()
        handler = StubMcpHandler(_ok())
        factory = WorkflowFactory(mcp_tool_handler=handler)
        definition = {
            "name": "mcp_pending_input",
            "actions": [
                {**_action(tool_name="before"), "id": "before"},
                {
                    "kind": pause_kind,
                    "id": "pause",
                    "question" if pause_kind == "Question" else "prompt": "Continue?",
                    "variable": "Local.answer",
                },
                {**_action(tool_name="after"), "id": "after"},
            ],
        }
        workflow = factory.create_workflow_from_definition(definition)
        requests: list[WorkflowEvent[Any]] = []
        for _ in range(2):
            if streaming:
                await workflow.run({}, stream=True, checkpoint_storage=storage).get_final_response()
            else:
                await workflow.run({}, checkpoint_storage=storage)
            [request] = [
                event
                for event in (await workflow._runner_context.get_pending_request_info_events()).values()
                if event.request_id not in {previous.request_id for previous in requests}
            ]
            requests.append(request)
        original_scopes = [invocation.workflow_session_id for invocation in handler.invocations]
        assert all(original_scopes)
        assert original_scopes[0] != original_scopes[1]

        if restore:
            checkpoint_id = workflow.get_last_checkpoint_id()
            assert checkpoint_id is not None
            workflow = factory.create_workflow_from_definition(definition)
            await workflow.run(checkpoint_id=checkpoint_id, checkpoint_storage=storage)

        for request, scope in zip(requests, original_scopes, strict=True):
            responses = {request.request_id: ExternalInputResponse(user_input="continue")}
            if streaming:
                await workflow.run(responses=responses, stream=True).get_final_response()
            else:
                await workflow.run(responses=responses)
            assert handler.invocations[-1].tool_name == "after"
            assert handler.invocations[-1].workflow_session_id == scope
        assert handler.call_count == 4
        assert not await workflow._runner_context.get_pending_request_info_events()

    @pytest.mark.parametrize("mixed_approval", [False, True])
    @pytest.mark.parametrize("streaming", [False, True])
    @pytest.mark.parametrize("restore", [False, True])
    async def test_external_input_batches_reject_different_workflow_sessions(
        self, mixed_approval: bool, streaming: bool, restore: bool
    ) -> None:
        from agent_framework import InMemoryCheckpointStorage

        from agent_framework_declarative._workflows import ExternalInputResponse, ToolApprovalResponse

        storage = InMemoryCheckpointStorage()
        handler = StubMcpHandler(_ok())
        factory = WorkflowFactory(mcp_tool_handler=handler)
        definition = {
            "name": "mcp_input_batches",
            "actions": [
                {**_action(tool_name="before"), "id": "before"},
                {"kind": "Question", "id": "pause", "question": "Continue?", "variable": "Local.answer"},
                {**_action(tool_name="after", require_approval=mixed_approval), "id": "after"},
            ],
        }
        workflow = factory.create_workflow_from_definition(definition)
        await workflow.run({}, checkpoint_storage=storage)
        [first] = (await workflow._runner_context.get_pending_request_info_events()).values()
        await workflow.run({}, checkpoint_storage=storage)
        [second] = [
            event
            for event in (await workflow._runner_context.get_pending_request_info_events()).values()
            if event.request_id != first.request_id
        ]
        if mixed_approval:
            await workflow.run(
                responses={second.request_id: ExternalInputResponse(user_input="continue")},
                checkpoint_storage=storage,
            )
            [second] = [
                event
                for event in (await workflow._runner_context.get_pending_request_info_events()).values()
                if event.request_id != first.request_id
            ]
        if restore:
            checkpoint_id = workflow.get_last_checkpoint_id()
            assert checkpoint_id is not None
            workflow = factory.create_workflow_from_definition(definition)
            await workflow.run(checkpoint_id=checkpoint_id, checkpoint_storage=storage)

        responses = {
            first.request_id: ExternalInputResponse(user_input="continue"),
            second.request_id: (
                ToolApprovalResponse(approved=True) if mixed_approval else ExternalInputResponse(user_input="continue")
            ),
        }
        with pytest.raises(DeclarativeWorkflowError, match="different workflow sessions"):
            if streaming:
                await workflow.run(responses=responses, stream=True).get_final_response()
            else:
                await workflow.run(responses=responses)
        assert handler.call_count == 2
        assert set(await workflow._runner_context.get_pending_request_info_events()) == set(responses)

    @pytest.mark.parametrize("pause_kind", ["Question", "RequestExternalInput"])
    async def test_external_input_without_originating_scope_is_not_consumed(self, pause_kind: str) -> None:
        from agent_framework_declarative._workflows import ExternalInputResponse

        handler = StubMcpHandler(_ok())
        factory = WorkflowFactory(mcp_tool_handler=handler)
        workflow = factory.create_workflow_from_definition({
            "name": "mcp_legacy_input",
            "actions": [
                {**_action(tool_name="before"), "id": "before"},
                {
                    "kind": pause_kind,
                    "id": "pause",
                    "question" if pause_kind == "Question" else "prompt": "Continue?",
                    "variable": "Local.answer",
                },
                {**_action(tool_name="after"), "id": "after"},
            ],
        })
        await workflow.run({})
        [request] = (await workflow._runner_context.get_pending_request_info_events()).values()
        request.data.workflow_session_id = None

        with pytest.raises(DeclarativeWorkflowError, match="originating workflow session"):
            await workflow.run(responses={request.request_id: ExternalInputResponse(user_input="continue")})

        assert handler.call_count == 1
        assert set(await workflow._runner_context.get_pending_request_info_events()) == {request.request_id}

    @pytest.mark.parametrize("run_kind", ["direct", "sessionless_agent", "explicit_agent"])
    @pytest.mark.parametrize("streaming", [False, True])
    async def test_entry_checkpoint_replay_preserves_workflow_session_id(self, run_kind: str, streaming: bool) -> None:
        from agent_framework import InMemoryCheckpointStorage

        storage = InMemoryCheckpointStorage()
        handler = StubMcpHandler(_ok())
        factory = WorkflowFactory(mcp_tool_handler=handler)
        definition = _yaml(_action())
        workflow = factory.create_workflow_from_definition(definition)
        session = AgentSession() if run_kind == "explicit_agent" else None

        if run_kind == "direct":
            if streaming:
                await workflow.run({}, stream=True, checkpoint_storage=storage).get_final_response()
            else:
                await workflow.run({}, checkpoint_storage=storage)
        else:
            agent = workflow.as_agent()
            if streaming:
                await agent.run(
                    "first turn", session=session, stream=True, checkpoint_storage=storage
                ).get_final_response()
            else:
                await agent.run("first turn", session=session, checkpoint_storage=storage)

        [original] = handler.invocations
        checkpoints = await storage.list_checkpoints(workflow_name=workflow.name)
        [entry_checkpoint] = [checkpoint for checkpoint in checkpoints if checkpoint.iteration_count == 0]
        workflow = factory.create_workflow_from_definition(definition)
        await workflow.run(checkpoint_id=entry_checkpoint.checkpoint_id, checkpoint_storage=storage)

        assert len(handler.invocations) == 2
        assert original.workflow_session_id
        assert handler.invocations[1].workflow_session_id == original.workflow_session_id

    @pytest.mark.parametrize("intervening_run", ["explicit_session", "direct_dict", "direct_message_list"])
    @pytest.mark.parametrize("streaming", [False, True])
    @pytest.mark.parametrize("restore", [False, True])
    async def test_sessionless_agent_scope_survives_intervening_runs(
        self, intervening_run: str, streaming: bool, restore: bool
    ) -> None:
        from agent_framework import InMemoryCheckpointStorage

        storage = InMemoryCheckpointStorage()
        handler = StubMcpHandler(_ok())
        factory = WorkflowFactory(mcp_tool_handler=handler)
        definition = _yaml(_action())
        workflow = factory.create_workflow_from_definition(definition)
        agent = workflow.as_agent(name="mcp-agent")

        async def agent_turn(text: str, session: AgentSession | None = None) -> None:
            if streaming:
                await agent.run(text, session=session, stream=True, checkpoint_storage=storage).get_final_response()
            else:
                await agent.run(text, session=session, checkpoint_storage=storage)

        await agent_turn("first sessionless turn")
        if intervening_run == "explicit_session":
            await agent_turn("explicit session turn", AgentSession())
        else:
            inputs: list[Message] | dict[str, Any] = (
                [Message(role="user", contents=[Content.from_text("direct run")])]
                if intervening_run == "direct_message_list"
                else {}
            )
            if streaming:
                await workflow.run(inputs, stream=True, checkpoint_storage=storage).get_final_response()
            else:
                await workflow.run(inputs, checkpoint_storage=storage)

        if restore:
            checkpoint_id = workflow.get_last_checkpoint_id()
            assert checkpoint_id is not None
            workflow = factory.create_workflow_from_definition(definition)
            await workflow.run(checkpoint_id=checkpoint_id, checkpoint_storage=storage)
            agent = workflow.as_agent(name="mcp-agent")

        await agent_turn("second sessionless turn")

        session_ids = [invocation.workflow_session_id for invocation in handler.invocations]
        assert len(session_ids) == 3
        assert all(session_ids)
        assert session_ids[0] != session_ids[1]
        assert session_ids[0] == session_ids[2]

    @pytest.mark.parametrize("message_list", [False, True])
    @pytest.mark.parametrize("streaming", [False, True])
    @pytest.mark.parametrize("restore", [False, True])
    async def test_sessionless_agent_does_not_inherit_direct_scope(
        self, message_list: bool, streaming: bool, restore: bool
    ) -> None:
        from agent_framework import InMemoryCheckpointStorage

        storage = InMemoryCheckpointStorage()
        handler = StubMcpHandler(_ok())
        factory = WorkflowFactory(mcp_tool_handler=handler)
        definition = _yaml(_action())
        workflow = factory.create_workflow_from_definition(definition)
        inputs: list[Message] | dict[str, Any] = (
            [Message(role="user", contents=[Content.from_text("direct run")])] if message_list else {}
        )
        if streaming:
            await workflow.run(inputs, stream=True, checkpoint_storage=storage).get_final_response()
        else:
            await workflow.run(inputs, checkpoint_storage=storage)

        if restore:
            checkpoint_id = workflow.get_last_checkpoint_id()
            assert checkpoint_id is not None
            workflow = factory.create_workflow_from_definition(definition)
            await workflow.run(checkpoint_id=checkpoint_id, checkpoint_storage=storage)

        agent = workflow.as_agent(name="mcp-agent")
        for text in ("first sessionless turn", "second sessionless turn"):
            if streaming:
                await agent.run(text, stream=True).get_final_response()
            else:
                await agent.run(text)

        session_ids = [invocation.workflow_session_id for invocation in handler.invocations]
        assert len(session_ids) == 3
        assert all(session_ids)
        assert session_ids[0] != session_ids[1]
        assert session_ids[1] == session_ids[2]

    @pytest.mark.parametrize("streaming", [False, True])
    @pytest.mark.parametrize("approved", [False, True])
    @pytest.mark.parametrize("restore", [False, True])
    async def test_sessionless_scope_survives_approval_origin_restoration(
        self, streaming: bool, approved: bool, restore: bool
    ) -> None:
        from agent_framework import InMemoryCheckpointStorage

        from agent_framework_declarative._workflows import ToolApprovalResponse

        storage = InMemoryCheckpointStorage()
        handler = StubMcpHandler(_ok())
        factory = WorkflowFactory(mcp_tool_handler=handler)
        downstream = {**_action(tool_name="downstream"), "id": "downstream"}
        definition = _yaml(_action(require_approval=True))
        definition["actions"].append(downstream)
        workflow = factory.create_workflow_from_definition(definition)
        agent = workflow.as_agent(name="mcp-agent")

        async def agent_turn(text: str, session: AgentSession | None = None) -> None:
            if streaming:
                await agent.run(text, session=session, stream=True, checkpoint_storage=storage).get_final_response()
            else:
                await agent.run(text, session=session, checkpoint_storage=storage)

        await agent_turn("first sessionless turn")
        [sessionless_approval] = (await workflow._runner_context.get_pending_request_info_events()).values()
        responses = {sessionless_approval.request_id: ToolApprovalResponse(approved=approved)}
        if streaming:
            await workflow.run(responses=responses, stream=True).get_final_response()
        else:
            await workflow.run(responses=responses)
        assert [invocation.workflow_session_id for invocation in handler.invocations] == [
            sessionless_approval.data.workflow_session_id
        ] * (2 if approved else 1)

        await agent_turn("explicit session turn", AgentSession())
        [explicit_approval] = (await workflow._runner_context.get_pending_request_info_events()).values()
        assert sessionless_approval.data.workflow_session_id
        assert explicit_approval.data.workflow_session_id
        assert sessionless_approval.data.workflow_session_id != explicit_approval.data.workflow_session_id

        if restore:
            checkpoint_id = workflow.get_last_checkpoint_id()
            assert checkpoint_id is not None
            workflow = factory.create_workflow_from_definition(definition)
            await workflow.run(checkpoint_id=checkpoint_id, checkpoint_storage=storage)
            agent = workflow.as_agent(name="mcp-agent")

        responses = {explicit_approval.request_id: ToolApprovalResponse(approved=approved)}
        if streaming:
            await workflow.run(responses=responses, stream=True).get_final_response()
        else:
            await workflow.run(responses=responses)
        assert [invocation.workflow_session_id for invocation in handler.invocations] == [
            scope
            for scope in (sessionless_approval.data.workflow_session_id, explicit_approval.data.workflow_session_id)
            for _ in range(2 if approved else 1)
        ]

        await agent_turn("second sessionless turn")
        [new_approval] = (await workflow._runner_context.get_pending_request_info_events()).values()
        assert new_approval.data.workflow_session_id == sessionless_approval.data.workflow_session_id
        responses = {new_approval.request_id: ToolApprovalResponse(approved=approved)}
        if streaming:
            await workflow.run(responses=responses, stream=True).get_final_response()
        else:
            await workflow.run(responses=responses)
        assert [invocation.workflow_session_id for invocation in handler.invocations] == [
            scope
            for scope in (
                sessionless_approval.data.workflow_session_id,
                explicit_approval.data.workflow_session_id,
                sessionless_approval.data.workflow_session_id,
            )
            for _ in range(2 if approved else 1)
        ]
        assert not await workflow._runner_context.get_pending_request_info_events()

    @pytest.mark.asyncio
    async def test_as_agent_sessions_isolate_and_reuse_workflow_session_ids(self) -> None:
        handler = StubMcpHandler(_ok())
        factory = WorkflowFactory(mcp_tool_handler=handler)
        workflow = factory.create_workflow_from_definition(_yaml(_action()))
        agent = workflow.as_agent(name="mcp-agent")
        session_a = AgentSession()
        session_b = AgentSession()

        await agent.run("session A first turn", session=session_a)
        await agent.run("session B first turn", session=session_b)
        await agent.run("session A second turn", session=session_a)

        assert len(handler.invocations) == 3
        session_a_id = handler.invocations[0].workflow_session_id
        session_b_id = handler.invocations[1].workflow_session_id
        assert session_a_id
        assert session_b_id
        assert session_a_id != session_b_id
        assert handler.invocations[2].workflow_session_id == session_a_id

    @pytest.mark.parametrize("message_list", [False, True])
    @pytest.mark.parametrize("streaming", [False, True])
    @pytest.mark.parametrize("explicit_session", [False, True])
    async def test_direct_fresh_runs_after_agent_turn_receive_separate_session_ids(
        self, message_list: bool, streaming: bool, explicit_session: bool
    ) -> None:
        handler = StubMcpHandler(_ok())
        factory = WorkflowFactory(mcp_tool_handler=handler)
        workflow = factory.create_workflow_from_definition(_yaml(_action()))
        agent = workflow.as_agent(name="mcp-agent")

        await agent.run("agent turn", session=AgentSession() if explicit_session else None)
        for text in ("first direct run", "second direct run"):
            inputs: list[Message] | dict[str, Any] = (
                [Message(role="user", contents=[Content.from_text(text)])] if message_list else {}
            )
            if streaming:
                await workflow.run(inputs, stream=True).get_final_response()
            else:
                await workflow.run(inputs)

        session_ids = [invocation.workflow_session_id for invocation in handler.invocations]
        assert len(session_ids) == 3
        assert all(session_ids)
        assert len(set(session_ids)) == 3

    @pytest.mark.asyncio
    async def test_continuation_reuses_workflow_session_id(self) -> None:
        from agent_framework_declarative._workflows import ToolApprovalResponse
        from agent_framework_declarative._workflows._mcp_handler import get_or_create_workflow_session_id

        handler = StubMcpHandler(_ok())
        factory = WorkflowFactory(mcp_tool_handler=handler)
        workflow = factory.create_workflow_from_definition(_yaml(_action(require_approval=True)))

        paused = await workflow.run({})
        [approval] = paused.get_request_info_events()
        workflow_session_id = get_or_create_workflow_session_id(workflow._runner.state)  # pyright: ignore[reportPrivateUsage]
        await workflow.run(responses={approval.request_id: ToolApprovalResponse(approved=True)})

        assert handler.last_invocation is not None
        assert handler.last_invocation.workflow_session_id == workflow_session_id

    @pytest.mark.parametrize("restore", [False, True])
    @pytest.mark.parametrize("agent_sessions", [False, True])
    @pytest.mark.parametrize("streaming", [False, True])
    @pytest.mark.parametrize("approved", [False, True])
    @pytest.mark.parametrize("second_approved", [False, True])
    async def test_pending_approval_uses_originating_workflow_session_id(
        self, restore: bool, agent_sessions: bool, streaming: bool, approved: bool, second_approved: bool
    ) -> None:
        from agent_framework import InMemoryCheckpointStorage

        from agent_framework_declarative._workflows import ToolApprovalResponse

        storage = InMemoryCheckpointStorage()
        handler = StubMcpHandler(_ok())
        factory = WorkflowFactory(mcp_tool_handler=handler)
        downstream = _action(tool_name="downstream")
        downstream["id"] = "downstream"
        definition = {"name": "mcp_test", "actions": [_action(require_approval=True), downstream]}
        workflow = factory.create_workflow_from_definition(definition)
        agent = workflow.as_agent(name="mcp-agent")

        if agent_sessions:
            await agent.run("first turn", session=AgentSession(), checkpoint_storage=storage)
        else:
            await workflow.run({}, checkpoint_storage=storage)
        [first_approval] = (await workflow._runner_context.get_pending_request_info_events()).values()
        first_session_id = first_approval.data.workflow_session_id

        await workflow.run({}, checkpoint_storage=storage)
        [second_approval] = [
            event
            for event in (await workflow._runner_context.get_pending_request_info_events()).values()
            if event.request_id != first_approval.request_id
        ]

        assert first_session_id
        assert second_approval.data.workflow_session_id
        assert first_session_id != second_approval.data.workflow_session_id

        checkpoint_id = None
        if restore:
            checkpoint_id = workflow.get_last_checkpoint_id()
            assert checkpoint_id is not None
            workflow = factory.create_workflow_from_definition(definition)
            await workflow.run(checkpoint_id=checkpoint_id, checkpoint_storage=storage)

        decisions = {first_approval.request_id: approved, second_approval.request_id: second_approved}
        batch = {request_id: ToolApprovalResponse(approved=decision) for request_id, decision in decisions.items()}
        with pytest.raises(DeclarativeWorkflowError, match="different workflow sessions"):
            if streaming:
                await workflow.run(
                    responses=batch,
                    stream=True,
                    checkpoint_id=checkpoint_id,
                    checkpoint_storage=storage,
                ).get_final_response()
            else:
                await workflow.run(responses=batch, checkpoint_id=checkpoint_id, checkpoint_storage=storage)
        assert handler.call_count == 0
        assert set(await workflow._runner_context.get_pending_request_info_events()) == set(batch)

        for approval in (first_approval, second_approval):
            responses = {approval.request_id: ToolApprovalResponse(approved=decisions[approval.request_id])}
            if streaming:
                await workflow.run(responses=responses, stream=True).get_final_response()
            else:
                await workflow.run(responses=responses)

        expected_tools = [
            tool
            for decision in (approved, second_approved)
            for tool in (["search", "downstream"] if decision else ["downstream"])
        ]
        assert [invocation.tool_name for invocation in handler.invocations] == expected_tools
        expected_sessions = [
            approval.data.workflow_session_id
            for approval in (first_approval, second_approval)
            for _ in range(2 if decisions[approval.request_id] else 1)
        ]
        assert [invocation.workflow_session_id for invocation in handler.invocations] == expected_sessions

    @pytest.mark.parametrize("streaming", [False, True])
    @pytest.mark.parametrize("approved", [False, True])
    async def test_same_scope_approval_batch_is_supported(self, streaming: bool, approved: bool) -> None:
        from agent_framework import WorkflowBuilder

        from agent_framework_declarative._workflows import InvokeMcpToolActionExecutor, ToolApprovalResponse
        from agent_framework_declarative._workflows._declarative_builder import _validate_response_batch
        from agent_framework_declarative._workflows._executors_control_flow import JoinExecutor

        handler = StubMcpHandler(_ok())
        entry = JoinExecutor({"kind": "Entry"}, id="entry")
        actions = [
            InvokeMcpToolActionExecutor({**_action(require_approval=True), "id": name}, mcp_tool_handler=handler)
            for name in ("first", "second")
        ]
        workflow = WorkflowBuilder(start_executor=entry).add_fan_out_edges(entry, actions).build()
        workflow._response_batch_validator = _validate_response_batch
        paused = await workflow.run({})
        approvals = paused.get_request_info_events()
        assert len(approvals) == 2
        scopes = {approval.data.workflow_session_id for approval in approvals}
        assert len(scopes) == 1
        assert all(scopes)

        responses = {approval.request_id: ToolApprovalResponse(approved=approved) for approval in approvals}
        if streaming:
            await workflow.run(responses=responses, stream=True).get_final_response()
        else:
            await workflow.run(responses=responses)

        assert handler.call_count == (2 if approved else 0)
        assert all(invocation.workflow_session_id in scopes for invocation in handler.invocations)
        assert not await workflow._runner_context.get_pending_request_info_events()

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


def _scope_pause_action(kind: str) -> dict[str, Any]:
    actions: dict[str, dict[str, Any]] = {
        "Question": {"kind": "Question", "question": "Continue?", "variable": "Local.answer"},
        "RequestExternalInput": {
            "kind": "RequestExternalInput",
            "prompt": "Continue?",
            "variable": "Local.answer",
        },
        "InvokeFunctionTool": {"kind": "InvokeFunctionTool", "functionName": "echo", "requireApproval": True},
        "InvokeAzureAgent": {
            "kind": "InvokeAzureAgent",
            "agent": "TestAgent",
            "input": {"externalLoop": {"when": '=Local.userInput <> "stop"'}},
        },
        "InvokeMcpTool": _action(require_approval=True),
    }
    return actions[kind]


def _scope_pause_response(kind: str, user_input: str = "stop") -> Any:
    from agent_framework_declarative._workflows import (
        AgentExternalInputResponse,
        ExternalInputResponse,
        ToolApprovalResponse,
    )

    if kind == "InvokeAzureAgent":
        return AgentExternalInputResponse(user_input=user_input)
    if kind in ("InvokeFunctionTool", "InvokeMcpTool"):
        return ToolApprovalResponse(approved=True)
    return ExternalInputResponse(user_input=user_input)


def _scope_checkpoint_storage(path: Path) -> Any:
    from agent_framework import FileCheckpointStorage

    return FileCheckpointStorage(
        path,
        allowed_checkpoint_types=[
            "agent_framework_declarative._workflows._declarative_base:ActionComplete",
            "agent_framework_declarative._workflows._declarative_base:ActionTrigger",
            "agent_framework_declarative._workflows._executors_tools:ToolApprovalRequest",
            "agent_framework_declarative._workflows._executors_tools:ToolApprovalResponse",
            "agent_framework_declarative._workflows._executors_mcp:MCPToolApprovalRequest",
            "agent_framework_declarative._workflows._executors_agents:AgentExternalInputRequest",
            "agent_framework_declarative._workflows._executors_agents:AgentExternalInputResponse",
            "agent_framework_declarative._workflows._executors_agents:ExternalLoopState",
            "agent_framework_declarative._workflows._executors_external_input:ExternalInputRequest",
            "agent_framework_declarative._workflows._executors_external_input:ExternalInputResponse",
        ],
    )


class TestRequestScopeContinuations:
    @pytest.mark.parametrize("pause_kind", ["InvokeFunctionTool", "InvokeAzureAgent"])
    @pytest.mark.parametrize("streaming", [False, True])
    @pytest.mark.parametrize("restore", [False, True])
    async def test_remaining_request_types_restore_originating_scope(
        self, tmp_path: Path, pause_kind: str, streaming: bool, restore: bool
    ) -> None:
        storage = _scope_checkpoint_storage(tmp_path)
        handler = StubMcpHandler(_ok())
        function = MagicMock(return_value="done")
        agent = MagicMock(run=AsyncMock(return_value="Need input"))
        factory = WorkflowFactory(mcp_tool_handler=handler, agents={"TestAgent": agent}).register_tool("echo", function)
        definition = {
            "name": "request_continuations",
            "actions": [
                {**_action(tool_name="before"), "id": "before"},
                {"kind": "SetValue", "path": "Local.userInput", "value": ""},
                {**_scope_pause_action(pause_kind), "id": "pause"},
                {**_action(tool_name="after"), "id": "after"},
            ],
        }
        workflow = factory.create_workflow_from_definition(definition)
        requests: list[Any] = []
        for _ in range(2):
            await workflow.run({}, checkpoint_storage=storage)
            [request] = [
                event
                for event in (await workflow._runner_context.get_pending_request_info_events()).values()
                if event.request_id not in {previous.request_id for previous in requests}
            ]
            requests.append(request)
        scopes = [invocation.workflow_session_id for invocation in handler.invocations]
        assert scopes[0] and scopes[1] and scopes[0] != scopes[1]
        if restore:
            checkpoint_id = workflow.get_last_checkpoint_id()
            assert checkpoint_id is not None
            workflow = factory.create_workflow_from_definition(definition)
            await workflow.run(checkpoint_id=checkpoint_id, checkpoint_storage=storage)
            assert set(await workflow._runner_context.get_pending_request_info_events()) == {
                request.request_id for request in requests
            }

        for request, scope in zip(requests, scopes, strict=True):
            responses = {request.request_id: _scope_pause_response(pause_kind)}
            if streaming:
                await workflow.run(responses=responses, stream=True).get_final_response()
            else:
                await workflow.run(responses=responses)
            assert handler.invocations[-1].tool_name == "after"
            assert handler.invocations[-1].workflow_session_id == scope
        assert handler.call_count == 4
        assert function.call_count == (2 if pause_kind == "InvokeFunctionTool" else 0)
        assert not await workflow._runner_context.get_pending_request_info_events()

    @pytest.mark.parametrize("streaming", [False, True])
    async def test_repeated_agent_input_retains_its_own_loop_state(self, tmp_path: Path, streaming: bool) -> None:
        from agent_framework_declarative._workflows._mcp_handler import get_or_create_workflow_session_id

        storage = _scope_checkpoint_storage(tmp_path)
        handler = StubMcpHandler(_ok())
        agent = MagicMock(run=AsyncMock(return_value="Need input"))
        factory = WorkflowFactory(mcp_tool_handler=handler, agents={"TestAgent": agent})
        definition = {
            "name": "repeated_agent_input",
            "actions": [
                {**_action(tool_name="before"), "id": "before"},
                {"kind": "SetValue", "path": "Local.userInput", "value": ""},
                {**_scope_pause_action("InvokeAzureAgent"), "id": "pause"},
                {**_action(tool_name="after"), "id": "after"},
            ],
        }
        workflow = factory.create_workflow_from_definition(definition)
        await workflow.run({})
        [first] = (await workflow._runner_context.get_pending_request_info_events()).values()
        await workflow.run({})
        [second] = [
            event
            for event in (await workflow._runner_context.get_pending_request_info_events()).values()
            if event.request_id != first.request_id
        ]
        first_scope, second_scope = (invocation.workflow_session_id for invocation in handler.invocations)
        await workflow.run(
            responses={first.request_id: _scope_pause_response("InvokeAzureAgent", "continue")},
            checkpoint_storage=storage,
        )
        assert get_or_create_workflow_session_id(workflow._runner.state) == first_scope
        [repeated] = [
            event
            for event in (await workflow._runner_context.get_pending_request_info_events()).values()
            if event.request_id != second.request_id
        ]
        checkpoint_id = workflow.get_last_checkpoint_id()
        assert checkpoint_id is not None
        workflow = factory.create_workflow_from_definition(definition)
        await workflow.run(checkpoint_id=checkpoint_id, checkpoint_storage=storage)

        for request, scope in ((second, second_scope), (repeated, first_scope)):
            responses = {request.request_id: _scope_pause_response("InvokeAzureAgent")}
            if streaming:
                await workflow.run(responses=responses, stream=True).get_final_response()
            else:
                await workflow.run(responses=responses)
            assert handler.invocations[-1].tool_name == "after"
            assert handler.invocations[-1].workflow_session_id == scope
        assert handler.call_count == 4
        assert agent.run.await_count == 3
        assert not await workflow._runner_context.get_pending_request_info_events()

    @pytest.mark.parametrize("pause_kind", ["InvokeFunctionTool", "InvokeAzureAgent"])
    @pytest.mark.parametrize("streaming", [False, True])
    async def test_mixed_request_families_reject_different_scopes(self, pause_kind: str, streaming: bool) -> None:
        handler = StubMcpHandler(_ok())
        function = MagicMock(return_value="done")
        agent = MagicMock(run=AsyncMock(return_value="Need input"))
        factory = WorkflowFactory(mcp_tool_handler=handler, agents={"TestAgent": agent}).register_tool("echo", function)
        workflow = factory.create_workflow_from_definition({
            "name": "mixed_request_scopes",
            "actions": [
                {"kind": "Question", "question": "Continue?", "variable": "Local.answer"},
                {"kind": "SetValue", "path": "Local.userInput", "value": ""},
                {**_scope_pause_action(pause_kind), "id": "pause"},
                _action(),
            ],
        })
        await workflow.run({})
        [first] = (await workflow._runner_context.get_pending_request_info_events()).values()
        await workflow.run({})
        [second] = [
            event
            for event in (await workflow._runner_context.get_pending_request_info_events()).values()
            if event.request_id != first.request_id
        ]
        await workflow.run(responses={second.request_id: _scope_pause_response("Question")})
        [second] = [
            event
            for event in (await workflow._runner_context.get_pending_request_info_events()).values()
            if event.request_id != first.request_id
        ]
        responses = {
            first.request_id: _scope_pause_response("Question"),
            second.request_id: _scope_pause_response(pause_kind),
        }
        with pytest.raises(DeclarativeWorkflowError, match="different workflow sessions"):
            if streaming:
                await workflow.run(responses=responses, stream=True).get_final_response()
            else:
                await workflow.run(responses=responses)
        assert handler.call_count == 0
        function.assert_not_called()
        assert agent.run.await_count == (1 if pause_kind == "InvokeAzureAgent" else 0)
        assert set(await workflow._runner_context.get_pending_request_info_events()) == set(responses)

    async def test_legacy_mcp_origin_is_rejected_before_consumption(self) -> None:
        handler = StubMcpHandler(_ok())
        factory = WorkflowFactory(mcp_tool_handler=handler)
        workflow = factory.create_workflow_from_definition(_yaml(_action(require_approval=True)))
        await workflow.run({})
        [legacy] = (await workflow._runner_context.get_pending_request_info_events()).values()
        legacy.data.workflow_session_id = None
        await workflow.run({})

        with pytest.raises(DeclarativeWorkflowError, match="migrate_legacy_request_scopes"):
            await workflow.run(responses={legacy.request_id: _scope_pause_response("InvokeMcpTool")})

        assert handler.call_count == 0
        assert legacy.request_id in await workflow._runner_context.get_pending_request_info_events()

    @pytest.mark.parametrize(
        "pause_kind", ["Question", "RequestExternalInput", "InvokeFunctionTool", "InvokeAzureAgent", "InvokeMcpTool"]
    )
    async def test_opt_in_legacy_migration_survives_file_checkpoints(self, tmp_path: Path, pause_kind: str) -> None:
        storage = _scope_checkpoint_storage(tmp_path)
        handler = StubMcpHandler(_ok())
        agent = MagicMock(run=AsyncMock(return_value="Need input"))
        function = MagicMock(return_value="done")
        factory = WorkflowFactory(mcp_tool_handler=handler, agents={"TestAgent": agent}).register_tool("echo", function)
        definition = {
            "name": "legacy_request_migration",
            "actions": [
                {**_action(tool_name="before"), "id": "before"},
                {"kind": "SetValue", "path": "Local.userInput", "value": ""},
                {**_scope_pause_action(pause_kind), "id": "pause"},
                {**_action(tool_name="after"), "id": "after"},
                {**_scope_pause_action("Question"), "id": "followup"},
                {**_action(tool_name="done"), "id": "done"},
            ],
        }
        workflow = factory.create_workflow_from_definition(definition)
        await workflow.run({}, checkpoint_storage=storage)
        await workflow.run({}, checkpoint_storage=storage)
        original_scopes = {invocation.workflow_session_id for invocation in handler.invocations}
        checkpoint_id = workflow.get_last_checkpoint_id()
        assert checkpoint_id is not None
        checkpoint = await storage.load(checkpoint_id)
        assert len(checkpoint.pending_request_info_events) == 2
        for event in checkpoint.pending_request_info_events.values():
            event.data.workflow_session_id = None
            if pause_kind == "InvokeAzureAgent":
                from agent_framework_declarative._workflows._executors_agents import EXTERNAL_LOOP_STATE_KEY

                checkpoint.state[EXTERNAL_LOOP_STATE_KEY] = event.data.loop_state
                del event.data.loop_state
        await storage.save(checkpoint)
        first_id, second_id = checkpoint.pending_request_info_events

        workflow = factory.create_workflow_from_definition(definition)
        await workflow.run(checkpoint_id=checkpoint_id, checkpoint_storage=storage)
        with pytest.raises(DeclarativeWorkflowError, match="migrate_legacy_request_scopes"):
            await workflow.run(responses={first_id: _scope_pause_response(pause_kind)})
        assert handler.call_count == 2
        assert set(await workflow._runner_context.get_pending_request_info_events()) == {first_id, second_id}

        migration_factory = WorkflowFactory(
            mcp_tool_handler=handler, agents={"TestAgent": agent}, migrate_legacy_request_scopes=True
        ).register_tool("echo", function)
        workflow = migration_factory.create_workflow_from_definition(definition)
        await workflow.run(checkpoint_id=checkpoint_id, checkpoint_storage=storage)
        with pytest.raises(DeclarativeWorkflowError, match="different workflow sessions"):
            await workflow.run(
                responses={
                    first_id: _scope_pause_response(pause_kind),
                    second_id: _scope_pause_response(pause_kind),
                }
            )
        pending = await workflow._runner_context.get_pending_request_info_events()
        assert all(event.data.workflow_session_id is None for event in pending.values())
        assert handler.call_count == 2
        function.assert_not_called()

        migrated_scopes: list[str] = []
        for _ in range(2):
            workflow = migration_factory.create_workflow_from_definition(definition)
            await workflow.run(checkpoint_id=checkpoint_id, checkpoint_storage=storage)
            before = handler.call_count
            await workflow.run(responses={first_id: _scope_pause_response(pause_kind)}, checkpoint_storage=storage)
            scope = handler.invocations[-1].workflow_session_id
            assert scope and scope not in original_scopes
            assert all(invocation.workflow_session_id == scope for invocation in handler.invocations[before:])
            migrated_scopes.append(scope)
        assert migrated_scopes[0] == migrated_scopes[1]

        migrated_checkpoint_id = workflow.get_last_checkpoint_id()
        assert migrated_checkpoint_id is not None
        workflow = factory.create_workflow_from_definition(definition)
        await workflow.run(checkpoint_id=migrated_checkpoint_id, checkpoint_storage=storage)
        pending = await workflow._runner_context.get_pending_request_info_events()
        [followup] = [event for event in pending.values() if event.request_id != second_id]
        assert followup.data.workflow_session_id == migrated_scopes[0]
        await workflow.run(responses={followup.request_id: _scope_pause_response("Question")})
        assert handler.invocations[-1].tool_name == "done"
        assert handler.invocations[-1].workflow_session_id == migrated_scopes[0]

        migrated_checkpoint = await storage.load(migrated_checkpoint_id)
        workflow = migration_factory.create_workflow_from_definition(definition)
        await workflow.run(checkpoint_id=migrated_checkpoint.checkpoint_id, checkpoint_storage=storage)
        await workflow.run(responses={second_id: _scope_pause_response(pause_kind)})
        assert handler.invocations[-1].tool_name == "after"
        assert handler.invocations[-1].workflow_session_id not in original_scopes | set(migrated_scopes)

    @pytest.mark.parametrize("invalid_scope", ["", 42])
    @pytest.mark.parametrize("migrate", [False, True])
    async def test_migration_does_not_replace_invalid_scopes(self, invalid_scope: Any, migrate: bool) -> None:
        handler = StubMcpHandler(_ok())
        factory = WorkflowFactory(mcp_tool_handler=handler, migrate_legacy_request_scopes=migrate)
        workflow = factory.create_workflow_from_definition(_yaml(_action(require_approval=True)))
        await workflow.run({})
        [request] = (await workflow._runner_context.get_pending_request_info_events()).values()
        request.data.workflow_session_id = invalid_scope

        with pytest.raises(DeclarativeWorkflowError, match="Invalid originating workflow session"):
            await workflow.run(responses={request.request_id: _scope_pause_response("InvokeMcpTool")})

        assert handler.call_count == 0
        assert set(await workflow._runner_context.get_pending_request_info_events()) == {request.request_id}

    @pytest.mark.parametrize(
        "pause_kind", ["Question", "RequestExternalInput", "InvokeFunctionTool", "InvokeAzureAgent", "InvokeMcpTool"]
    )
    @pytest.mark.parametrize(
        ("restore_kind", "streaming"),
        [("memory", False), ("memory", True), ("file", False), ("file", True), ("embedded", False)],
    )
    async def test_legacy_queued_response_migration_precedes_replay(
        self, tmp_path: Path, pause_kind: str, restore_kind: str, streaming: bool
    ) -> None:
        from agent_framework import InMemoryCheckpointStorage
        from agent_framework._workflows._runner_context import MessageType

        storage = _scope_checkpoint_storage(tmp_path) if restore_kind == "file" else InMemoryCheckpointStorage()
        handler = StubMcpHandler(_ok())
        agent = MagicMock(run=AsyncMock(return_value="Need input"))
        function = MagicMock(return_value="done")
        factory = WorkflowFactory(
            checkpoint_storage=storage, mcp_tool_handler=handler, agents={"TestAgent": agent}
        ).register_tool("echo", function)
        definition = {
            "name": "queued_legacy_response",
            "actions": [
                {**_action(tool_name="before"), "id": "before"},
                {"kind": "SetValue", "path": "Local.userInput", "value": ""},
                {**_scope_pause_action(pause_kind), "id": "pause"},
                {**_action(tool_name="after"), "id": "after"},
                {**_scope_pause_action("Question"), "id": "followup"},
            ],
        }
        workflow = factory.create_workflow_from_definition(definition)
        await workflow.run({})
        [request] = (await workflow._runner_context.get_pending_request_info_events()).values()
        await workflow.run(responses={request.request_id: _scope_pause_response(pause_kind)})
        checkpoints = await storage.list_checkpoints(workflow_name=workflow.name)
        [checkpoint] = [
            item
            for item in checkpoints
            if any(message.type == MessageType.RESPONSE for batch in item.messages.values() for message in batch)
        ]
        [queued_response] = [message for batch in checkpoint.messages.values() for message in batch]
        original = queued_response.original_request_info_event
        assert original is not None
        assert original.request_id == request.request_id
        assert not checkpoint.pending_request_info_events
        original_scope = original.data.workflow_session_id
        original.data.workflow_session_id = None
        await storage.save(checkpoint)
        before = handler.call_count
        function.reset_mock()

        factory = WorkflowFactory(
            checkpoint_storage=storage,
            mcp_tool_handler=handler,
            agents={"TestAgent": agent},
            migrate_legacy_request_scopes=True,
        ).register_tool("echo", function)
        workflow = factory.create_workflow_from_definition(definition)
        if restore_kind == "embedded":
            await workflow._runner.restore_checkpoint(await storage.load(checkpoint.checkpoint_id))
            _ = [event async for event in workflow._runner.run_until_convergence()]
        elif streaming:
            await workflow.run(checkpoint_id=checkpoint.checkpoint_id, stream=True).get_final_response()
        else:
            await workflow.run(checkpoint_id=checkpoint.checkpoint_id)

        replayed = handler.invocations[before:]
        assert replayed
        assert replayed[-1].tool_name == "after"
        scope = replayed[-1].workflow_session_id
        assert scope == f"legacy-request:{request.request_id}"
        assert scope != original_scope
        assert all(invocation.workflow_session_id == scope for invocation in replayed)
        assert function.call_count == (1 if pause_kind == "InvokeFunctionTool" else 0)
        [followup] = (await workflow._runner_context.get_pending_request_info_events()).values()
        assert followup.data.workflow_session_id == scope
        saved_id = workflow.get_last_checkpoint_id()
        assert saved_id is not None
        saved = await storage.load(saved_id)
        assert saved.pending_request_info_events[followup.request_id].data.workflow_session_id == scope

    @pytest.mark.parametrize("restore_kind", ["file", "embedded"])
    @pytest.mark.parametrize("legacy", [False, True])
    async def test_queued_response_batch_is_validated_before_restoring_state(
        self, tmp_path: Path, restore_kind: str, legacy: bool
    ) -> None:
        from agent_framework import InMemoryCheckpointStorage
        from agent_framework.exceptions import WorkflowCheckpointException

        storage = _scope_checkpoint_storage(tmp_path) if restore_kind == "file" else InMemoryCheckpointStorage()
        handler = StubMcpHandler(_ok())
        factory = WorkflowFactory(
            checkpoint_storage=storage, mcp_tool_handler=handler, migrate_legacy_request_scopes=True
        )
        workflow = factory.create_workflow_from_definition(_yaml(_action(require_approval=True)))
        await workflow.run({})
        await workflow.run({})
        requests = await workflow._runner_context.get_pending_request_info_events()
        assert len(requests) == 2
        for request in requests.values():
            if legacy:
                request.data.workflow_session_id = None
            await workflow._runner_context.send_request_info_response(
                request.request_id, _scope_pause_response("InvokeMcpTool")
            )
        await workflow._runner.create_checkpoint_if_enabled()
        checkpoint_id = workflow.get_last_checkpoint_id()
        assert checkpoint_id is not None
        checkpoint = await storage.load(checkpoint_id)
        assert not checkpoint.pending_request_info_events

        workflow = factory.create_workflow_from_definition(_yaml(_action(require_approval=True)))
        workflow._runner.state.set("preexisting", "keep")
        workflow._runner.state.commit()
        with pytest.raises(WorkflowCheckpointException) as exc:
            if restore_kind == "embedded":
                await workflow._runner.restore_checkpoint(checkpoint)
            else:
                await workflow.run(checkpoint_id=checkpoint_id)

        assert isinstance(exc.value.__cause__, DeclarativeWorkflowError)
        assert "different workflow sessions" in str(exc.value.__cause__)
        assert workflow._runner.state.get("preexisting") == "keep"
        assert handler.call_count == 0
        if legacy:
            for batch in checkpoint.messages.values():
                for message in batch:
                    original = message.original_request_info_event
                    assert original is not None
                    assert original.data.workflow_session_id is None

    @pytest.mark.parametrize("restore_kind", ["file", "embedded"])
    async def test_queued_and_new_responses_share_batch_validation(self, tmp_path: Path, restore_kind: str) -> None:
        from agent_framework import InMemoryCheckpointStorage

        storage = _scope_checkpoint_storage(tmp_path) if restore_kind == "file" else InMemoryCheckpointStorage()
        handler = StubMcpHandler(_ok())
        factory = WorkflowFactory(checkpoint_storage=storage, mcp_tool_handler=handler)
        definition = _yaml(_action(require_approval=True))
        workflow = factory.create_workflow_from_definition(definition)
        await workflow.run({})
        await workflow.run({})
        first_id, second_id = (await workflow._runner_context.get_pending_request_info_events()).keys()
        await workflow._runner_context.send_request_info_response(first_id, _scope_pause_response("InvokeMcpTool"))
        await workflow._runner.create_checkpoint_if_enabled()
        checkpoint_id = workflow.get_last_checkpoint_id()
        assert checkpoint_id is not None

        workflow = factory.create_workflow_from_definition(definition)
        with pytest.raises(DeclarativeWorkflowError, match="different workflow sessions"):
            if restore_kind == "embedded":
                await workflow._runner.restore_checkpoint(await storage.load(checkpoint_id))
                await workflow.run(responses={second_id: _scope_pause_response("InvokeMcpTool")})
            else:
                await workflow.run(
                    checkpoint_id=checkpoint_id, responses={second_id: _scope_pause_response("InvokeMcpTool")}
                )

        assert handler.call_count == 0
        assert set(await workflow._runner_context.get_pending_request_info_events()) == {second_id}

    @pytest.mark.parametrize("restore_kind", ["file", "embedded"])
    async def test_legacy_queued_response_requires_opt_in_before_restore(
        self, tmp_path: Path, restore_kind: str
    ) -> None:
        from agent_framework import InMemoryCheckpointStorage
        from agent_framework.exceptions import WorkflowCheckpointException

        storage = _scope_checkpoint_storage(tmp_path) if restore_kind == "file" else InMemoryCheckpointStorage()
        handler = StubMcpHandler(_ok())
        factory = WorkflowFactory(checkpoint_storage=storage, mcp_tool_handler=handler)
        definition = _yaml(_action(require_approval=True))
        workflow = factory.create_workflow_from_definition(definition)
        await workflow.run({})
        [request] = (await workflow._runner_context.get_pending_request_info_events()).values()
        request.data.workflow_session_id = None
        await workflow._runner_context.send_request_info_response(
            request.request_id, _scope_pause_response("InvokeMcpTool")
        )
        await workflow._runner.create_checkpoint_if_enabled()
        checkpoint_id = workflow.get_last_checkpoint_id()
        assert checkpoint_id is not None
        checkpoint = await storage.load(checkpoint_id)

        workflow = factory.create_workflow_from_definition(definition)
        workflow._runner.state.set("preexisting", "keep")
        workflow._runner.state.commit()
        with pytest.raises(WorkflowCheckpointException) as exc:
            if restore_kind == "embedded":
                await workflow._runner.restore_checkpoint(checkpoint)
            else:
                await workflow.run(checkpoint_id=checkpoint_id)

        assert isinstance(exc.value.__cause__, DeclarativeWorkflowError)
        assert "migrate_legacy_request_scopes" in str(exc.value.__cause__)
        assert workflow._runner.state.get("preexisting") == "keep"
        assert handler.call_count == 0

    @pytest.mark.parametrize("restore_kind", ["file", "embedded"])
    @pytest.mark.parametrize("depth", [1, 2])
    @pytest.mark.parametrize("mode", ["missing", "invalid", "migrate", "valid"])
    async def test_parent_queued_child_response_preflight_preserves_state(
        self, tmp_path: Path, restore_kind: str, depth: int, mode: str
    ) -> None:
        from copy import deepcopy

        from agent_framework import WorkflowBuilder, WorkflowExecutor
        from agent_framework._workflows._checkpoint_encoding import encode_checkpoint_value
        from agent_framework._workflows._const import EXECUTOR_STATE_KEY
        from agent_framework.exceptions import WorkflowCheckpointException

        storage = _scope_checkpoint_storage(tmp_path)
        mcp_handler = StubMcpHandler(_ok())
        child = WorkflowFactory(
            mcp_tool_handler=mcp_handler, migrate_legacy_request_scopes=mode == "migrate"
        ).create_workflow_from_definition(_yaml(_action(require_approval=True)))
        workflows = [child]
        parent = child
        for level in range(depth):
            wrapper = WorkflowExecutor(parent, id=f"nested_{level}", propagate_request=True)
            parent = WorkflowBuilder(start_executor=wrapper, checkpoint_storage=storage).build()
            workflows.append(parent)
        await parent.run({})
        [request] = (await parent._runner_context.get_pending_request_info_events()).values()
        await parent._runner_context.send_request_info_response(
            request.request_id, _scope_pause_response("InvokeMcpTool")
        )
        checkpoint = deepcopy(await parent._runner.build_checkpoint())
        # The child's pending request, not the parent's copy, owns the response policy.
        for batch in checkpoint.messages.values():
            for message in batch:
                message.original_request_info_event = deepcopy(message.original_request_info_event)
        child_checkpoint = checkpoint
        for level in reversed(range(depth)):
            child_checkpoint = child_checkpoint.state[EXECUTOR_STATE_KEY][f"nested_{level}"]["sub_workflow_checkpoint"]
        original_scope = child_checkpoint.pending_request_info_events[request.request_id].data.workflow_session_id
        if mode != "valid":
            child_checkpoint.pending_request_info_events[request.request_id].data.workflow_session_id = (
                42 if mode == "invalid" else None
            )
        checkpoint_before = encode_checkpoint_value(checkpoint.to_dict())
        await storage.save(checkpoint)

        for workflow in workflows:
            workflow._runner.state.set("restore_marker", "live")
            workflow._runner.state.commit()
            workflow._runner.state.set("uncommitted", "keep")

        async def snapshots() -> list[Any]:
            result: list[Any] = []
            for workflow in workflows:
                snapshot = await workflow._runner_context.build_checkpoint(
                    workflow.name, workflow.graph_signature_hash, workflow._runner.state, None, 0
                )
                result.append(
                    encode_checkpoint_value({
                        "state": snapshot.state,
                        "messages": snapshot.messages,
                        "requests": snapshot.pending_request_info_events,
                    })
                )
            return result

        before = await snapshots()

        async def restore() -> None:
            if restore_kind == "embedded":
                await parent._runner.restore_checkpoint(checkpoint)
            else:
                await parent._runner.restore_from_checkpoint(checkpoint.checkpoint_id)

        if mode in {"missing", "invalid"}:
            with pytest.raises(WorkflowCheckpointException):
                await restore()
            assert await snapshots() == before
            for workflow in workflows:
                assert workflow._runner.state.get("restore_marker") == "live"
                assert workflow._runner.state.get("uncommitted") == "keep"
        else:
            await restore()
            _ = [event async for event in parent._runner.run_until_convergence()]
            assert mcp_handler.call_count == 1
            assert mcp_handler.invocations[0].workflow_session_id == (
                f"legacy-request:{request.request_id}" if mode == "migrate" else original_scope
            )
        assert encode_checkpoint_value(checkpoint.to_dict()) == checkpoint_before
        assert mcp_handler.call_count == (1 if mode in {"migrate", "valid"} else 0)

    @pytest.mark.parametrize("depth", [1, 2])
    @pytest.mark.parametrize("mode", ["missing", "invalid", "queued"])
    async def test_parent_child_response_rejection_preserves_pending_request(self, depth: int, mode: str) -> None:
        from copy import deepcopy

        from agent_framework import WorkflowBuilder, WorkflowExecutor

        mcp_handler = StubMcpHandler(_ok())
        child = WorkflowFactory(mcp_tool_handler=mcp_handler).create_workflow_from_definition(
            _yaml(_action(require_approval=True))
        )
        parent = child
        for level in range(depth):
            parent = WorkflowBuilder(
                start_executor=WorkflowExecutor(parent, id=f"nested_{level}", propagate_request=True)
            ).build()
        await parent.run({})
        if mode == "queued":
            await parent.run({})
        pending = await parent._runner_context.get_pending_request_info_events()
        child_pending = await child._runner_context.get_pending_request_info_events()
        request_ids = list(pending)
        request_id = request_ids[-1]
        original_scope = child_pending[request_id].data.workflow_session_id
        if mode == "queued":
            await child._runner_context.send_request_info_response(
                request_ids[0], _scope_pause_response("InvokeMcpTool")
            )
        else:
            pending[request_id].data = deepcopy(pending[request_id].data)
            child_pending[request_id].data.workflow_session_id = None if mode == "missing" else 42

        with pytest.raises(DeclarativeWorkflowError):
            await parent.run(responses={request_id: _scope_pause_response("InvokeMcpTool")})

        assert set(await parent._runner_context.get_pending_request_info_events()) == set(request_ids)
        assert request_id in await child._runner_context.get_pending_request_info_events()
        assert mcp_handler.call_count == 0
        if mode != "queued":
            child_pending[request_id].data.workflow_session_id = original_scope
            await parent.run(responses={request_id: _scope_pause_response("InvokeMcpTool")})
            assert not await parent._runner_context.get_pending_request_info_events()
            assert mcp_handler.call_count == 1

    @pytest.mark.parametrize("restore_kind", ["file", "embedded"])
    @pytest.mark.parametrize("depth", [1, 2])
    @pytest.mark.parametrize("mode", ["missing", "mixed", "valid", "pending"])
    async def test_nested_checkpoint_preflight_preserves_live_state(
        self, tmp_path: Path, restore_kind: str, depth: int, mode: str
    ) -> None:
        from copy import deepcopy

        from agent_framework import (
            Executor,
            Workflow,
            WorkflowBuilder,
            WorkflowCheckpoint,
            WorkflowContext,
            WorkflowExecutor,
            handler,
        )
        from agent_framework._workflows._checkpoint_encoding import encode_checkpoint_value
        from agent_framework._workflows._runner_context import WorkflowMessage
        from agent_framework.exceptions import WorkflowCheckpointException

        class RestoreRecorder(Executor):
            def __init__(self, executor_id: str) -> None:
                super().__init__(id=executor_id)
                self.value = "snapshot"
                self.restore_calls = 0

            @handler
            async def forward(self, message: str, ctx: WorkflowContext[str]) -> None:
                await ctx.send_message(message)

            async def on_checkpoint_save(self) -> dict[str, Any]:
                return {"value": self.value}

            async def on_checkpoint_restore(self, state: dict[str, Any]) -> None:
                self.restore_calls += 1
                self.value = state["value"]

        storage = _scope_checkpoint_storage(tmp_path)
        mcp_handler = StubMcpHandler(_ok())
        leaves: list[Workflow] = []
        for index in range(2):
            factory = WorkflowFactory(
                mcp_tool_handler=mcp_handler,
                migrate_legacy_request_scopes=index == 0 or mode in {"mixed", "valid"},
            )
            leaf = factory.create_workflow_from_definition(_yaml(_action(require_approval=True)))
            await leaf.run({})
            if index == 1 and mode == "mixed":
                await leaf.run({})
            requests = await leaf._runner_context.get_pending_request_info_events()
            for request in requests.values():
                if mode != "mixed" or index == 0:
                    request.data.workflow_session_id = None
                if index != 1 or mode != "pending":
                    await leaf._runner_context.send_request_info_response(
                        request.request_id, _scope_pause_response("InvokeMcpTool")
                    )
            leaves.append(leaf)

        workflows = list(leaves)
        recorders: list[RestoreRecorder] = []
        root = leaves[1]
        for level in range(depth):
            recorder = RestoreRecorder(f"recorder_{level}")
            builder = WorkflowBuilder(start_executor=recorder, checkpoint_storage=storage)
            nested = WorkflowExecutor(root, id=f"nested_{level}")
            if level == 0:
                good = WorkflowExecutor(leaves[0], id="good")
                builder.add_fan_out_edges(recorder, [good, nested])
            else:
                builder.add_edge(recorder, nested)
            root = builder.build()
            workflows.append(root)
            recorders.append(recorder)
        for workflow in workflows:
            workflow._runner.state.set("restore_marker", "snapshot")
            workflow._runner.state.commit()
        checkpoint = await root._runner.build_checkpoint()
        checkpoint_before = encode_checkpoint_value(checkpoint.to_dict())
        await storage.save(checkpoint)

        for workflow in workflows:
            workflow._runner.state.set("restore_marker", "live")
            workflow._runner.state.commit()
            workflow._runner.state.set("uncommitted", "keep")
            await workflow._runner_context.send_message(
                WorkflowMessage(data="live", source_id="live", target_id=next(iter(workflow.executors)))
            )
        for recorder in recorders:
            recorder.value = "live"

        async def snapshots() -> list[WorkflowCheckpoint]:
            return [
                deepcopy(
                    await workflow._runner_context.build_checkpoint(
                        workflow.name, workflow.graph_signature_hash, workflow._runner.state, None, 0
                    )
                )
                for workflow in workflows
            ]

        before = await snapshots()

        async def restore() -> None:
            if restore_kind == "embedded":
                await root._runner.restore_checkpoint(checkpoint)
            else:
                await root._runner.restore_from_checkpoint(checkpoint.checkpoint_id)

        if mode in {"missing", "mixed"}:
            with pytest.raises(WorkflowCheckpointException) as exc:
                await restore()
            cause: BaseException = exc.value
            while cause.__cause__ is not None:
                cause = cause.__cause__
            assert isinstance(cause, DeclarativeWorkflowError)
            expected = "migrate_legacy_request_scopes" if mode == "missing" else "different workflow sessions"
            assert expected in str(cause)
            after = await snapshots()
            for old, current in zip(before, after, strict=True):
                assert encode_checkpoint_value(current.state) == encode_checkpoint_value(old.state)
                assert encode_checkpoint_value(current.messages) == encode_checkpoint_value(old.messages)
                assert encode_checkpoint_value(current.pending_request_info_events) == encode_checkpoint_value(
                    old.pending_request_info_events
                )
            assert all(workflow._runner.state.get("uncommitted") == "keep" for workflow in workflows)
            assert all(recorder.value == "live" and recorder.restore_calls == 0 for recorder in recorders)
        else:
            await restore()
            assert all(workflow._runner.state.get("restore_marker") == "snapshot" for workflow in workflows)
            assert all(recorder.value == "snapshot" and recorder.restore_calls == 1 for recorder in recorders)
            assert mcp_handler.call_count == 0
            for index, leaf in enumerate(leaves):
                queued = await leaf._runner_context.get_queued_response_info_events()
                if mode == "pending" and index == 1:
                    [pending] = (await leaf._runner_context.get_pending_request_info_events()).values()
                    assert pending.data.workflow_session_id is None
                    assert not queued
                    continue
                [request] = queued
                scope = f"legacy-request:{request.request_id}"
                assert request.data.workflow_session_id == scope
                _ = [event async for event in leaf._runner.run_until_convergence()]
                assert mcp_handler.invocations[-1].workflow_session_id == scope
        assert encode_checkpoint_value(checkpoint.to_dict()) == checkpoint_before
        assert mcp_handler.call_count == (2 if mode == "valid" else 1 if mode == "pending" else 0)


# ---------- Output handling ------------------------------------------------


class TestOutput:
    @pytest.mark.asyncio
    async def test_output_result_parses_json_text(self) -> None:
        handler = StubMcpHandler(_ok([Content.from_text('{"k":"v","n":1}')]))
        factory = WorkflowFactory(mcp_tool_handler=handler)
        workflow = factory.create_workflow_from_definition(_yaml(_action(output={"result": "Local.Result"})))
        await workflow.run({})
        decl = workflow._runner.state.get(DECLARATIVE_STATE_KEY)
        assert decl["Local"]["Result"] == [{"k": "v", "n": 1}]

    @pytest.mark.asyncio
    async def test_output_result_falls_back_to_raw_text(self) -> None:
        handler = StubMcpHandler(_ok([Content.from_text("plain text not json")]))
        factory = WorkflowFactory(mcp_tool_handler=handler)
        workflow = factory.create_workflow_from_definition(_yaml(_action(output={"result": "Local.Result"})))
        await workflow.run({})
        decl = workflow._runner.state.get(DECLARATIVE_STATE_KEY)
        assert decl["Local"]["Result"] == ["plain text not json"]

    @pytest.mark.asyncio
    async def test_output_messages_writes_single_tool_role_message(self) -> None:
        handler = StubMcpHandler(_ok([Content.from_text("hi"), Content.from_text("there")]))
        factory = WorkflowFactory(mcp_tool_handler=handler)
        workflow = factory.create_workflow_from_definition(_yaml(_action(output={"messages": "Local.Messages"})))
        await workflow.run({})
        decl = workflow._runner.state.get(DECLARATIVE_STATE_KEY)
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
        decl = workflow._runner.state.get(DECLARATIVE_STATE_KEY)
        assert decl["Local"]["Result"] == ["https://example.com/file.txt"]

    @pytest.mark.asyncio
    async def test_output_path_object_form(self) -> None:
        handler = StubMcpHandler(_ok([Content.from_text("ok")]))
        factory = WorkflowFactory(mcp_tool_handler=handler)
        workflow = factory.create_workflow_from_definition(_yaml(_action(output={"result": {"path": "Local.Result"}})))
        await workflow.run({})
        decl = workflow._runner.state.get(DECLARATIVE_STATE_KEY)
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
        decl = workflow._runner.state.get(DECLARATIVE_STATE_KEY)
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
        decl = workflow._runner.state.get(DECLARATIVE_STATE_KEY)
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
        return state._data.get(key, default)

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
    @pytest.mark.parametrize("restore", [False, True])
    @pytest.mark.parametrize("change_context", [False, True])
    @pytest.mark.asyncio
    async def test_auth_context_binding_survives_workflow_resume(self, restore: bool, change_context: bool) -> None:
        from agent_framework import InMemoryCheckpointStorage, WorkflowBuilder

        from agent_framework_declarative._workflows import (
            ActionTrigger,
            ExternalInputResponse,
            InvokeMcpToolActionExecutor,
            MCPToolApprovalRequest,
            RequestExternalInputExecutor,
            SetValueExecutor,
            ToolApprovalResponse,
        )
        from agent_framework_declarative._workflows._declarative_base import DeclarativeEnvConfig
        from agent_framework_declarative._workflows._executors_mcp import _HEADER_BINDING_KEY

        storage = InMemoryCheckpointStorage()
        handler = StubMcpHandler(_ok())
        config = DeclarativeEnvConfig(values={"FIRST": "context-first", "SECOND": "context-second"})

        def build():
            start = SetValueExecutor({"kind": "SetValue", "id": "start", "path": "Local.selector", "value": "first"})
            change = RequestExternalInputExecutor({
                "kind": "RequestExternalInput",
                "id": "change",
                "prompt": "Select context",
                "variable": "Local.selector",
            })
            invoke = InvokeMcpToolActionExecutor(
                _action(
                    require_approval=True,
                    arguments={"q": "reviewed"},
                    headers={"Authorization": '=If(Local.selector = "first", Env.FIRST, Env.SECOND)'},
                ),
                mcp_tool_handler=handler,
            )
            invoke.set_declarative_env_config(config)
            return (
                WorkflowBuilder(name="approval_context", start_executor=start, checkpoint_storage=storage)
                .add_fan_out_edges(start, [change, invoke])
                .build()
            )

        workflow = build()
        paused = await workflow.run(ActionTrigger())
        requests = paused.get_request_info_events()
        approval = next(event for event in requests if isinstance(event.data, MCPToolApprovalRequest))
        change_request = next(event for event in requests if event is not approval)
        approval_session_id = approval.data.workflow_session_id
        assert approval_session_id
        selector = "second" if change_context else "first"
        await workflow.run(responses={change_request.request_id: ExternalInputResponse(user_input=selector)})
        assert handler.call_count == 0

        checkpoints = await storage.list_checkpoints(workflow_name=workflow.name)
        assert "context-first" not in repr(checkpoints)
        assert "context-second" not in repr(checkpoints)
        assert "context-first" not in repr(approval.data)
        assert "context-second" not in repr(approval.data)
        # Wall-clock timestamps can tie on Windows. Select the checkpoint after
        # the context change, where only the original approval remains pending.
        checkpoint = next(
            item
            for item in checkpoints
            if approval.request_id in item.pending_request_info_events
            and change_request.request_id not in item.pending_request_info_events
        )
        assert checkpoint.state[_HEADER_BINDING_KEY] not in repr(approval.data)
        if restore:
            workflow = build()
            await workflow.run(checkpoint_id=checkpoint.checkpoint_id)

        resumed = await workflow.run(responses={approval.request_id: ToolApprovalResponse(approved=True)})
        if not change_context:
            assert handler.call_count == 1
            assert not resumed.get_request_info_events()
            assert handler.last_invocation is not None
            assert handler.last_invocation.headers == {"Authorization": "context-first"}
            assert handler.last_invocation.workflow_session_id == approval_session_id
            return
        assert handler.call_count == 0
        [replacement] = resumed.get_request_info_events()
        assert replacement.request_id != approval.request_id
        assert replacement.data.arguments == {"q": "reviewed"}
        assert "context-second" not in repr(replacement.data)

        await workflow.run(responses={replacement.request_id: ToolApprovalResponse(approved=True)})
        assert handler.call_count == 1
        assert handler.last_invocation is not None
        assert handler.last_invocation.headers == {"Authorization": "context-second"}
        assert handler.last_invocation.arguments == {"q": "reviewed"}
        assert handler.last_invocation.workflow_session_id == approval_session_id

    @pytest.mark.asyncio
    async def test_approval_required_emits_request_and_yields(self, mock_state, mock_context) -> None:  # type: ignore[no-untyped-def]
        from agent_framework_declarative._workflows._declarative_base import ActionTrigger
        from agent_framework_declarative._workflows._executors_mcp import (
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

    @pytest.mark.asyncio
    async def test_approval_response_approved_invokes_handler(self, mock_state, mock_context) -> None:  # type: ignore[no-untyped-def]
        from agent_framework_declarative._workflows import ActionComplete, ActionTrigger, ToolApprovalResponse
        from agent_framework_declarative._workflows._executors_mcp import (
            InvokeMcpToolActionExecutor,
        )

        _seed_state(mock_state)
        handler = StubMcpHandler(_ok([Content.from_text('{"ok":true}')]))
        executor = InvokeMcpToolActionExecutor(
            _action(
                require_approval=True,
                arguments={"q": "x"},
                headers={"Authorization": "Bearer tk"},
                output={"result": "Local.Result"},
            ),
            mcp_tool_handler=handler,
        )
        await executor.handle_action(ActionTrigger(), mock_context)
        request = mock_context.request_info.call_args.args[0]
        await executor.handle_approval_response(request, ToolApprovalResponse(approved=True), mock_context)

        assert handler.call_count == 1
        inv = handler.last_invocation
        assert inv is not None
        # Invocation fields source from the approval request payload.
        assert inv.tool_name == "search"
        assert inv.server_url == "https://mcp.example/api"
        assert inv.arguments == {"q": "x"}
        # Headers are re-evaluated from the action definition on resume.
        assert inv.headers == {"Authorization": "Bearer tk"}
        # ActionComplete was sent.
        mock_context.send_message.assert_called_once()
        sent = mock_context.send_message.call_args[0][0]
        assert isinstance(sent, ActionComplete)

    @pytest.mark.asyncio
    async def test_approval_response_rejected_assigns_error(self, mock_state, mock_context) -> None:  # type: ignore[no-untyped-def]
        from agent_framework_declarative._workflows import ToolApprovalResponse
        from agent_framework_declarative._workflows._executors_mcp import (
            InvokeMcpToolActionExecutor,
            MCPToolApprovalRequest,
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
        await executor.handle_approval_response(
            MCPToolApprovalRequest(
                request_id="req-2",
                tool_name="search",
                server_url="https://mcp.example/api",
                server_label=None,
                arguments={},
                workflow_session_id="workflow-a",
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
        decl = workflow._runner.state.get(DECLARATIVE_STATE_KEY)
        assert decl["Local"]["Result"] == "Error: server down"

    @pytest.mark.asyncio
    async def test_tool_execution_exception_becomes_error_result(self) -> None:
        handler = StubMcpHandler(raise_exc=ToolExecutionException("invalid arguments"))
        factory = WorkflowFactory(mcp_tool_handler=handler)
        workflow = factory.create_workflow_from_definition(_yaml(_action(output={"result": "Local.Result"})))
        await workflow.run({})
        decl = workflow._runner.state.get(DECLARATIVE_STATE_KEY)
        assert decl["Local"]["Result"] == "Error: invalid arguments"

    @pytest.mark.asyncio
    async def test_httpx_error_becomes_error_result(self) -> None:
        handler = StubMcpHandler(raise_exc=httpx.ConnectError("dns fail"))
        factory = WorkflowFactory(mcp_tool_handler=handler)
        workflow = factory.create_workflow_from_definition(_yaml(_action(output={"result": "Local.Result"})))
        await workflow.run({})
        decl = workflow._runner.state.get(DECLARATIVE_STATE_KEY)
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


# ---------- _format_outputs_for_send --------------------------------------


class TestFormatOutputsForSend:
    """Direct tests for the auto-send rendering helper.

    Regression for PR #5630 review-comment 4: a single scalar JSON value
    must render bare (e.g. ``"42"``) rather than wrapped (``"[42]"``).
    """

    @pytest.mark.parametrize(
        ("parsed", "expected"),
        [
            ([], ""),
            (["hello"], "hello"),
            (["a", "b"], "a\nb"),
            ([42], "42"),
            ([3.14], "3.14"),
            ([True], "true"),
            ([False], "false"),
            ([None], "null"),
            ([{"k": "v"}], '{"k": "v"}'),
            ([[1, 2]], "[1, 2]"),
            (["hello", 42], '["hello", 42]'),
            ([{"a": 1}, {"b": 2}], '[{"a": 1}, {"b": 2}]'),
        ],
    )
    def test_format_outputs_for_send(self, parsed: list[Any], expected: str) -> None:
        from agent_framework_declarative._workflows._executors_mcp import _format_outputs_for_send

        assert _format_outputs_for_send(parsed) == expected
