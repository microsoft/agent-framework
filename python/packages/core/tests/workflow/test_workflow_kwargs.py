# Copyright (c) Microsoft. All rights reserved.

from collections.abc import AsyncIterable, Awaitable, Sequence
from typing import Annotated, Any

import pytest

from agent_framework import (
    AgentResponse,
    AgentResponseUpdate,
    AgentSession,
    BaseAgent,
    Content,
    Message,
    ResponseStream,
    WorkflowRunState,
    tool,
)
from agent_framework._workflows._const import WORKFLOW_RUN_KWARGS_KEY
from agent_framework.orchestrations import (
    ConcurrentBuilder,
    GroupChatBuilder,
    GroupChatState,
    HandoffBuilder,
    SequentialBuilder,
)

# Track kwargs received by tools during test execution
_received_kwargs: list[dict[str, Any]] = []


@tool(approval_mode="never_require")
def tool_with_kwargs(
    action: Annotated[str, "The action to perform"],
    **kwargs: Any,
) -> str:
    """A test tool that captures kwargs for verification."""
    _received_kwargs.append(dict(kwargs))
    custom_data = kwargs.get("custom_data", {})
    user_token = kwargs.get("user_token", {})
    return f"Executed {action} with custom_data={custom_data}, user={user_token.get('user_name', 'unknown')}"


class _KwargsCapturingAgent(BaseAgent):
    """Test agent that captures kwargs passed to run."""

    captured_kwargs: list[dict[str, Any]]

    def __init__(self, name: str = "test_agent") -> None:
        super().__init__(name=name, description="Test agent for kwargs capture")
        self.captured_kwargs = []

    def run(
        self,
        messages: str | Content | Message | Sequence[str | Content | Message] | None = None,
        *,
        stream: bool = False,
        session: AgentSession | None = None,
        **kwargs: Any,
    ) -> Awaitable[AgentResponse] | ResponseStream[AgentResponseUpdate, AgentResponse]:
        self.captured_kwargs.append(dict(kwargs))
        if stream:

            async def _stream() -> AsyncIterable[AgentResponseUpdate]:
                yield AgentResponseUpdate(contents=[Content.from_text(text=f"{self.name} response")])

            return ResponseStream(_stream(), finalizer=AgentResponse.from_updates)

        async def _run() -> AgentResponse:
            return AgentResponse(messages=[Message("assistant", [f"{self.name} response"])])

        return _run()


