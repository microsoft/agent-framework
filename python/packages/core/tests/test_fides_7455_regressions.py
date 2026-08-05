# Copyright (c) Microsoft. All rights reserved.

"""Regression tests for the FIDES integration fixes from issue #7455."""

import asyncio
import contextlib
from typing import Any, cast

from agent_framework._harness._tool_approval import (
    ToolApprovalMiddleware,
    ToolApprovalRule,
    ToolApprovalState,
    _function_call_from_request,
    _has_policy_violation,
)
from agent_framework._middleware import FunctionInvocationContext, FunctionMiddlewarePipeline, MiddlewareTermination
from agent_framework._sessions import AgentSession
from agent_framework._tools import (
    FunctionInvocationConfiguration,
    FunctionTool,
    _execute_single_function_call,
    _extract_function_calls,
    _handle_function_call_results,
)
from agent_framework._types import ChatResponse, Content, Message
from agent_framework.security import (
    ConfidentialityLabel,
    ContentLabel,
    IntegrityLabel,
    LabelTrackingFunctionMiddleware,
    PolicyEnforcementFunctionMiddleware,
    SecureAgentConfig,
    get_quarantine_client,
    set_quarantine_client,
)

TRUSTED = ContentLabel(
    integrity=IntegrityLabel.TRUSTED,
    confidentiality=ConfidentialityLabel.PUBLIC,
)
UNTRUSTED = ContentLabel(
    integrity=IntegrityLabel.UNTRUSTED,
    confidentiality=ConfidentialityLabel.PUBLIC,
)


class _Session:
    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self.state: dict[str, object] = {}


async def _noop() -> None:
    pass


def _context(session: AgentSession | _Session, tool: FunctionTool, label: ContentLabel) -> FunctionInvocationContext:
    return FunctionInvocationContext(
        function=tool,
        arguments={},
        session=cast(AgentSession, session),
        metadata={"context_label": label},
    )


def test_context_label_isolated_by_session() -> None:
    tracker = LabelTrackingFunctionMiddleware()
    session_a = _Session("a")
    session_b = _Session("b")

    tracker._set_context_label(session_a, UNTRUSTED)

    assert tracker._get_context_label(session_a).integrity == IntegrityLabel.UNTRUSTED
    assert tracker._get_context_label(session_b).integrity == IntegrityLabel.TRUSTED


async def test_policy_block_returns_content_and_audit_is_per_session() -> None:
    tool = FunctionTool(name="get_config", description="test", fn=lambda: "secret")
    middleware = PolicyEnforcementFunctionMiddleware(block_on_violation=True)
    session_a = _Session("a")
    session_b = _Session("b")

    async def must_not_execute() -> None:
        raise AssertionError("blocked tool was executed")

    for _ in range(2):
        context = _context(session_a, tool, UNTRUSTED)
        with contextlib.suppress(MiddlewareTermination):
            await middleware.process(context, must_not_execute)
        assert isinstance(context.result, dict)
        assert context.result["blocked_violation"] is True

    trusted_context = _context(session_b, tool, TRUSTED)
    executed = False

    async def execute_trusted() -> None:
        nonlocal executed
        executed = True

    await middleware.process(trusted_context, execute_trusted)

    assert executed is True
    audit = middleware.get_audit_log(session_a)
    assert [entry["turn"] for entry in audit] == [1, 1]
    assert [entry["call_index"] for entry in audit] == [1, 2]
    assert middleware.get_audit_log(session_b) == []


