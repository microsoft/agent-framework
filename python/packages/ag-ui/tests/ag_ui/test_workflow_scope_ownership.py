# Copyright (c) Microsoft. All rights reserved.

"""AG-UI endpoint tests: workflow-owned agent sessions stay bound to one authorization scope."""

from __future__ import annotations

import asyncio
import gc
import weakref
from concurrent.futures import ThreadPoolExecutor
from typing import Any, cast

import pytest
from agent_framework import (
    AgentExecutor,
    SupportsAgentRun,
    Workflow,
    WorkflowBuilder,
    WorkflowContext,
    WorkflowExecutor,
    executor,
)
from fastapi.testclient import TestClient
from workflow_scope_helpers import (  # pyrefly: ignore[missing-import] # pyright: ignore[reportMissingImports]
    INVOKE_PREFIX,
    REPLY_TEXT,
    RecordingChatClient,
    always_approve_resume,
    assistant_text,
    build_agent,
    build_app,
    build_workflow,
    event_types,
    interrupts,
    post_run,
    run_error_codes,
)

from agent_framework_ag_ui import AgentFrameworkAgent, AgentFrameworkWorkflow
from agent_framework_ag_ui._session_ownership import claim_agent_executors, claim_workflow_agent

SCOPE_MODES = ["authorization", "snapshot"]
CONFLICT_CODE = "WORKFLOW_SCOPE_CONFLICT"


def _assert_completed(events: list[dict[str, Any]]) -> None:
    """A run reached the model, produced its reply, and finished without an error."""
    assert run_error_codes(events) == []
    assert REPLY_TEXT in assistant_text(events)
    assert "RUN_FINISHED" in event_types(events)


def _assert_scope_conflict(events: list[dict[str, Any]]) -> None:
    assert event_types(events) == ["RUN_STARTED", "RUN_ERROR"]
    assert run_error_codes(events) == [CONFLICT_CODE]


# region shared instances serve one scope


@pytest.mark.parametrize("scope_mode", SCOPE_MODES)
@pytest.mark.parametrize("persist_snapshots", [False, True])
@pytest.mark.parametrize("same_thread_id", [False, True])
def test_shared_workflow_serves_only_the_first_authorization_scope(
    scope_mode: Any, persist_snapshots: bool, same_thread_id: bool
) -> None:
    client = RecordingChatClient()
    app = build_app(build_workflow(build_agent(client)), scope_mode, persist_snapshots=persist_snapshots)

    with TestClient(app) as http:
        alice_first = post_run(http, "alice", "thread-a", "ALICE_FIRST")
        bob = post_run(http, "bob", "thread-a" if same_thread_id else "thread-b", "BOB_ONLY")
        alice_second = post_run(http, "alice", "thread-a", "ALICE_SECOND")

    _assert_completed(alice_first)
    _assert_completed(alice_second)
    _assert_scope_conflict(bob)
    # Only Alice's two runs reached the model, so Bob's request and Alice's history never met.
    assert len(client.calls) == 2
    assert not any("BOB_ONLY" in text for call in client.calls for _, text in call)
    assert client.saw("ALICE_FIRST", call=1)
    assert client.sessions[0] is client.sessions[1]


@pytest.mark.parametrize("scope_mode", SCOPE_MODES)
@pytest.mark.parametrize("share", ["one_workflow", "one_builder"])
def test_workflow_factory_result_shared_between_scopes_is_refused(scope_mode: Any, share: str) -> None:
    client = RecordingChatClient()
    agent = build_agent(client)
    shared_workflow = build_workflow(agent)
    shared_builder = WorkflowBuilder(start_executor=AgentExecutor(agent, id="worker"))
    runner = AgentFrameworkWorkflow(
        workflow_factory=lambda _thread_id: shared_workflow if share == "one_workflow" else shared_builder.build()
    )

    with TestClient(build_app(runner, scope_mode)) as http:
        alice = post_run(http, "alice", "thread-a", "ALICE_ONLY")
        bob = post_run(http, "bob", "thread-b", "BOB_ONLY")

    _assert_completed(alice)
    _assert_scope_conflict(bob)
    assert len(client.calls) == 1


@pytest.mark.parametrize("scope_mode", SCOPE_MODES)
def test_factory_that_wraps_a_shared_workflow_agent_is_refused(scope_mode: Any) -> None:
    client = RecordingChatClient()
    shared_workflow_agent = build_workflow(build_agent(client)).as_agent()

    def factory(_thread_id: str) -> Workflow:
        outer = AgentExecutor(shared_workflow_agent, id="outer")
        return WorkflowBuilder(start_executor=outer, output_from=[outer]).build()

    runner = AgentFrameworkWorkflow(workflow_factory=factory)

    with TestClient(build_app(runner, scope_mode)) as http:
        alice = post_run(http, "alice", "thread-a", "ALICE_ONLY")
        bob = post_run(http, "bob", "thread-b", "BOB_ONLY")

    _assert_completed(alice)
    _assert_scope_conflict(bob)
    assert len(client.calls) == 1


