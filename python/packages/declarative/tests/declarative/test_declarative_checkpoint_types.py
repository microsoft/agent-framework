# Copyright (c) Microsoft. All rights reserved.

"""Built-in declarative workflow types must survive a checkpoint round trip.

Checkpoint restore runs pickle through a restricted unpickler. Its default allowlist
trusts ``agent_framework.`` and ``agent_framework_orchestrations.`` but not
``agent_framework_declarative``, so framework-owned declarative types have to opt in by
name. Importing the package is what registers them.

These tests use a ``FileCheckpointStorage`` built with **no** ``allowed_checkpoint_types``,
because the bug was that users had to supply framework-internal module paths themselves.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest
from agent_framework import Content, FileCheckpointStorage, Message, WorkflowCheckpoint

from agent_framework_declarative import ExternalInputResponse, WorkflowFactory
from agent_framework_declarative._workflows import (
    ActionComplete,
    ActionTrigger,
    AgentExternalInputRequest,
    AgentExternalInputResponse,
    ExternalInputRequest,
    ExternalLoopState,
    LoopControl,
    LoopIterationResult,
    MCPToolApprovalRequest,
    ToolApprovalRequest,
    ToolApprovalResponse,
)
from agent_framework_declarative._workflows._declarative_base import ConditionResult

try:
    import powerfx  # noqa: F401

    _powerfx_available = True
except (ImportError, RuntimeError):
    _powerfx_available = False


def _payloads() -> list[tuple[str, Any]]:
    """One populated instance of every declarative type that crosses a checkpoint."""
    message = Message(role="assistant", contents=["Which city?"])
    return [
        ("ActionTrigger", ActionTrigger(data={"input": "hello"})),
        ("ActionComplete", ActionComplete(result={"value": 1})),
        ("ConditionResult", ConditionResult(matched=True, branch_index=0, value=True)),
        ("LoopIterationResult", LoopIterationResult(has_next=True, current_item="a", current_index=0)),
        ("LoopControl", LoopControl(action="break")),
        ("ExternalInputRequest", ExternalInputRequest(request_id="r1", message="Approve?", metadata={"k": "v"})),
        ("ExternalInputResponse", ExternalInputResponse(user_input="yes", value={"approved": True})),
        (
            "AgentExternalInputRequest",
            AgentExternalInputRequest(
                request_id="r2",
                agent_name="planner",
                agent_response="Which city?",
                iteration=1,
                messages=[message],
                function_calls=[Content.from_function_call(call_id="c1", name="lookup", arguments={"q": "x"})],
            ),
        ),
        (
            "AgentExternalInputResponse",
            AgentExternalInputResponse(
                user_input="Seattle",
                messages=[Message(role="user", contents=["Seattle"])],
                function_results={"c1": Content.from_function_result(call_id="c1", result="ok")},
            ),
        ),
        ("ToolApprovalRequest", ToolApprovalRequest(request_id="r3", function_name="send", arguments={"to": "a"})),
        ("ToolApprovalResponse", ToolApprovalResponse(approved=False, reason="not now")),
        (
            "MCPToolApprovalRequest",
            MCPToolApprovalRequest(
                request_id="r4",
                tool_name="search",
                server_url="https://example.com/mcp",
                server_label="docs",
                arguments={"query": "agents"},
                header_names=["Authorization"],
                metadata={"source": "test"},
            ),
        ),
        (
            "ExternalLoopState",
            ExternalLoopState(
                agent_name="planner",
                iteration=2,
                external_loop_when="=true",
                messages_var="Local.messages",
                response_obj_var=None,
                result_property=None,
                auto_send=True,
            ),
        ),
    ]


@pytest.mark.parametrize(("name", "payload"), _payloads(), ids=[name for name, _ in _payloads()])
async def test_declarative_type_survives_checkpoint_round_trip(tmp_path: Path, name: str, payload: Any) -> None:
    """Saving and restoring a built-in declarative payload needs no user allowlist."""
    storage = FileCheckpointStorage(tmp_path)  # deliberately no allowed_checkpoint_types
    await storage.save(
        WorkflowCheckpoint(
            workflow_name="declarative",
            graph_signature_hash="test-hash",
            checkpoint_id=f"ck-{name}",
            state={"payload": payload},
        )
    )

    restored = await storage.load(f"ck-{name}")

    restored_payload = restored.state["payload"]
    assert type(restored_payload) is type(payload)
    assert vars(restored_payload).keys() == vars(payload).keys()


@pytest.mark.skipif(not _powerfx_available, reason="PowerFx engine not available")
async def test_paused_workflow_resumes_from_file_checkpoint(tmp_path: Path) -> None:
    """A workflow paused on external input can be restored from storage and resumed."""
    yaml_definition = """
name: checkpoint-resume
actions:
  - kind: SetValue
    path: Local.greeting
    value: Hello
  - kind: RequestExternalInput
    id: ask
    prompt: Approve?
    variable: Local.answer
  - kind: SendActivity
    activity:
      text: '=Concatenate(Local.greeting, " - ", Local.answer)'
"""
    storage = FileCheckpointStorage(tmp_path)  # deliberately no allowed_checkpoint_types
    workflow = WorkflowFactory(checkpoint_storage=storage).create_workflow_from_yaml(yaml_definition)

    result = await workflow.run({})
    requests = result.get_request_info_events()
    assert len(requests) == 1

    # Every checkpoint written to disk must also decode; undecodable ones are skipped by the listing.
    files_on_disk = [name for name in os.listdir(tmp_path) if name.endswith(".json")]
    listed = await storage.list_checkpoints(workflow_name=workflow.name)
    assert len(listed) == len(files_on_disk) > 1

    latest = await storage.get_latest(workflow_name=workflow.name)
    assert latest is not None

    restored_workflow = WorkflowFactory(checkpoint_storage=storage).create_workflow_from_yaml(yaml_definition)
    await restored_workflow.run(checkpoint_id=latest.checkpoint_id)
    resumed = await restored_workflow.run(
        responses={requests[0].request_id: ExternalInputResponse(user_input="approved")}
    )

    assert resumed.get_outputs() == ["Hello - approved"]