async def test_blocked_result_is_visible_through_function_invoker() -> None:
    async def get_config() -> str:
        raise AssertionError("blocked tool was executed")

    tool = FunctionTool(name="get_config", description="test", fn=get_config)
    session = AgentSession(session_id="a2")
    tracker = LabelTrackingFunctionMiddleware(auto_hide_untrusted=False)
    tracker.reset_context_label(session)
    tracker._set_context_label(session, UNTRUSTED)
    pipeline = FunctionMiddlewarePipeline(
        tracker,
        PolicyEnforcementFunctionMiddleware(block_on_violation=True),
    )

    result_groups, terminated = await _execute_single_function_call(
        Content.from_function_call(call_id="call-a2", name="get_config", arguments={}),
        custom_args={},
        config=FunctionInvocationConfiguration(),
        tool_map={"get_config": tool},
        invocation_session=session,
        middleware_pipeline=pipeline,
        live_tools=None,
    )

    result = result_groups[0]
    assert terminated is False
    assert result.type == "function_result"
    assert result.call_id == "call-a2"
    assert result.exception and "Policy violation" in result.exception
    assert result.result and "Policy violation" in result.result
    assert result.additional_properties["blocked_violation"] is True

    # Exercise the same response path used by the agent loop: the blocked
    # result must close the original call_id so the next model request is valid.
    response = ChatResponse(
        messages=[
            Message(
                role="assistant",
                contents=[Content.from_function_call(call_id="call-a2", name="get_config", arguments={})],
            )
        ]
    )
    processing = _handle_function_call_results(
        response=response,
        execution_results=[result],
        function_call_count=1,
        function_call_messages=None,
        errors_in_a_row=0,
        had_errors=True,
        max_errors=3,
    )
    assert processing.action == "continue"
    assert response.messages[-1].contents[0].call_id == "call-a2"
    assert _extract_function_calls(response) == []


async def test_public_approval_builder_is_used_for_policy_requests() -> None:
    class CustomPolicy(PolicyEnforcementFunctionMiddleware):
        def build_function_call_content(self, context):  # type: ignore[no-untyped-def]
            function_call = super().build_function_call_content(context)
            function_call.additional_properties["host_marker"] = "custom"
            return function_call

    tool = FunctionTool(name="write_file", description="test", fn=lambda: "written")
    middleware = CustomPolicy(approval_on_violation=True)
    context = _context(_Session("b4"), tool, UNTRUSTED)
    context.metadata["call_id"] = "call-b4"

    with contextlib.suppress(MiddlewareTermination):
        await middleware.process(context, _noop)

    assert context.result.type == "function_approval_request"
    assert context.result.function_call.additional_properties["host_marker"] == "custom"


def test_secure_config_can_disable_quarantine_without_disabling_policy() -> None:
    config = SecureAgentConfig(enable_quarantine=False, auto_hide_untrusted=False)

    assert config.get_tools() == []
    assert config.get_instructions() == ""
    assert len(config.get_middleware()) == 2


def test_secure_config_rejects_hidden_content_without_quarantine_tooling() -> None:
    try:
        SecureAgentConfig(enable_quarantine=False)
    except ValueError as exc:
        assert "auto_hide_untrusted" in str(exc)
    else:
        raise AssertionError("Disabling quarantine must not leave hidden content without a handler")


def test_read_only_mcp_tools_cap_argument_confidentiality() -> None:
    from types import SimpleNamespace

    from agent_framework.security import _map_mcp_annotations_to_labels

    _, max_confidentiality, accepts_untrusted = _map_mcp_annotations_to_labels(
        SimpleNamespace(readOnlyHint=True, openWorldHint=True)
    )

    assert max_confidentiality == ConfidentialityLabel.PUBLIC
    assert accepts_untrusted is True


async def test_mcp_read_only_sink_cap_has_a_granular_opt_out() -> None:
    from types import SimpleNamespace

    from agent_framework.security import apply_mcp_security_labels

    read_only = SimpleNamespace(readOnlyHint=True, openWorldHint=True)
    tool = FunctionTool(name="search", description="test", fn=lambda: "result")
    tool.additional_properties = {"_mcp_remote_name": "search"}

    class _McpSession:
        async def list_tools(self, params: object = None) -> object:
            return SimpleNamespace(tools=[SimpleNamespace(name="search", annotations=read_only)], nextCursor=None)

    mcp = SimpleNamespace(is_connected=True, session=_McpSession(), functions=[tool])
    await apply_mcp_security_labels(mcp, mark_read_tools_as_sinks=False)

    assert "max_allowed_confidentiality" not in tool.additional_properties