@pytest.mark.parametrize("scope_mode", SCOPE_MODES)
@pytest.mark.parametrize("wrap", ["workflow_agent", "wrapped_workflow_agent"])
def test_workflow_agent_serves_only_the_first_authorization_scope(scope_mode: Any, wrap: str) -> None:
    client = RecordingChatClient()
    workflow_agent = build_workflow(build_agent(client)).as_agent()
    runner = workflow_agent if wrap == "workflow_agent" else AgentFrameworkAgent(agent=workflow_agent)

    with TestClient(build_app(runner, scope_mode)) as http:
        alice_first = post_run(http, "alice", "thread-a", "ALICE_FIRST")
        bob = post_run(http, "bob", "thread-b", "BOB_ONLY")
        alice_second = post_run(http, "alice", "thread-a", "ALICE_SECOND")

    _assert_completed(alice_first)
    _assert_completed(alice_second)
    _assert_scope_conflict(bob)
    assert len(client.calls) == 2
    assert not any("BOB_ONLY" in text for call in client.calls for _, text in call)


@pytest.mark.parametrize("scope_mode", SCOPE_MODES)
def test_a2ui_wrapped_workflow_agent_serves_only_the_first_authorization_scope(scope_mode: Any) -> None:
    pytest.importorskip("ag_ui_a2ui_toolkit")
    from agent_framework_ag_ui._a2ui import enable_a2ui

    client = RecordingChatClient()
    workflow_agent = build_workflow(build_agent(client)).as_agent()
    runner = AgentFrameworkAgent(agent=cast(SupportsAgentRun, enable_a2ui(workflow_agent, object())))

    with TestClient(build_app(runner, scope_mode)) as http:
        alice = post_run(http, "alice", "thread-a", "ALICE_ONLY")
        bob = post_run(http, "bob", "thread-b", "BOB_ONLY")

    _assert_completed(alice)
    _assert_scope_conflict(bob)
    assert len(client.calls) == 1
    assert not any("BOB_ONLY" in text for call in client.calls for _, text in call)


@pytest.mark.parametrize("scope_mode", SCOPE_MODES)
def test_factory_that_shares_one_agent_session_between_scopes_is_refused(scope_mode: Any) -> None:
    client = RecordingChatClient()
    agent = build_agent(client)
    shared_session = agent.create_session()
    runner = AgentFrameworkWorkflow(workflow_factory=lambda _thread_id: build_workflow(agent, session=shared_session))

    with TestClient(build_app(runner, scope_mode)) as http:
        alice = post_run(http, "alice", "thread-a", "ALICE_ONLY")
        bob = post_run(http, "bob", "thread-b", "BOB_ONLY")

    _assert_completed(alice)
    _assert_scope_conflict(bob)
    assert len(client.calls) == 1
    assert not any("ALICE_ONLY" in text for call in client.calls[1:] for _, text in call)


# endregion

# region requests that start no workflow, and runs without a scope


@pytest.mark.parametrize("scope_mode", SCOPE_MODES)
@pytest.mark.parametrize("runner_kind", ["workflow", "workflow_agent"])
def test_snapshot_replay_does_not_bind_the_executors(scope_mode: Any, runner_kind: str) -> None:
    client = RecordingChatClient()
    workflow = build_workflow(build_agent(client))
    runner = workflow if runner_kind == "workflow" else workflow.as_agent()

    with TestClient(build_app(runner, scope_mode, persist_snapshots=True)) as http:
        # A read-only replay starts no workflow and reaches no model, so it does not decide who owns the executors.
        replay = post_run(http, "alice", "thread-a")
        bob = post_run(http, "bob", "thread-b", "BOB_FIRST")
        alice = post_run(http, "alice", "thread-a", "ALICE_LATER")

    assert event_types(replay) == ["RUN_STARTED", "RUN_FINISHED"]
    _assert_completed(bob)
    _assert_scope_conflict(alice)
    assert len(client.calls) == 1


