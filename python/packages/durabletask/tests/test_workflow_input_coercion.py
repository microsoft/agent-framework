# Copyright (c) Microsoft. All rights reserved.

"""Unit tests for workflow initial-input coercion (`_coerce_initial_input`).

A durable workflow runs as a durable orchestration, so its initial payload
arrives as plain JSON (no type markers). The shared engine reconstructs the
start executor's declared input type from that JSON, mirroring in-process
delivery. These tests pin that behavior across the relevant start-executor
shapes.
"""

import json
from dataclasses import dataclass
from unittest.mock import Mock

from agent_framework import AgentExecutor, Executor, WorkflowContext, handler
from pydantic import BaseModel

from agent_framework_durabletask._workflows.orchestrator import _coerce_initial_input


@dataclass
class _Submission:
    content_id: str
    title: str


class _SubmissionModel(BaseModel):
    content_id: str
    title: str


class _StrStart(Executor):
    def __init__(self) -> None:
        super().__init__(id="str_start")

    @handler
    async def run(self, message: str, ctx: WorkflowContext) -> None:  # pragma: no cover - never invoked
        ...


class _DataclassStart(Executor):
    def __init__(self) -> None:
        super().__init__(id="dc_start")

    @handler
    async def run(self, message: _Submission, ctx: WorkflowContext) -> None:  # pragma: no cover - never invoked
        ...


class _PydanticStart(Executor):
    def __init__(self) -> None:
        super().__init__(id="pyd_start")

    @handler
    async def run(self, message: _SubmissionModel, ctx: WorkflowContext) -> None:  # pragma: no cover - never invoked
        ...


def _workflow_with(executor: Executor | Mock) -> Mock:
    workflow = Mock()
    workflow.executors = {executor.id: executor}
    workflow.start_executor_id = executor.id
    return workflow


class TestCoerceInitialInput:
    """Test reconstruction of the initial workflow input by start-executor type."""

    def test_str_start_passes_string_through(self) -> None:
        workflow = _workflow_with(_StrStart())

        assert _coerce_initial_input(workflow, "hello world") == "hello world"

    def test_dataclass_start_reconstructs_from_dict(self) -> None:
        workflow = _workflow_with(_DataclassStart())

        result = _coerce_initial_input(workflow, {"content_id": "x", "title": "T"})

        assert isinstance(result, _Submission)
        assert result.content_id == "x"
        assert result.title == "T"

    def test_pydantic_start_reconstructs_from_dict(self) -> None:
        workflow = _workflow_with(_PydanticStart())

        result = _coerce_initial_input(workflow, {"content_id": "x", "title": "T"})

        assert isinstance(result, _SubmissionModel)
        assert result.content_id == "x"

    def test_str_start_leaves_dict_unchanged(self) -> None:
        """A str-typed start executor declares text; a dict is not coerced to str."""
        workflow = _workflow_with(_StrStart())
        payload = {"content_id": "x"}

        assert _coerce_initial_input(workflow, payload) == payload

    def test_agent_start_passes_string_through(self) -> None:
        agent_executor = Mock(spec=AgentExecutor)
        agent_executor.id = "agent"
        workflow = _workflow_with(agent_executor)

        assert _coerce_initial_input(workflow, "draft this email") == "draft this email"

    def test_agent_start_stringifies_dict(self) -> None:
        """Agents only consume text, so a structured payload is serialized to text."""
        agent_executor = Mock(spec=AgentExecutor)
        agent_executor.id = "agent"
        workflow = _workflow_with(agent_executor)

        result = _coerce_initial_input(workflow, {"email": "hi"})

        assert result == json.dumps({"email": "hi"})

    def test_missing_start_executor_passes_through(self) -> None:
        workflow = Mock()
        workflow.executors = {}
        workflow.start_executor_id = "missing"
        payload = {"a": 1}

        assert _coerce_initial_input(workflow, payload) == payload

    def test_pickle_marker_injection_is_neutralized(self) -> None:
        """A crafted pickle-marker payload is stripped before reconstruction (no pickle RCE).

        The initial workflow input is untrusted, so a dict carrying the checkpoint
        ``__pickled__`` marker must be neutralized rather than flowing into
        ``deserialize_value`` (which would ``pickle.loads`` it).
        """
        workflow = _workflow_with(_DataclassStart())
        malicious = {"__pickled__": "<crafted-base64-payload>", "content_id": "x", "title": "T"}

        # The marker-bearing dict is replaced with None, never unpickled or reconstructed.
        assert _coerce_initial_input(workflow, malicious) is None