async def test_mcp_explicit_override_cap_survives_read_only_sink_opt_out() -> None:
    from types import SimpleNamespace

    from agent_framework.security import apply_mcp_security_labels

    read_only = SimpleNamespace(readOnlyHint=True, openWorldHint=True)
    tool = FunctionTool(name="search", description="test", fn=lambda: "result")
    tool.additional_properties = {"_mcp_remote_name": "search"}

    class _McpSession:
        async def list_tools(self, params: object = None) -> object:
            return SimpleNamespace(tools=[SimpleNamespace(name="search", annotations=read_only)], nextCursor=None)

    mcp = SimpleNamespace(is_connected=True, session=_McpSession(), functions=[tool])
    await apply_mcp_security_labels(
        mcp,
        annotation_overrides={"search": (IntegrityLabel.TRUSTED, ConfidentialityLabel.PRIVATE)},
        mark_read_tools_as_sinks=False,
    )

    assert tool.additional_properties["max_allowed_confidentiality"] == "private"
    assert "_fides_mcp_auto_max_confidentiality" not in tool.additional_properties

    # A later annotation-only pass must not mistake the host-owned cap for an
    # auto-generated one and remove it when read-only sinks are opted out.
    await apply_mcp_security_labels(mcp, mark_read_tools_as_sinks=False)

    assert tool.additional_properties["max_allowed_confidentiality"] == "private"
    assert "_fides_mcp_auto_max_confidentiality" not in tool.additional_properties


def test_no_session_fallback_counters_are_independent() -> None:
    middleware = PolicyEnforcementFunctionMiddleware()

    assert middleware._resolve_turn_counter() == 1
    assert middleware._resolve_call_counter() == 1
    assert middleware._resolve_turn_counter() == 2
    assert middleware._resolve_call_counter() == 2


async def test_pending_approvals_are_json_persistible() -> None:
    tool = FunctionTool(name="write_file", description="test", fn=lambda: "written")
    middleware = PolicyEnforcementFunctionMiddleware(approval_on_violation=True)
    session = AgentSession(session_id="approval")
    context = _context(session, tool, UNTRUSTED)
    context.metadata["call_id"] = "call-approval"

    with contextlib.suppress(MiddlewareTermination):
        await middleware.process(context, _noop)

    pending = session.state["_fides"]["pending_policy_approvals"]["call-approval"]
    assert isinstance(pending, dict)
    restored = AgentSession.from_dict(session.to_dict())
    assert isinstance(
        restored.state["_fides"]["pending_policy_approvals"]["call-approval"],
        dict,
    )


async def test_denylist_takes_precedence_over_allowlist() -> None:
    tool = FunctionTool(name="sensitive_tool", description="test", fn=lambda: "secret")
    middleware = PolicyEnforcementFunctionMiddleware(
        allow_untrusted_tools={"sensitive_tool"},
        deny_untrusted_tools={"sensitive_tool"},
    )
    context = _context(_Session("deny"), tool, UNTRUSTED)

    async def must_not_execute() -> None:
        raise AssertionError("denylisted tool was executed")

    with contextlib.suppress(MiddlewareTermination):
        await middleware.process(context, must_not_execute)
    assert isinstance(context.result, dict)
    assert context.result["blocked_violation"] is True


async def test_tool_labels_apply_to_harness_tools() -> None:
    tool = FunctionTool(name="external_tool", description="test", fn=lambda: "external")
    config = SecureAgentConfig(tool_labels={"external_tool": UNTRUSTED})
    labeler = config.get_middleware()[0]
    context = _context(_Session("labels"), tool, TRUSTED)

    async def execute() -> None:
        context.result = Content.from_text("external")

    await labeler.process(context, execute)

    assert tool.additional_properties is None
    result = context.result[0] if isinstance(context.result, list) else context.result
    assert result.additional_properties["security_label"]["integrity"] == "untrusted"


async def test_quarantine_client_isolated_between_async_tasks() -> None:
    async def run(client: object) -> None:
        set_quarantine_client(cast(Any, client))
        await asyncio.sleep(0)
        assert get_quarantine_client() is client

    await asyncio.gather(run(object()), run(object()))


async def test_policy_violations_are_not_auto_approved_by_standing_rules() -> None:
    request = Content.from_function_approval_request(
        id="call-1",
        function_call=Content.from_function_call(call_id="call-1", name="write_file", arguments={}),
        additional_properties={"policy_violation": True},
    )
    function_call = _function_call_from_request(request)
    assert function_call is not None
    assert function_call.additional_properties["policy_violation"] is True
    assert _has_policy_violation(request) is True

    middleware = ToolApprovalMiddleware()
    state = ToolApprovalState(rules=[ToolApprovalRule(tool_name="write_file")])
    messages = [Message(role="assistant", contents=[request])]

    all_auto_approved = await middleware._process_outbound_messages(messages, state)

    assert all_auto_approved is False
    assert messages[0].contents == [request]