@pytest.mark.parametrize("scope_mode", SCOPE_MODES)
def test_workflow_run_without_a_scope_blocks_a_later_scoped_endpoint(scope_mode: Any) -> None:
    client = RecordingChatClient()
    runner = AgentFrameworkWorkflow(workflow=build_workflow(build_agent(client)))

    async def run_without_scope() -> list[Any]:
        request = {
            "thread_id": "thread-local",
            "run_id": "run-local",
            "messages": [{"id": "message-local", "role": "user", "content": "LOCAL_ONLY"}],
        }
        return [event async for event in runner.run(request)]

    local_events = asyncio.run(run_without_scope())

    assert any(type(event).__name__ == "RunFinishedEvent" for event in local_events)
    with TestClient(build_app(runner, scope_mode)) as http:
        alice = post_run(http, "alice", "thread-a", "ALICE_ONLY")

    _assert_scope_conflict(alice)
    assert len(client.calls) == 1


# endregion

# region intentional persistence and per-scope construction keep working


@pytest.mark.parametrize("scope_mode", ["single_user", "authorization"])
def test_shared_workflow_keeps_one_state_for_every_thread_of_its_scope(scope_mode: Any) -> None:
    client = RecordingChatClient()
    app = build_app(build_workflow(build_agent(client)), scope_mode)

    with TestClient(app) as http:
        first = post_run(http, "alice", "thread-a", "FIRST_THREAD")
        second = post_run(http, "alice", "thread-b", "SECOND_THREAD")

    _assert_completed(first)
    _assert_completed(second)
    assert client.saw("FIRST_THREAD", call=1)
    assert client.sessions[0] is client.sessions[1]


@pytest.mark.parametrize("scope_mode", SCOPE_MODES)
@pytest.mark.parametrize("persist_snapshots", [False, True])
@pytest.mark.parametrize("same_thread_id", [False, True])
def test_workflow_factory_isolates_scopes_and_keeps_each_scope_history(
    scope_mode: Any, persist_snapshots: bool, same_thread_id: bool
) -> None:
    client = RecordingChatClient()
    agent = build_agent(client)
    runner = AgentFrameworkWorkflow(workflow_factory=lambda _thread_id: build_workflow(agent))
    app = build_app(runner, scope_mode, persist_snapshots=persist_snapshots)

    with TestClient(app) as http:
        alice_first = post_run(http, "alice", "thread-a", "ALICE_FIRST")
        bob_first = post_run(http, "bob", "thread-a" if same_thread_id else "thread-b", "BOB_FIRST")
        alice_second = post_run(http, "alice", "thread-a", "ALICE_SECOND")

    for events in (alice_first, bob_first, alice_second):
        _assert_completed(events)
    assert len(client.calls) == 3
    # Bob starts from his own state; Alice continues from hers and never sees Bob's.
    assert not client.saw("ALICE_FIRST", call=1)
    assert client.saw("ALICE_FIRST", call=2)
    assert not client.saw("BOB_FIRST", call=2)
    assert client.sessions[0] is not client.sessions[1]
    assert client.sessions[0] is client.sessions[2]


@pytest.mark.parametrize("scope_mode", SCOPE_MODES)
def test_shared_workflow_without_agent_executor_is_not_bound_to_a_scope(scope_mode: Any) -> None:
    @executor(id="responder")
    async def responder(message: Any, ctx: WorkflowContext[Any, Any]) -> None:
        del message
        await ctx.yield_output("Workflow response")

    app = build_app(WorkflowBuilder(start_executor=responder).build(), scope_mode)

    with TestClient(app) as http:
        alice = post_run(http, "alice", "thread-a", "ALICE_ONLY")
        bob = post_run(http, "bob", "thread-b", "BOB_ONLY")

    for events in (alice, bob):
        assert run_error_codes(events) == []
        assert "Workflow response" in assistant_text(events)


# endregion

# region approvals follow the same ownership


@pytest.mark.parametrize("isolation", ["factory", "shared"])
def test_standing_approval_does_not_reach_another_scope(isolation: str) -> None:
    client = RecordingChatClient()
    agent = build_agent(client, standing_approvals=True)
    runner: Any = (
        AgentFrameworkWorkflow(workflow_factory=lambda _thread_id: build_workflow(agent))
        if isolation == "factory"
        else build_workflow(agent)
    )

    with TestClient(build_app(runner, "authorization")) as http:
        first = post_run(http, "alice", "thread-a", f"{INVOKE_PREFIX}ALICE_FIRST")
        (interrupt,) = interrupts(first)
        approved = post_run(http, "alice", "thread-a", resume=always_approve_resume(interrupt))
        # Alice's standing rule skips her next approval prompt.
        repeated = post_run(http, "alice", "thread-a", f"{INVOKE_PREFIX}ALICE_SECOND")
        bob = post_run(http, "bob", "thread-b", f"{INVOKE_PREFIX}BOB_ONLY")

    assert run_error_codes(approved) == []
    assert interrupts(repeated) == []
    assert client.executed == ["ALICE_FIRST", "ALICE_SECOND"]
    if isolation == "factory":
        assert len(interrupts(bob)) == 1
    else:
        _assert_scope_conflict(bob)