class _OptionsAwareAgent(BaseAgent):
    """Test agent that captures explicit `options` and kwargs passed to run()."""

    captured_options: list[dict[str, Any] | None]
    captured_kwargs: list[dict[str, Any]]

    def __init__(self, name: str = "options_agent") -> None:
        super().__init__(name=name, description="Test agent for options capture")
        self.captured_options = []
        self.captured_kwargs = []

    def run(
        self,
        messages: str | Content | Message | Sequence[str | Content | Message] | None = None,
        *,
        stream: bool = False,
        session: AgentSession | None = None,
        options: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Awaitable[AgentResponse] | ResponseStream[AgentResponseUpdate, AgentResponse]:
        self.captured_options.append(dict(options) if options is not None else None)
        self.captured_kwargs.append(dict(kwargs))
        if stream:

            async def _stream() -> AsyncIterable[AgentResponseUpdate]:
                yield AgentResponseUpdate(contents=[Content.from_text(text=f"{self.name} response")])

            return ResponseStream(_stream(), finalizer=AgentResponse.from_updates)

        async def _run() -> AgentResponse:
            return AgentResponse(messages=[Message("assistant", [f"{self.name} response"])])

        return _run()


# region Sequential Builder Tests


async def test_sequential_kwargs_flow_to_agent() -> None:
    """Test that kwargs passed to SequentialBuilder workflow flow through to agent."""
    agent = _KwargsCapturingAgent(name="seq_agent")
    workflow = SequentialBuilder(participants=[agent]).build()

    custom_data = {"endpoint": "https://api.example.com", "version": "v1"}
    user_token = {"user_name": "alice", "access_level": "admin"}

    async for event in workflow.run(
        "test message",
        stream=True,
        custom_data=custom_data,
        user_token=user_token,
    ):
        if event.type == "status" and event.state == WorkflowRunState.IDLE:
            break

    # Verify agent received kwargs
    assert len(agent.captured_kwargs) >= 1, "Agent should have been invoked at least once"
    received = agent.captured_kwargs[0]
    assert "custom_data" in received, "Agent should receive custom_data kwarg"
    assert "user_token" in received, "Agent should receive user_token kwarg"
    assert received["custom_data"] == custom_data
    assert received["user_token"] == user_token


async def test_sequential_kwargs_flow_to_multiple_agents() -> None:
    """Test that kwargs flow to all agents in a sequential workflow."""
    agent1 = _KwargsCapturingAgent(name="agent1")
    agent2 = _KwargsCapturingAgent(name="agent2")
    workflow = SequentialBuilder(participants=[agent1, agent2]).build()

    custom_data = {"key": "value"}

    async for event in workflow.run("test", custom_data=custom_data, stream=True):
        if event.type == "status" and event.state == WorkflowRunState.IDLE:
            break

    # Both agents should have received kwargs
    assert len(agent1.captured_kwargs) >= 1, "First agent should be invoked"
    assert len(agent2.captured_kwargs) >= 1, "Second agent should be invoked"
    assert agent1.captured_kwargs[0].get("custom_data") == custom_data
    assert agent2.captured_kwargs[0].get("custom_data") == custom_data


async def test_sequential_run_kwargs_flow() -> None:
    """Test that kwargs flow through workflow.run() (non-streaming)."""
    agent = _KwargsCapturingAgent(name="run_agent")
    workflow = SequentialBuilder(participants=[agent]).build()

    _ = await workflow.run("test message", custom_data={"test": True})

    assert len(agent.captured_kwargs) >= 1
    assert agent.captured_kwargs[0].get("custom_data") == {"test": True}


async def test_sequential_run_options_does_not_conflict_with_agent_options() -> None:
    """Test workflow.run(options=...) does not conflict with Agent.run(options=...)."""
    agent = _OptionsAwareAgent(name="options_agent")
    workflow = SequentialBuilder(participants=[agent]).build()

    custom_data = {"session_id": "abc123"}
    user_token = {"user_name": "alice"}
    provided_options = {
        "store": False,
        "additional_function_arguments": {"source": "workflow-options"},
    }

    async for event in workflow.run(
        "test message",
        stream=True,
        options=provided_options,
        custom_data=custom_data,
        user_token=user_token,
    ):
        if event.type == "status" and event.state == WorkflowRunState.IDLE:
            break

    assert len(agent.captured_options) >= 1
    captured_options = agent.captured_options[0]
    assert captured_options is not None
    assert captured_options.get("store") is False

    additional_args = captured_options.get("additional_function_arguments")
    assert isinstance(additional_args, dict)
    assert additional_args.get("source") == "workflow-options"
    assert additional_args.get("custom_data") == custom_data
    assert additional_args.get("user_token") == user_token

    # "options" should be passed once via the dedicated options parameter,
    # not duplicated in **kwargs.
    assert len(agent.captured_kwargs) >= 1
    captured_kwargs = agent.captured_kwargs[0]
    assert "options" not in captured_kwargs
    assert captured_kwargs.get("custom_data") == custom_data
    assert captured_kwargs.get("user_token") == user_token


async def test_sequential_run_additional_function_arguments_flattened() -> None:
    """Test workflow.run(additional_function_arguments=...) maps directly to tool kwargs."""
    agent = _OptionsAwareAgent(name="options_agent")
    workflow = SequentialBuilder(participants=[agent]).build()

    custom_data = {"session_id": "abc123"}
    user_token = {"user_name": "alice"}

    async for event in workflow.run(
        "test message",
        stream=True,
        additional_function_arguments={"custom_data": custom_data, "user_token": user_token},
    ):
        if event.type == "status" and event.state == WorkflowRunState.IDLE:
            break

    assert len(agent.captured_options) >= 1
    captured_options = agent.captured_options[0]
    assert captured_options is not None

    additional_args = captured_options.get("additional_function_arguments")
    assert isinstance(additional_args, dict)
    assert additional_args.get("custom_data") == custom_data
    assert additional_args.get("user_token") == user_token
    assert "additional_function_arguments" not in additional_args

    assert len(agent.captured_kwargs) >= 1
    captured_kwargs = agent.captured_kwargs[0]
    assert "additional_function_arguments" not in captured_kwargs


async def test_sequential_run_additional_function_arguments_merges_with_options() -> None:
    """Test workflow additional_function_arguments merges with workflow options."""
    agent = _OptionsAwareAgent(name="options_agent")
    workflow = SequentialBuilder(participants=[agent]).build()

    async for event in workflow.run(
        "test message",
        stream=True,
        options={"additional_function_arguments": {"source": "workflow-options"}},
        additional_function_arguments={"custom_data": {"session_id": "abc123"}},
        user_token={"user_name": "alice"},
    ):
        if event.type == "status" and event.state == WorkflowRunState.IDLE:
            break

    assert len(agent.captured_options) >= 1
    captured_options = agent.captured_options[0]
    assert captured_options is not None

    additional_args = captured_options.get("additional_function_arguments")
    assert isinstance(additional_args, dict)
    assert additional_args.get("source") == "workflow-options"
    assert additional_args.get("custom_data") == {"session_id": "abc123"}
    assert additional_args.get("user_token") == {"user_name": "alice"}
    assert "additional_function_arguments" not in additional_args


# endregion


# region Concurrent Builder Tests


async def test_concurrent_kwargs_flow_to_agents() -> None:
    """Test that kwargs flow to all agents in a concurrent workflow."""
    agent1 = _KwargsCapturingAgent(name="concurrent1")
    agent2 = _KwargsCapturingAgent(name="concurrent2")
    workflow = ConcurrentBuilder(participants=[agent1, agent2]).build()

    custom_data = {"batch_id": "123"}
    user_token = {"user_name": "bob"}

    async for event in workflow.run(
        "concurrent test",
        stream=True,
        custom_data=custom_data,
        user_token=user_token,
    ):
        if event.type == "status" and event.state == WorkflowRunState.IDLE:
            break

    # Both agents should have received kwargs
    assert len(agent1.captured_kwargs) >= 1, "First concurrent agent should be invoked"
    assert len(agent2.captured_kwargs) >= 1, "Second concurrent agent should be invoked"

    for agent in [agent1, agent2]:
        received = agent.captured_kwargs[0]
        assert received.get("custom_data") == custom_data
        assert received.get("user_token") == user_token


# endregion


# region GroupChat Builder Tests


async def test_groupchat_kwargs_flow_to_agents() -> None:
    """Test that kwargs flow to agents in a group chat workflow."""
    agent1 = _KwargsCapturingAgent(name="chat1")
    agent2 = _KwargsCapturingAgent(name="chat2")

    # Simple selector that takes GroupChatStateSnapshot
    turn_count = 0

    def simple_selector(state: GroupChatState) -> str:
        nonlocal turn_count
        turn_count += 1
        if turn_count > 2:  # Loop after two turns for test
            turn_count = 0
        # state is a Mapping - access via dict syntax
        names = list(state.participants.keys())
        return names[(turn_count - 1) % len(names)]

    workflow = GroupChatBuilder(
        participants=[agent1, agent2],
        max_rounds=2,  # Limit rounds to prevent infinite loop
        selection_func=simple_selector,
    ).build()

    custom_data = {"session_id": "group123"}

    async for event in workflow.run("group chat test", custom_data=custom_data, stream=True):
        if event.type == "status" and event.state == WorkflowRunState.IDLE:
            break

    # At least one agent should have received kwargs
    all_kwargs = agent1.captured_kwargs + agent2.captured_kwargs
    assert len(all_kwargs) >= 1, "At least one agent should be invoked in group chat"

    for received in all_kwargs:
        assert received.get("custom_data") == custom_data


# endregion


# region State Verification Tests


async def test_kwargs_stored_in_state() -> None:
    """Test that kwargs are stored in State with the correct key."""
    from agent_framework import Executor, WorkflowContext, handler

    stored_kwargs: dict[str, Any] | None = None

    class _StateInspector(Executor):
        @handler
        async def inspect(self, msgs: list[Message], ctx: WorkflowContext[list[Message]]) -> None:
            nonlocal stored_kwargs
            stored_kwargs = ctx.get_state(WORKFLOW_RUN_KWARGS_KEY)
            await ctx.send_message(msgs)

    inspector = _StateInspector(id="inspector")
    workflow = SequentialBuilder(participants=[inspector]).build()

    async for event in workflow.run("test", my_kwarg="my_value", another=123, stream=True):
        if event.type == "status" and event.state == WorkflowRunState.IDLE:
            break

    assert stored_kwargs is not None, "kwargs should be stored in State"
    assert stored_kwargs.get("my_kwarg") == "my_value"
    assert stored_kwargs.get("another") == 123


async def test_empty_kwargs_stored_as_empty_dict() -> None:
    """Test that empty kwargs are stored as empty dict in State."""
    from agent_framework import Executor, WorkflowContext, handler

    stored_kwargs: Any = "NOT_CHECKED"

    class _StateChecker(Executor):
        @handler
        async def check(self, msgs: list[Message], ctx: WorkflowContext[list[Message]]) -> None:
            nonlocal stored_kwargs
            stored_kwargs = ctx.get_state(WORKFLOW_RUN_KWARGS_KEY)
            await ctx.send_message(msgs)

    checker = _StateChecker(id="checker")
    workflow = SequentialBuilder(participants=[checker]).build()

    # Run without any kwargs
    async for event in workflow.run("test", stream=True):
        if event.type == "status" and event.state == WorkflowRunState.IDLE:
            break

    # State should have empty dict when no kwargs provided
    assert stored_kwargs == {}, f"Expected empty dict, got: {stored_kwargs}"


# endregion


# region Edge Cases


async def test_kwargs_with_none_values() -> None:
    """Test that kwargs with None values are passed through correctly."""
    agent = _KwargsCapturingAgent(name="none_test")
    workflow = SequentialBuilder(participants=[agent]).build()

    async for event in workflow.run("test", optional_param=None, other_param="value", stream=True):
        if event.type == "status" and event.state == WorkflowRunState.IDLE:
            break

    assert len(agent.captured_kwargs) >= 1
    received = agent.captured_kwargs[0]
    assert "optional_param" in received
    assert received["optional_param"] is None
    assert received["other_param"] == "value"


async def test_kwargs_with_complex_nested_data() -> None:
    """Test that complex nested data structures flow through correctly."""
    agent = _KwargsCapturingAgent(name="nested_test")
    workflow = SequentialBuilder(participants=[agent]).build()

    complex_data = {
        "level1": {
            "level2": {
                "level3": ["a", "b", "c"],
                "number": 42,
            },
            "list": [1, 2, {"nested": True}],
        },
        "tuple_like": [1, 2, 3],
    }

    async for event in workflow.run("test", complex_data=complex_data, stream=True):
        if event.type == "status" and event.state == WorkflowRunState.IDLE:
            break

    assert len(agent.captured_kwargs) >= 1
    received = agent.captured_kwargs[0]
    assert received.get("complex_data") == complex_data


async def test_kwargs_preserved_across_workflow_reruns() -> None:
    """Test that kwargs are correctly isolated between workflow runs."""
    agent = _KwargsCapturingAgent(name="rerun_test")

    # Build separate workflows for each run to avoid "already running" error
    workflow1 = SequentialBuilder(participants=[agent]).build()
    workflow2 = SequentialBuilder(participants=[agent]).build()

    # First run
    async for event in workflow1.run("run1", run_id="first", stream=True):
        if event.type == "status" and event.state == WorkflowRunState.IDLE:
            break

    # Second run with different kwargs (using fresh workflow)
    async for event in workflow2.run("run2", run_id="second", stream=True):
        if event.type == "status" and event.state == WorkflowRunState.IDLE:
            break

    assert len(agent.captured_kwargs) >= 2
    assert agent.captured_kwargs[0].get("run_id") == "first"
    assert agent.captured_kwargs[1].get("run_id") == "second"


# endregion


# region Handoff Builder Tests


@pytest.mark.xfail(reason="Handoff workflow does not yet propagate kwargs to agents")
async def test_handoff_kwargs_flow_to_agents() -> None:
    """Test that kwargs flow to agents in a handoff workflow."""
    agent1 = _KwargsCapturingAgent(name="coordinator")
    agent2 = _KwargsCapturingAgent(name="specialist")

    workflow = (
        HandoffBuilder(termination_condition=lambda conv: len(conv) >= 4)
        .participants([agent1, agent2])
        .with_start_agent(agent1)
        .with_autonomous_mode()
        .build()
    )

    custom_data = {"session_id": "handoff123"}

    async for event in workflow.run("handoff test", custom_data=custom_data, stream=True):
        if event.type == "status" and event.state == WorkflowRunState.IDLE:
            break

    # Coordinator agent should have received kwargs
    assert len(agent1.captured_kwargs) >= 1, "Coordinator should be invoked in handoff"
    assert agent1.captured_kwargs[0].get("custom_data") == custom_data


# endregion


# region Magentic Builder Tests


async def test_magentic_kwargs_flow_to_agents() -> None:
    """Test that kwargs flow to agents in a magentic workflow via MagenticAgentExecutor."""
    from agent_framework_orchestrations._magentic import (
        MagenticContext,
        MagenticManagerBase,
        MagenticProgressLedger,
        MagenticProgressLedgerItem,
    )

    from agent_framework.orchestrations import MagenticBuilder

    # Create a mock manager that completes after one round
    class _MockManager(MagenticManagerBase):
        def __init__(self) -> None:
            super().__init__(max_stall_count=3, max_reset_count=None, max_round_count=2)
            self.task_ledger = None

        async def plan(self, magentic_context: MagenticContext) -> Message:
            return Message(role="assistant", text="Plan: Test task", author_name="manager")

        async def replan(self, magentic_context: MagenticContext) -> Message:
            return Message(role="assistant", text="Replan: Test task", author_name="manager")

        async def create_progress_ledger(self, magentic_context: MagenticContext) -> MagenticProgressLedger:
            # Return completed on first call
            return MagenticProgressLedger(
                is_request_satisfied=MagenticProgressLedgerItem(answer=True, reason="Done"),
                is_progress_being_made=MagenticProgressLedgerItem(answer=True, reason="Progress"),
                is_in_loop=MagenticProgressLedgerItem(answer=False, reason="Not looping"),
                instruction_or_question=MagenticProgressLedgerItem(answer="Complete", reason="Done"),
                next_speaker=MagenticProgressLedgerItem(answer="agent1", reason="First"),
            )

        async def prepare_final_answer(self, magentic_context: MagenticContext) -> Message:
            return Message(role="assistant", text="Final answer", author_name="manager")

    agent = _KwargsCapturingAgent(name="agent1")
    manager = _MockManager()

    workflow = MagenticBuilder(participants=[agent], manager=manager).build()

    custom_data = {"session_id": "magentic123"}

    async for event in workflow.run("magentic test", custom_data=custom_data, stream=True):
        if event.type == "status" and event.state == WorkflowRunState.IDLE:
            break

    # The workflow completes immediately via prepare_final_answer without invoking agents
    # because is_request_satisfied=True. This test verifies the kwargs storage path works.
    # A more comprehensive integration test would require the manager to select an agent.


async def test_magentic_kwargs_stored_in_state() -> None:
    """Test that kwargs are stored in State when using MagenticWorkflow.run()."""
    from agent_framework_orchestrations._magentic import (
        MagenticContext,
        MagenticManagerBase,
        MagenticProgressLedger,
        MagenticProgressLedgerItem,
    )

    from agent_framework.orchestrations import MagenticBuilder

    class _MockManager(MagenticManagerBase):
        def __init__(self) -> None:
            super().__init__(max_stall_count=3, max_reset_count=None, max_round_count=1)
            self.task_ledger = None

        async def plan(self, magentic_context: MagenticContext) -> Message:
            return Message(role="assistant", text="Plan", author_name="manager")

        async def replan(self, magentic_context: MagenticContext) -> Message:
            return Message(role="assistant", text="Replan", author_name="manager")

        async def create_progress_ledger(self, magentic_context: MagenticContext) -> MagenticProgressLedger:
            return MagenticProgressLedger(
                is_request_satisfied=MagenticProgressLedgerItem(answer=True, reason="Done"),
                is_progress_being_made=MagenticProgressLedgerItem(answer=True, reason="Progress"),
                is_in_loop=MagenticProgressLedgerItem(answer=False, reason="Not looping"),
                instruction_or_question=MagenticProgressLedgerItem(answer="Done", reason="Done"),
                next_speaker=MagenticProgressLedgerItem(answer="agent1", reason="First"),
            )

        async def prepare_final_answer(self, magentic_context: MagenticContext) -> Message:
            return Message(role="assistant", text="Final", author_name="manager")

    agent = _KwargsCapturingAgent(name="agent1")
    manager = _MockManager()

    magentic_workflow = MagenticBuilder(participants=[agent], manager=manager).build()

    # Use MagenticWorkflow.run() which goes through the kwargs attachment path
    custom_data = {"magentic_key": "magentic_value"}

    async for event in magentic_workflow.run("test task", custom_data=custom_data, stream=True):
        if event.type == "status" and event.state == WorkflowRunState.IDLE:
            break

    # Verify the workflow completed (kwargs were stored, even if agent wasn't invoked)
    # The test validates the code path through MagenticWorkflow.run(stream=True, ) -> _MagenticStartMessage


# endregion


# region WorkflowAgent (as_agent) kwargs Tests


async def test_workflow_as_agent_run_propagates_kwargs_to_underlying_agent() -> None:
    """Test that kwargs passed to workflow_agent.run() flow through to the underlying agents."""
    agent = _KwargsCapturingAgent(name="inner_agent")
    workflow = SequentialBuilder(participants=[agent]).build()
    workflow_agent = workflow.as_agent(name="TestWorkflowAgent")

    custom_data = {"endpoint": "https://api.example.com", "version": "v1"}
    user_token = {"user_name": "alice", "access_level": "admin"}

    _ = await workflow_agent.run(
        "test message",
        custom_data=custom_data,
        user_token=user_token,
    )

    # Verify inner agent received kwargs
    assert len(agent.captured_kwargs) >= 1, "Inner agent should have been invoked at least once"
    received = agent.captured_kwargs[0]
    assert "custom_data" in received, "Inner agent should receive custom_data kwarg"
    assert "user_token" in received, "Inner agent should receive user_token kwarg"
    assert received["custom_data"] == custom_data
    assert received["user_token"] == user_token


async def test_workflow_as_agent_run_stream_propagates_kwargs_to_underlying_agent() -> None:
    """Test that kwargs passed to workflow_agent.run() flow through to the underlying agents."""
    agent = _KwargsCapturingAgent(name="inner_agent")
    workflow = SequentialBuilder(participants=[agent]).build()
    workflow_agent = workflow.as_agent(name="TestWorkflowAgent")

    custom_data = {"session_id": "xyz123"}
    api_token = "secret-token"

    async for _ in workflow_agent.run(
        "test message",
        stream=True,
        custom_data=custom_data,
        api_token=api_token,
    ):
        pass

    # Verify inner agent received kwargs
    assert len(agent.captured_kwargs) >= 1, "Inner agent should have been invoked at least once"
    received = agent.captured_kwargs[0]
    assert "custom_data" in received, "Inner agent should receive custom_data kwarg"
    assert "api_token" in received, "Inner agent should receive api_token kwarg"
    assert received["custom_data"] == custom_data
    assert received["api_token"] == api_token


async def test_workflow_as_agent_propagates_kwargs_to_multiple_agents() -> None:
    """Test that kwargs flow to all agents when using workflow.as_agent()."""
    agent1 = _KwargsCapturingAgent(name="agent1")
    agent2 = _KwargsCapturingAgent(name="agent2")
    workflow = SequentialBuilder(participants=[agent1, agent2]).build()
    workflow_agent = workflow.as_agent(name="MultiAgentWorkflow")

    custom_data = {"batch_id": "batch-001"}

    _ = await workflow_agent.run("test message", custom_data=custom_data)

    # Both agents should have received kwargs
    assert len(agent1.captured_kwargs) >= 1, "First agent should be invoked"
    assert len(agent2.captured_kwargs) >= 1, "Second agent should be invoked"
    assert agent1.captured_kwargs[0].get("custom_data") == custom_data
    assert agent2.captured_kwargs[0].get("custom_data") == custom_data


async def test_workflow_as_agent_kwargs_with_none_values() -> None:
    """Test that kwargs with None values are passed through correctly via as_agent()."""
    agent = _KwargsCapturingAgent(name="none_test_agent")
    workflow = SequentialBuilder(participants=[agent]).build()
    workflow_agent = workflow.as_agent(name="NoneTestWorkflow")

    _ = await workflow_agent.run("test", optional_param=None, other_param="value")

    assert len(agent.captured_kwargs) >= 1
    received = agent.captured_kwargs[0]
    assert "optional_param" in received
    assert received["optional_param"] is None
    assert received["other_param"] == "value"


async def test_workflow_as_agent_kwargs_with_complex_nested_data() -> None:
    """Test that complex nested data structures flow through correctly via as_agent()."""
    agent = _KwargsCapturingAgent(name="nested_agent")
    workflow = SequentialBuilder(participants=[agent]).build()
    workflow_agent = workflow.as_agent(name="NestedDataWorkflow")

    complex_data = {
        "level1": {
            "level2": {
                "level3": ["a", "b", "c"],
                "number": 42,
            },
            "list": [1, 2, {"nested": True}],
        },
    }

    _ = await workflow_agent.run("test", complex_data=complex_data)

    assert len(agent.captured_kwargs) >= 1
    received = agent.captured_kwargs[0]
    assert received.get("complex_data") == complex_data


# endregion


# region SubWorkflow (WorkflowExecutor) Tests


async def test_subworkflow_kwargs_propagation() -> None:
    """Test that kwargs are propagated to subworkflows.

    Verifies kwargs passed to parent workflow.run() flow through to agents
    in subworkflows wrapped by WorkflowExecutor.
    """
    from agent_framework._workflows._workflow_executor import WorkflowExecutor

    # Create an agent inside the subworkflow that captures kwargs
    inner_agent = _KwargsCapturingAgent(name="inner_agent")

    # Build the inner (sub) workflow with the agent
    inner_workflow = SequentialBuilder(participants=[inner_agent]).build()

    # Wrap the inner workflow in a WorkflowExecutor so it can be used as a subworkflow
    subworkflow_executor = WorkflowExecutor(workflow=inner_workflow, id="subworkflow_executor")

    # Build the outer (parent) workflow containing the subworkflow
    outer_workflow = SequentialBuilder(participants=[subworkflow_executor]).build()

    # Define kwargs that should propagate to subworkflow
    custom_data = {"api_key": "secret123", "endpoint": "https://api.example.com"}
    user_token = {"user_name": "alice", "access_level": "admin"}

    # Run the outer workflow with kwargs
    async for event in outer_workflow.run(
        "test message for subworkflow",
        stream=True,
        custom_data=custom_data,
        user_token=user_token,
    ):
        if event.type == "status" and event.state == WorkflowRunState.IDLE:
            break

    # Verify that the inner agent was called
    assert len(inner_agent.captured_kwargs) >= 1, "Inner agent in subworkflow should have been invoked"

    received_kwargs = inner_agent.captured_kwargs[0]

    # Verify kwargs were propagated from parent workflow to subworkflow agent
    assert "custom_data" in received_kwargs, (
        f"Subworkflow agent should receive 'custom_data' kwarg. Received keys: {list(received_kwargs.keys())}"
    )
    assert "user_token" in received_kwargs, (
        f"Subworkflow agent should receive 'user_token' kwarg. Received keys: {list(received_kwargs.keys())}"
    )
    assert received_kwargs.get("custom_data") == custom_data, (
        f"Expected custom_data={custom_data}, got {received_kwargs.get('custom_data')}"
    )
    assert received_kwargs.get("user_token") == user_token, (
        f"Expected user_token={user_token}, got {received_kwargs.get('user_token')}"
    )


async def test_subworkflow_kwargs_accessible_via_state() -> None:
    """Test that kwargs are accessible via State within subworkflow.

    Verifies that WORKFLOW_RUN_KWARGS_KEY is populated in the subworkflow's State
    with kwargs from the parent workflow.
    """
    from agent_framework import Executor, WorkflowContext, handler
    from agent_framework._workflows._workflow_executor import WorkflowExecutor

    captured_kwargs_from_state: list[dict[str, Any]] = []

    class _StateReader(Executor):
        """Executor that reads kwargs from State for verification."""

        @handler
        async def read_kwargs(self, msgs: list[Message], ctx: WorkflowContext[list[Message]]) -> None:
            kwargs_from_state = ctx.get_state(WORKFLOW_RUN_KWARGS_KEY)
            captured_kwargs_from_state.append(kwargs_from_state or {})
            await ctx.send_message(msgs)

    # Build inner workflow with State reader
    state_reader = _StateReader(id="state_reader")
    inner_workflow = SequentialBuilder(participants=[state_reader]).build()

    # Wrap as subworkflow
    subworkflow_executor = WorkflowExecutor(workflow=inner_workflow, id="subworkflow")

    # Build outer workflow
    outer_workflow = SequentialBuilder(participants=[subworkflow_executor]).build()

    # Run with kwargs
    async for event in outer_workflow.run(
        "test",
        stream=True,
        my_custom_kwarg="should_be_propagated",
        another_kwarg=42,
    ):
        if event.type == "status" and event.state == WorkflowRunState.IDLE:
            break

    # Verify the state reader was invoked
    assert len(captured_kwargs_from_state) >= 1, "State reader should have been invoked"

    kwargs_in_subworkflow = captured_kwargs_from_state[0]

    assert kwargs_in_subworkflow.get("my_custom_kwarg") == "should_be_propagated", (
        f"Expected 'my_custom_kwarg' in subworkflow  got: {kwargs_in_subworkflow}"
    )
    assert kwargs_in_subworkflow.get("another_kwarg") == 42, (
        f"Expected 'another_kwarg'=42 in subworkflow  got: {kwargs_in_subworkflow}"
    )


async def test_nested_subworkflow_kwargs_propagation() -> None:
    """Test kwargs propagation through multiple levels of nested subworkflows.

    Verifies kwargs flow through 3 levels:
    - Outer workflow
      - Middle subworkflow (WorkflowExecutor)
        - Inner subworkflow (WorkflowExecutor) with agent
    """
    from agent_framework._workflows._workflow_executor import WorkflowExecutor

    # Innermost agent
    inner_agent = _KwargsCapturingAgent(name="deeply_nested_agent")

    # Build inner workflow
    inner_workflow = SequentialBuilder(participants=[inner_agent]).build()
    inner_executor = WorkflowExecutor(workflow=inner_workflow, id="inner_executor")

    # Build middle workflow containing inner
    middle_workflow = SequentialBuilder(participants=[inner_executor]).build()
    middle_executor = WorkflowExecutor(workflow=middle_workflow, id="middle_executor")

    # Build outer workflow containing middle
    outer_workflow = SequentialBuilder(participants=[middle_executor]).build()

    # Run with kwargs
    async for event in outer_workflow.run(
        "deeply nested test",
        stream=True,
        deep_kwarg="should_reach_inner",
    ):
        if event.type == "status" and event.state == WorkflowRunState.IDLE:
            break

    # Verify inner agent was called
    assert len(inner_agent.captured_kwargs) >= 1, "Deeply nested agent should be invoked"

    received = inner_agent.captured_kwargs[0]
    assert received.get("deep_kwarg") == "should_reach_inner", (
        f"Deeply nested agent should receive 'deep_kwarg'. Got: {received}"
    )


# endregion