async def test_before_run_does_not_clear_an_external_quarantine_client() -> None:
    sentinel = object()
    set_quarantine_client(cast(Any, sentinel))
    config = SecureAgentConfig(enable_quarantine=False, auto_hide_untrusted=False)
    session = AgentSession(session_id="quarantine-preserve")

    class _Context:
        def extend_tools(self, *args: object) -> None:
            pass

        def extend_instructions(self, *args: object) -> None:
            pass

        def extend_middleware(self, *args: object) -> None:
            pass

    await config.before_run(agent=None, session=session, context=_Context(), state={})

    assert get_quarantine_client() is sentinel


async def test_public_accessors_use_the_last_session_in_the_async_context() -> None:
    config = SecureAgentConfig(enable_quarantine=False, auto_hide_untrusted=False)
    session = AgentSession(session_id="public-accessors")

    class _Context:
        def extend_tools(self, *args: object) -> None:
            pass

        def extend_instructions(self, *args: object) -> None:
            pass

        def extend_middleware(self, *args: object) -> None:
            pass

    await config.before_run(agent=None, session=session, context=_Context(), state={})
    policy_enforcer = config.policy_enforcer
    assert policy_enforcer is not None
    policy_enforcer._log_violation({"type": "test"}, session)

    assert config.get_audit_log() == [{"type": "test"}]


async def test_tool_labels_preserve_server_supplied_result_labels() -> None:
    server_label = ContentLabel(
        integrity=IntegrityLabel.TRUSTED,
        confidentiality=ConfidentialityLabel.PRIVATE,
    )
    configured_label = ContentLabel(
        integrity=IntegrityLabel.UNTRUSTED,
        confidentiality=ConfidentialityLabel.PUBLIC,
    )
    tool = FunctionTool(name="external_tool", description="test", fn=lambda: "external")
    config = SecureAgentConfig(tool_labels={"external_tool": configured_label})
    context = _context(_Session("server-label"), tool, TRUSTED)

    async def execute() -> None:
        context.result = Content.from_text("external", additional_properties={"security_label": server_label.to_dict()})

    await config.get_middleware()[0].process(context, execute)

    assert tool.additional_properties is None
    result = context.result[0]
    assert result.additional_properties["security_label"] == server_label.to_dict()


async def test_tool_labels_do_not_leak_between_configs() -> None:
    tool = FunctionTool(name="external_tool", description="test", fn=lambda: "external")
    config_a = SecureAgentConfig(tool_labels={"external_tool": UNTRUSTED})
    config_b = SecureAgentConfig(tool_labels={"external_tool": TRUSTED})

    async def run(config: SecureAgentConfig, session_id: str) -> Content:
        context = _context(_Session(session_id), tool, TRUSTED)

        async def execute() -> None:
            context.result = Content.from_text("external")

        await config.get_middleware()[0].process(context, execute)
        return context.result[0]

    result_a = await run(config_a, "labels-a")
    result_b = await run(config_b, "labels-b")

    assert result_a.additional_properties["security_label"]["integrity"] == "untrusted"
    assert result_b.additional_properties["security_label"]["integrity"] == "trusted"
    assert tool.additional_properties is None


def test_label_metadata_is_durable_state_safe() -> None:
    session = AgentSession(session_id="safe-label")
    session.state["_fides"] = {
        "context_label": ContentLabel(metadata={"opaque": object()}).to_dict(),
    }

    restored = AgentSession.from_dict(session.to_dict())

    assert restored.state["_fides"]["context_label"]["metadata"]["opaque"]


def test_audit_log_has_a_bounded_default() -> None:
    middleware = PolicyEnforcementFunctionMiddleware(max_audit_log_entries=2)
    session = _Session("audit-cap")

    for index in range(3):
        middleware._log_violation({"index": index}, session)

    assert middleware.get_audit_log(session) == [{"index": 1}, {"index": 2}]