# endregion

# region claim_agent_executors


def test_claim_binds_agent_executors_to_the_first_scope() -> None:
    workflow = build_workflow(build_agent(RecordingChatClient()))

    assert claim_agent_executors(workflow, "scope-a")
    assert claim_agent_executors(workflow, "scope-a")
    assert not claim_agent_executors(workflow, "scope-b")


def test_claim_binds_unscoped_runs_to_their_own_owner() -> None:
    workflow = build_workflow(build_agent(RecordingChatClient()))

    assert claim_agent_executors(workflow, None)
    assert claim_agent_executors(workflow, None)
    assert not claim_agent_executors(workflow, "scope-a")


def test_claim_refuses_an_unscoped_run_on_scoped_executors() -> None:
    workflow = build_workflow(build_agent(RecordingChatClient()))

    assert claim_agent_executors(workflow, "scope-a")
    assert not claim_agent_executors(workflow, None)


def test_claim_binds_the_session_of_every_agent_executor() -> None:
    agent = build_agent(RecordingChatClient())
    shared_session = agent.create_session()
    first = build_workflow(agent, session=shared_session)
    second = build_workflow(agent, session=shared_session)

    assert claim_agent_executors(first, "scope-a")
    # New executors that inject the session of a bound executor are refused for another scope.
    assert not claim_agent_executors(second, "scope-b")
    assert claim_agent_executors(second, "scope-a")


def test_claim_allows_executors_of_one_workflow_to_share_a_session() -> None:
    agent = build_agent(RecordingChatClient())
    shared_session = agent.create_session()
    writer = AgentExecutor(agent, id="writer", session=shared_session)
    reviewer = AgentExecutor(agent, id="reviewer", session=shared_session)
    workflow = WorkflowBuilder(start_executor=writer, output_from=[reviewer]).add_edge(writer, reviewer).build()

    assert claim_agent_executors(workflow, "scope-a")
    assert claim_agent_executors(workflow, "scope-a")
    assert not claim_agent_executors(workflow, "scope-b")


def test_claim_covers_agent_executors_inside_nested_workflows() -> None:
    inner = build_workflow(build_agent(RecordingChatClient()))
    outer = WorkflowBuilder(start_executor=WorkflowExecutor(inner, id="inner")).build()

    assert claim_agent_executors(outer, "scope-a")
    assert not claim_agent_executors(inner, "scope-b")
    assert not claim_agent_executors(outer, "scope-b")


def test_claim_covers_workflows_behind_a_wrapped_workflow_agent() -> None:
    inner = build_workflow(build_agent(RecordingChatClient()))
    outer = WorkflowBuilder(start_executor=AgentExecutor(inner.as_agent(), id="outer")).build()

    assert claim_agent_executors(outer, "scope-a")
    assert not claim_agent_executors(inner, "scope-b")


def test_claim_workflow_agent_ignores_agents_that_run_no_workflow() -> None:
    agent = build_agent(RecordingChatClient())

    assert claim_workflow_agent(agent, "scope-a")
    assert claim_workflow_agent(agent, "scope-b")
    assert claim_workflow_agent(agent, None)


def test_claim_workflow_agent_looks_through_a2ui_runners() -> None:
    pytest.importorskip("ag_ui_a2ui_toolkit")
    from agent_framework_ag_ui._a2ui import enable_a2ui

    workflow = build_workflow(build_agent(RecordingChatClient()))
    wrapped = enable_a2ui(enable_a2ui(workflow.as_agent(), object()), object())

    assert claim_workflow_agent(wrapped, "scope-a")
    assert not claim_agent_executors(workflow, "scope-b")
    assert not claim_workflow_agent(wrapped, "scope-b")


def test_claim_is_atomic_across_threads() -> None:
    workflow = build_workflow(build_agent(RecordingChatClient()))

    with ThreadPoolExecutor(max_workers=16) as pool:
        results = list(pool.map(lambda index: claim_agent_executors(workflow, f"scope-{index}"), range(64)))

    assert results.count(True) == 1


def test_claim_does_not_keep_executors_alive() -> None:
    workflow = build_workflow(build_agent(RecordingChatClient()))
    executor_ref = weakref.ref(workflow.get_start_executor())
    assert claim_agent_executors(workflow, "scope-a")

    del workflow
    gc.collect()

    assert executor_ref() is None


# endregion
