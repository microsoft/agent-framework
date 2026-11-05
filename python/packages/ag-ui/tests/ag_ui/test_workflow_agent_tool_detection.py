# Copyright (c) Microsoft. All rights reserved.

"""Tests of the search for tools that wrap a WorkflowAgent, which AG-UI refuses to serve."""

from __future__ import annotations

import pytest
from workflow_scope_helpers import (  # pyrefly: ignore[missing-import] # pyright: ignore[reportMissingImports]
    WORKFLOW_TOOL_NAME,
    RecordingChatClient,
    build_agent,
    build_agent_with_tools,
    build_runner_with_a_workflow_tool,
    build_workflow,
    build_workflow_tool,
)

from agent_framework_ag_ui._session_ownership import workflow_agent_tools

# The forms that are an agent or a workflow themselves. The two wrapper forms are unwrapped by the endpoint.
SEARCHABLE_FORMS = ["agent", "sub_agent", "executor_agent", "workflow_agent_runner", "nested_workflow"]


@pytest.mark.parametrize("form", SEARCHABLE_FORMS)
def test_workflow_agent_tools_names_the_tool_in_every_form(form: str) -> None:
    assert workflow_agent_tools(build_runner_with_a_workflow_tool(form)) == [WORKFLOW_TOOL_NAME]


def test_workflow_agent_tools_ignores_the_tools_of_ordinary_agents() -> None:
    outer = build_agent_with_tools(build_agent(RecordingChatClient()).as_tool(name="sub_agent_tool"))

    assert workflow_agent_tools(outer) == []


def test_workflow_agent_tools_finds_nothing_in_a_workflow_without_tools() -> None:
    assert workflow_agent_tools(build_workflow(build_agent(RecordingChatClient()))) == []


def test_workflow_agent_tools_finds_nothing_in_an_object_that_is_neither_an_agent_nor_a_workflow() -> None:
    assert workflow_agent_tools(object()) == []


def test_workflow_agent_tools_terminates_when_agents_delegate_to_each_other() -> None:
    first = build_agent_with_tools(name="first")
    second = build_agent_with_tools(first.as_tool(name="first_tool"), name="second")
    first.default_options["tools"] = [second.as_tool(name="second_tool")]

    assert workflow_agent_tools(first) == []


def test_workflow_agent_tools_reports_a_workflow_tool_that_sits_behind_a_cycle() -> None:
    first = build_agent_with_tools(name="first")
    second = build_agent_with_tools(first.as_tool(name="first_tool"), build_workflow_tool(), name="second")
    first.default_options["tools"] = [second.as_tool(name="second_tool")]

    assert workflow_agent_tools(first) == [WORKFLOW_TOOL_NAME]


def test_workflow_agent_tools_looks_through_a2ui_runners() -> None:
    pytest.importorskip("ag_ui_a2ui_toolkit")
    from agent_framework_ag_ui._a2ui import enable_a2ui

    outer = build_agent_with_tools(build_workflow_tool())

    assert workflow_agent_tools(enable_a2ui(outer, object())) == [WORKFLOW_TOOL_NAME]
