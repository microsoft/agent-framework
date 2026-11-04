# Copyright (c) Microsoft. All rights reserved.

"""AG-UI endpoint tests: an agent that exposes a WorkflowAgent as a tool is rejected, not served."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from workflow_scope_helpers import (  # pyrefly: ignore[missing-import] # pyright: ignore[reportMissingImports]
    OUTER_REPLY_TEXT,
    RUNNER_FORMS_WITH_A_WORKFLOW_TOOL,
    WORKFLOW_TOOL_NAME,
    RecordingChatClient,
    assistant_text,
    build_agent,
    build_agent_with_tools,
    build_app,
    build_runner_with_a_workflow_tool,
    build_workflow_tool,
    build_workflow_whose_agent_has_tools,
    event_types,
    post_run,
    run_error_codes,
)

from agent_framework_ag_ui import AgentFrameworkWorkflow

REJECTED_CODE = "WORKFLOW_AGENT_TOOL_UNSUPPORTED"
SCOPE_MODES = ["authorization", "snapshot", "single_user"]


def _assert_rejected(events: list[dict[str, Any]]) -> None:
    assert event_types(events) == ["RUN_STARTED", "RUN_ERROR"]
    assert run_error_codes(events) == [REJECTED_CODE]


@pytest.mark.parametrize("form", RUNNER_FORMS_WITH_A_WORKFLOW_TOOL)
def test_endpoint_rejects_a_runner_that_exposes_a_workflow_agent_as_a_tool(form: str) -> None:
    with pytest.raises(ValueError, match=r"WorkflowAgent\.as_tool\(\)") as rejection:
        build_app(build_runner_with_a_workflow_tool(form), "single_user")

    assert WORKFLOW_TOOL_NAME in str(rejection.value)


def test_endpoint_registers_a_workflow_factory_without_calling_it() -> None:
    calls: list[str] = []

    def factory(thread_id: str) -> Any:
        calls.append(thread_id)
        return build_workflow_whose_agent_has_tools(build_workflow_tool())

    build_app(AgentFrameworkWorkflow(workflow_factory=factory), "single_user")

    # A factory builds its workflow per request, so only a run can find out what it exposes.
    assert calls == []


@pytest.mark.parametrize("scope_mode", SCOPE_MODES)
def test_workflow_factory_that_builds_a_workflow_agent_tool_ends_the_run(scope_mode: Any) -> None:
    inner_client = RecordingChatClient()
    runner = AgentFrameworkWorkflow(
        workflow_factory=lambda _thread_id: build_workflow_whose_agent_has_tools(build_workflow_tool(inner_client))
    )

    with TestClient(build_app(runner, scope_mode)) as http:
        events = post_run(http, "alice", "thread-a", "ALICE_ONLY")

    _assert_rejected(events)
    assert inner_client.calls == []


@pytest.mark.parametrize("scope_mode", SCOPE_MODES)
def test_agent_that_gains_a_workflow_agent_tool_after_registration_ends_the_run(scope_mode: Any) -> None:
    inner_client = RecordingChatClient()
    agent = build_agent_with_tools()
    app = build_app(agent, scope_mode)
    agent.default_options["tools"] = [build_workflow_tool(inner_client)]

    with TestClient(app) as http:
        events = post_run(http, "alice", "thread-a", "ALICE_ONLY")

    _assert_rejected(events)
    assert inner_client.calls == []


@pytest.mark.parametrize("scope_mode", SCOPE_MODES)
def test_endpoint_still_serves_an_agent_that_exposes_an_ordinary_agent_as_a_tool(scope_mode: Any) -> None:
    inner_client = RecordingChatClient()
    sub_agent_tool = build_agent(inner_client).as_tool(name="sub_agent_tool")
    outer = build_agent_with_tools(sub_agent_tool, tool_name="sub_agent_tool")

    with TestClient(build_app(outer, scope_mode)) as http:
        alice = post_run(http, "alice", "thread-a", "ALICE_ONLY")
        bob = post_run(http, "bob", "thread-b", "BOB_ONLY")

    for events in (alice, bob):
        assert run_error_codes(events) == []
        assert OUTER_REPLY_TEXT in assistant_text(events)
    # Each call reached the sub-agent, which starts from a new session every time.
    assert len(inner_client.calls) == 2
    assert not inner_client.saw("ALICE_ONLY", call=1)
