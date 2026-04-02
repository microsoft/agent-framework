# Copyright (c) Microsoft. All rights reserved.

from collections.abc import AsyncIterable, Awaitable
from typing import TYPE_CHECKING, Any, Literal, overload

import pytest

from agent_framework import (
    AgentResponse,
    AgentResponseUpdate,
    AgentRunInputs,
    AgentSession,
    BaseAgent,
    Content,
    Message,
    ResponseStream,
    WorkflowRunState,
)
from agent_framework._workflows._const import WORKFLOW_RUN_KWARGS_KEY
from agent_framework.orchestrations import (
    ConcurrentBuilder,
    GroupChatBuilder,
    GroupChatState,
    HandoffBuilder,
    SequentialBuilder,
)

if TYPE_CHECKING:
    from _pytest.logging import LogCaptureFixture


# Track kwargs received by tools during test execution
class _KwargsCapturingAgent(BaseAgent):
    """Test agent that captures kwargs passed to run."""

    captured_kwargs: list[dict[str, Any]]

    def __init__(self, name: str = "test_agent") -> None:
        super().__init__(name=name, description="Test agent for kwargs capture")
        self.captured_kwargs = []

    @overload
    def run(
        self,
        messages: AgentRunInputs | None = ...,
        *,
        stream: Literal[False] = ...,
        session: AgentSession | None = ...,
        **kwargs: Any,
    ) -> Awaitable[AgentResponse[Any]]: ...
    @overload
    def run(
        self,
        messages: AgentRunInputs | None = ...,
        *,
        stream: Literal[True],
        session: AgentSession | None = ...,
        **kwargs: Any,
    ) -> ResponseStream[AgentResponseUpdate, AgentResponse[Any]]: ...

    def run(
        self,
        messages: AgentRunInputs | None = None,
        *,
        stream: bool = False,
        session: AgentSession | None = None,
        **kwargs: Any,
    ) -> Awaitable[AgentResponse[Any]] | ResponseStream[AgentResponseUpdate, AgentResponse[Any]]:
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
    """Test that function_invocation_kwargs passed to SequentialBuilder workflow flow through to agent."""
    agent = _KwargsCapturingAgent(name="seq_agent")
    workflow = SequentialBuilder(participants=[agent]).build()

    fi_kwargs = {"endpoint": "https://api.example.com", "version": "v1"}

    async for event in workflow.run(
        "test message",
        stream=True,
        function_invocation_kwargs=fi_kwargs,
    ):
        if event.type == "status" and event.state == WorkflowRunState.IDLE:
            break

    # Verify agent received kwargs
    assert len(agent.captured_kwargs) >= 1, "Agent should have been invoked at least once"
    received = agent.captured_kwargs[0]
    assert received.get("function_invocation_kwargs") == fi_kwargs


async def test_sequential_kwargs_flow_to_multiple_agents() -> None:
    """Test that function_invocation_kwargs flow to all agents in a sequential workflow."""
    agent1 = _KwargsCapturingAgent(name="agent1")
    agent2 = _KwargsCapturingAgent(name="agent2")
    workflow = SequentialBuilder(participants=[agent1, agent2]).build()

    fi_kwargs = {"key": "value"}

    async for event in workflow.run("test", function_invocation_kwargs=fi_kwargs, stream=True):
        if event.type == "status" and event.state == WorkflowRunState.IDLE:
            break

    # Both agents should have received kwargs
    assert len(agent1.captured_kwargs) >= 1, "First agent should be invoked"
    assert len(agent2.captured_kwargs) >= 1, "Second agent should be invoked"
    assert agent1.captured_kwargs[0].get("function_invocation_kwargs") == fi_kwargs
    assert agent2.captured_kwargs[0].get("function_invocation_kwargs") == fi_kwargs


async def test_sequential_run_kwargs_flow() -> None:
    """Test that function_invocation_kwargs flow through workflow.run() (non-streaming)."""
    agent = _KwargsCapturingAgent(name="run_agent")
    workflow = SequentialBuilder(participants=[agent]).build()

    _ = await workflow.run("test message", function_invocation_kwargs={"test": True})

    assert len(agent.captured_kwargs) >= 1
    assert agent.captured_kwargs[0].get("function_invocation_kwargs") == {"test": True}


async def test_sequential_run_non_streaming_kwargs_flow() -> None:
    """Test workflow.run(function_invocation_kwargs=...) non-streaming path."""
    agent = _KwargsCapturingAgent(name="options_agent")
    workflow = SequentialBuilder(participants=[agent]).build()

    fi_kwargs = {"session_id": "abc123"}

    _ = await workflow.run(
        "test message",
        function_invocation_kwargs=fi_kwargs,
    )

    assert len(agent.captured_kwargs) >= 1
    assert agent.captured_kwargs[0].get("function_invocation_kwargs") == fi_kwargs


# endregion


# region Concurrent Builder Tests


async def test_concurrent_kwargs_flow_to_agents() -> None:
    """Test that function_invocation_kwargs flow to all agents in a concurrent workflow."""
    agent1 = _KwargsCapturingAgent(name="concurrent1")
    agent2 = _KwargsCapturingAgent(name="concurrent2")
    workflow = ConcurrentBuilder(participants=[agent1, agent2]).build()

    fi_kwargs = {"batch_id": "123"}

    async for event in workflow.run(
        "concurrent test",
        stream=True,
        function_invocation_kwargs=fi_kwargs,
    ):
        if event.type == "status" and event.state == WorkflowRunState.IDLE:
            break

    # Both agents should have received kwargs
    assert len(agent1.captured_kwargs) >= 1, "First concurrent agent should be invoked"
    assert len(agent2.captured_kwargs) >= 1, "Second concurrent agent should be invoked"

    for agent in [agent1, agent2]:
        received = agent.captured_kwargs[0]
        assert received.get("function_invocation_kwargs") == fi_kwargs


# endregion


# region GroupChat Builder Tests


async def test_groupchat_kwargs_flow_to_agents() -> None:
    """Test that function_invocation_kwargs flow to agents in a group chat workflow."""
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

    fi_kwargs = {"session_id": "group123"}

    async for event in workflow.run("group chat test", function_invocation_kwargs=fi_kwargs, stream=True):
        if event.type == "status" and event.state == WorkflowRunState.IDLE:
            break

    # At least one agent should have received kwargs
    all_kwargs = agent1.captured_kwargs + agent2.captured_kwargs
    assert len(all_kwargs) >= 1, "At least one agent should be invoked in group chat"

    for received in all_kwargs:
        assert received.get("function_invocation_kwargs") == fi_kwargs


# endregion


# region State Verification Tests


async def test_kwargs_stored_in_state() -> None:
    """Test that function_invocation_kwargs are stored in State with the correct key."""
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

    async for event in workflow.run("test", function_invocation_kwargs={"my_kwarg": "my_value"}, stream=True):
        if event.type == "status" and event.state == WorkflowRunState.IDLE:
            break

    assert stored_kwargs is not None, "kwargs should be stored in State"
    assert "function_invocation_kwargs" in stored_kwargs


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


async def test_kwargs_with_complex_nested_data() -> None:
    """Test that complex nested data structures flow through correctly via function_invocation_kwargs."""
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

    async for event in workflow.run("test", function_invocation_kwargs=complex_data, stream=True):
        if event.type == "status" and event.state == WorkflowRunState.IDLE:
            break

    assert len(agent.captured_kwargs) >= 1
    received = agent.captured_kwargs[0]
    assert received.get("function_invocation_kwargs") == complex_data


async def test_kwargs_preserved_on_response_continuation() -> None:
    """Test that function_invocation_kwargs are preserved when continuing a paused workflow with run(responses=...).

    Regression test for #4293: kwargs were overwritten to {} on continuation calls.
    """

    class _ApprovalCapturingAgent(BaseAgent):
        """Agent that pauses for approval on first call and captures kwargs on every call."""

        captured_kwargs: list[dict[str, Any]]
        _asked: bool

        def __init__(self) -> None:
            super().__init__(name="approval_agent", description="Test agent")
            self.captured_kwargs = []
            self._asked = False

        @overload
        def run(
            self,
            messages: AgentRunInputs | None = ...,
            *,
            stream: Literal[False] = ...,
            session: AgentSession | None = ...,
            **kwargs: Any,
        ) -> Awaitable[AgentResponse[Any]]: ...
        @overload
        def run(
            self,
            messages: AgentRunInputs | None = ...,
            *,
            stream: Literal[True],
            session: AgentSession | None = ...,
            **kwargs: Any,
        ) -> ResponseStream[AgentResponseUpdate, AgentResponse[Any]]: ...

        def run(
            self,
            messages: AgentRunInputs | None = None,
            *,
            stream: bool = False,
            session: AgentSession | None = None,
            **kwargs: Any,
        ) -> Awaitable[AgentResponse[Any]] | ResponseStream[AgentResponseUpdate, AgentResponse[Any]]:
            self.captured_kwargs.append(dict(kwargs))
            if not self._asked:
                self._asked = True

                async def _pause() -> AgentResponse:
                    call = Content.from_function_call(call_id="c1", name="do_thing", arguments="{}")
                    req = Content.from_function_approval_request(id="r1", function_call=call)
                    return AgentResponse(messages=[Message("assistant", [req])])

                return _pause()

            async def _done() -> AgentResponse:
                return AgentResponse(messages=[Message("assistant", ["done"])])

            return _done()

    from agent_framework import WorkflowBuilder

    agent = _ApprovalCapturingAgent()
    workflow = WorkflowBuilder(start_executor=agent, output_executors=[agent]).build()

    # Initial run with function_invocation_kwargs — workflow should pause for approval
    fi_kwargs = {"token": "abc"}
    result = await workflow.run("go", function_invocation_kwargs=fi_kwargs)
    request_events = result.get_request_info_events()
    assert len(request_events) == 1

    # Continue with responses only — no new kwargs
    approval = request_events[0]
    await workflow.run(responses={approval.request_id: approval.data.to_function_approval_response(True)})

    # Both calls should have received the original function_invocation_kwargs
    assert len(agent.captured_kwargs) == 2
    assert agent.captured_kwargs[0].get("function_invocation_kwargs") == fi_kwargs
    assert agent.captured_kwargs[1].get("function_invocation_kwargs") == fi_kwargs, (
        f"kwargs should be preserved on continuation, got: {agent.captured_kwargs[1]}"
    )


async def test_kwargs_reset_context_stores_empty_dict() -> None:
    """Test that reset_context=True with no kwargs stores an empty dict.

    This exercises the `elif reset_context` branch that ensures WORKFLOW_RUN_KWARGS_KEY
    is always populated after a fresh run, even when no kwargs are provided.
    """
    agent = _KwargsCapturingAgent(name="reset_ctx_test")

    workflow = SequentialBuilder(participants=[agent]).build()

    # Run with no kwargs and reset_context=True (the default for a fresh run)
    async for event in workflow.run("test", stream=True):
        if event.type == "status" and event.state == WorkflowRunState.IDLE:
            break

    assert len(agent.captured_kwargs) >= 1
    received = agent.captured_kwargs[0]
    assert received.get("function_invocation_kwargs") is None
    assert received.get("client_kwargs") is None


# endregion


# region Handoff Builder Tests


@pytest.mark.xfail(reason="Handoff workflow does not yet propagate kwargs to agents")
async def test_handoff_kwargs_flow_to_agents() -> None:
    """Test that function_invocation_kwargs flow to agents in a handoff workflow."""
    agent1 = _KwargsCapturingAgent(name="coordinator")
    agent2 = _KwargsCapturingAgent(name="specialist")

    workflow = (
        HandoffBuilder(termination_condition=lambda conv: len(conv) >= 4)
        .participants([agent1, agent2])  # type: ignore[list-item]
        .with_start_agent(agent1)  # type: ignore[arg-type]
        .with_autonomous_mode()
        .build()
    )

    fi_kwargs = {"session_id": "handoff123"}

    async for event in workflow.run("handoff test", function_invocation_kwargs=fi_kwargs, stream=True):
        if event.type == "status" and event.state == WorkflowRunState.IDLE:
            break

    # Coordinator agent should have received kwargs
    assert len(agent1.captured_kwargs) >= 1, "Coordinator should be invoked in handoff"
    assert agent1.captured_kwargs[0].get("function_invocation_kwargs") == fi_kwargs


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
            return Message(role="assistant", contents=["Plan: Test task"], author_name="manager")

        async def replan(self, magentic_context: MagenticContext) -> Message:
            return Message(role="assistant", contents=["Replan: Test task"], author_name="manager")

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
            return Message(role="assistant", contents=["Final answer"], author_name="manager")

    agent = _KwargsCapturingAgent(name="agent1")
    manager = _MockManager()

    workflow = MagenticBuilder(participants=[agent], manager=manager).build()

    custom_data = {"session_id": "magentic123"}

    async for event in workflow.run("magentic test", function_invocation_kwargs=custom_data, stream=True):
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
            return Message(role="assistant", contents=["Plan"], author_name="manager")

        async def replan(self, magentic_context: MagenticContext) -> Message:
            return Message(role="assistant", contents=["Replan"], author_name="manager")

        async def create_progress_ledger(self, magentic_context: MagenticContext) -> MagenticProgressLedger:
            return MagenticProgressLedger(
                is_request_satisfied=MagenticProgressLedgerItem(answer=True, reason="Done"),
                is_progress_being_made=MagenticProgressLedgerItem(answer=True, reason="Progress"),
                is_in_loop=MagenticProgressLedgerItem(answer=False, reason="Not looping"),
                instruction_or_question=MagenticProgressLedgerItem(answer="Done", reason="Done"),
                next_speaker=MagenticProgressLedgerItem(answer="agent1", reason="First"),
            )

        async def prepare_final_answer(self, magentic_context: MagenticContext) -> Message:
            return Message(role="assistant", contents=["Final"], author_name="manager")

    agent = _KwargsCapturingAgent(name="agent1")
    manager = _MockManager()

    magentic_workflow = MagenticBuilder(participants=[agent], manager=manager).build()

    # Use MagenticWorkflow.run() which goes through the kwargs attachment path
    custom_data = {"magentic_key": "magentic_value"}

    async for event in magentic_workflow.run("test task", function_invocation_kwargs=custom_data, stream=True):
        if event.type == "status" and event.state == WorkflowRunState.IDLE:
            break

    # Verify the workflow completed (kwargs were stored, even if agent wasn't invoked)
    # The test validates the code path through MagenticWorkflow.run(stream=True, ) -> _MagenticStartMessage


# endregion


# region WorkflowAgent (as_agent) kwargs Tests


async def test_workflow_as_agent_run_propagates_kwargs_to_underlying_agent() -> None:
    """Test that function_invocation_kwargs passed to workflow_agent.run() flow through to the underlying agents."""
    agent = _KwargsCapturingAgent(name="inner_agent")
    workflow = SequentialBuilder(participants=[agent]).build()
    workflow_agent = workflow.as_agent(name="TestWorkflowAgent")

    fi_kwargs = {"endpoint": "https://api.example.com", "version": "v1"}

    _ = await workflow_agent.run(
        "test message",
        function_invocation_kwargs=fi_kwargs,
    )

    # Verify inner agent received kwargs
    assert len(agent.captured_kwargs) >= 1, "Inner agent should have been invoked at least once"
    received = agent.captured_kwargs[0]
    assert received.get("function_invocation_kwargs") == fi_kwargs


async def test_workflow_as_agent_run_stream_propagates_kwargs_to_underlying_agent() -> None:
    """Test that function_invocation_kwargs passed to workflow_agent.run(stream=True) flow through."""
    agent = _KwargsCapturingAgent(name="inner_agent")
    workflow = SequentialBuilder(participants=[agent]).build()
    workflow_agent = workflow.as_agent(name="TestWorkflowAgent")

    fi_kwargs = {"session_id": "xyz123"}

    async for _ in workflow_agent.run(
        "test message",
        stream=True,
        function_invocation_kwargs=fi_kwargs,
    ):
        pass

    # Verify inner agent received kwargs
    assert len(agent.captured_kwargs) >= 1, "Inner agent should have been invoked at least once"
    received = agent.captured_kwargs[0]
    assert received.get("function_invocation_kwargs") == fi_kwargs


async def test_workflow_as_agent_propagates_kwargs_to_multiple_agents() -> None:
    """Test that function_invocation_kwargs flow to all agents when using workflow.as_agent()."""
    agent1 = _KwargsCapturingAgent(name="agent1")
    agent2 = _KwargsCapturingAgent(name="agent2")
    workflow = SequentialBuilder(participants=[agent1, agent2]).build()
    workflow_agent = workflow.as_agent(name="MultiAgentWorkflow")

    fi_kwargs = {"batch_id": "batch-001"}

    _ = await workflow_agent.run("test message", function_invocation_kwargs=fi_kwargs)

    # Both agents should have received kwargs
    assert len(agent1.captured_kwargs) >= 1, "First agent should be invoked"
    assert len(agent2.captured_kwargs) >= 1, "Second agent should be invoked"
    assert agent1.captured_kwargs[0].get("function_invocation_kwargs") == fi_kwargs
    assert agent2.captured_kwargs[0].get("function_invocation_kwargs") == fi_kwargs


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

    _ = await workflow_agent.run("test", function_invocation_kwargs=complex_data)

    assert len(agent.captured_kwargs) >= 1
    received = agent.captured_kwargs[0]
    assert received.get("function_invocation_kwargs") == complex_data


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
    fi_kwargs = {"api_key": "secret123", "endpoint": "https://api.example.com"}

    # Run the outer workflow with kwargs
    async for event in outer_workflow.run(
        "test message for subworkflow",
        stream=True,
        function_invocation_kwargs=fi_kwargs,
    ):
        if event.type == "status" and event.state == WorkflowRunState.IDLE:
            break

    # Verify that the inner agent was called
    assert len(inner_agent.captured_kwargs) >= 1, "Inner agent in subworkflow should have been invoked"

    received_kwargs = inner_agent.captured_kwargs[0]

    # Verify kwargs were propagated from parent workflow to subworkflow agent
    assert received_kwargs.get("function_invocation_kwargs") == fi_kwargs, (
        f"Expected function_invocation_kwargs={fi_kwargs}, got {received_kwargs.get('function_invocation_kwargs')}"
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
    fi_kwargs = {"my_custom_kwarg": "should_be_propagated", "another_kwarg": 42}
    async for event in outer_workflow.run(
        "test",
        stream=True,
        function_invocation_kwargs=fi_kwargs,
    ):
        if event.type == "status" and event.state == WorkflowRunState.IDLE:
            break

    # Verify the state reader was invoked
    assert len(captured_kwargs_from_state) >= 1, "State reader should have been invoked"

    kwargs_in_subworkflow = captured_kwargs_from_state[0]

    assert "function_invocation_kwargs" in kwargs_in_subworkflow, (
        f"Expected 'function_invocation_kwargs' in subworkflow state, got: {kwargs_in_subworkflow}"
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
        function_invocation_kwargs={"deep_kwarg": "should_reach_inner"},
    ):
        if event.type == "status" and event.state == WorkflowRunState.IDLE:
            break

    # Verify inner agent was called
    assert len(inner_agent.captured_kwargs) >= 1, "Deeply nested agent should be invoked"

    received = inner_agent.captured_kwargs[0]
    assert received.get("function_invocation_kwargs") == {"deep_kwarg": "should_reach_inner"}, (
        f"Deeply nested agent should receive 'deep_kwarg'. Got: {received}"
    )


# endregion


# region Per-Executor Invocation Kwargs Tests


async def test_function_and_client_kwargs_together() -> None:
    """Both function_invocation_kwargs and client_kwargs can be provided in the same call."""
    agent1 = _KwargsCapturingAgent(name="agent1")
    agent2 = _KwargsCapturingAgent(name="agent2")
    workflow = SequentialBuilder(participants=[agent1, agent2]).build()

    fi_kwargs = {"tool_param": "tool_value"}
    ci_kwargs = {"temperature": 0.7}

    async for event in workflow.run(
        "test",
        stream=True,
        function_invocation_kwargs=fi_kwargs,
        client_kwargs=ci_kwargs,
    ):
        if event.type == "status" and event.state == WorkflowRunState.IDLE:
            break

    # Both agents should receive both kwargs
    for agent in [agent1, agent2]:
        assert len(agent.captured_kwargs) >= 1
        assert agent.captured_kwargs[0].get("function_invocation_kwargs") == fi_kwargs
        assert agent.captured_kwargs[0].get("client_kwargs") == ci_kwargs


async def test_global_function_invocation_kwargs_flow_to_all_agents() -> None:
    """Global function_invocation_kwargs should be received by all agents in a sequential workflow."""
    agent1 = _KwargsCapturingAgent(name="agent1")
    agent2 = _KwargsCapturingAgent(name="agent2")
    workflow = SequentialBuilder(participants=[agent1, agent2]).build()

    fi_kwargs = {"tool_param": "shared_value"}

    async for event in workflow.run(
        "test",
        stream=True,
        function_invocation_kwargs=fi_kwargs,
    ):
        if event.type == "status" and event.state == WorkflowRunState.IDLE:
            break

    # Both agents should receive function_invocation_kwargs
    assert len(agent1.captured_kwargs) >= 1
    assert agent1.captured_kwargs[0].get("function_invocation_kwargs") == fi_kwargs
    assert len(agent2.captured_kwargs) >= 1
    assert agent2.captured_kwargs[0].get("function_invocation_kwargs") == fi_kwargs


async def test_per_executor_function_invocation_kwargs_routes_to_correct_agent() -> None:
    """Per-executor function_invocation_kwargs should only be received by the targeted agent."""
    agent1 = _KwargsCapturingAgent(name="agent1")
    agent2 = _KwargsCapturingAgent(name="agent2")
    workflow = SequentialBuilder(participants=[agent1, agent2]).build()

    # Per-executor: keys match agent names (which are used as executor IDs)
    fi_kwargs = {
        "agent1": {"tool_param": "value_for_agent1"},
        "agent2": {"tool_param": "value_for_agent2"},
    }

    async for event in workflow.run(
        "test",
        stream=True,
        function_invocation_kwargs=fi_kwargs,
    ):
        if event.type == "status" and event.state == WorkflowRunState.IDLE:
            break

    # Each agent should receive only its own kwargs
    assert len(agent1.captured_kwargs) >= 1
    assert agent1.captured_kwargs[0].get("function_invocation_kwargs") == {"tool_param": "value_for_agent1"}
    assert len(agent2.captured_kwargs) >= 1
    assert agent2.captured_kwargs[0].get("function_invocation_kwargs") == {"tool_param": "value_for_agent2"}


async def test_per_executor_kwargs_unmatched_agent_gets_none() -> None:
    """An agent not targeted in per-executor kwargs should receive None for that kwarg."""
    agent1 = _KwargsCapturingAgent(name="agent1")
    agent2 = _KwargsCapturingAgent(name="agent2")
    workflow = SequentialBuilder(participants=[agent1, agent2]).build()

    # Only agent1 is targeted
    fi_kwargs = {"agent1": {"tool_param": "only_for_agent1"}}

    async for event in workflow.run(
        "test",
        stream=True,
        function_invocation_kwargs=fi_kwargs,
    ):
        if event.type == "status" and event.state == WorkflowRunState.IDLE:
            break

    assert len(agent1.captured_kwargs) >= 1
    assert agent1.captured_kwargs[0].get("function_invocation_kwargs") == {"tool_param": "only_for_agent1"}
    assert len(agent2.captured_kwargs) >= 1
    assert agent2.captured_kwargs[0].get("function_invocation_kwargs") is None


async def test_global_client_kwargs_flow_to_all_agents() -> None:
    """Global client_kwargs should be received by all agents."""
    agent1 = _KwargsCapturingAgent(name="agent1")
    agent2 = _KwargsCapturingAgent(name="agent2")
    workflow = SequentialBuilder(participants=[agent1, agent2]).build()

    ci_kwargs = {"temperature": 0.5}

    async for event in workflow.run(
        "test",
        stream=True,
        client_kwargs=ci_kwargs,
    ):
        if event.type == "status" and event.state == WorkflowRunState.IDLE:
            break

    assert len(agent1.captured_kwargs) >= 1
    assert agent1.captured_kwargs[0].get("client_kwargs") == ci_kwargs
    assert len(agent2.captured_kwargs) >= 1
    assert agent2.captured_kwargs[0].get("client_kwargs") == ci_kwargs


async def test_per_executor_client_kwargs_routes_correctly() -> None:
    """Per-executor client_kwargs should only be received by the targeted agent."""
    agent1 = _KwargsCapturingAgent(name="agent1")
    agent2 = _KwargsCapturingAgent(name="agent2")
    workflow = SequentialBuilder(participants=[agent1, agent2]).build()

    ci_kwargs = {
        "agent1": {"temperature": 0.1},
        "agent2": {"temperature": 0.9},
    }

    async for event in workflow.run(
        "test",
        stream=True,
        client_kwargs=ci_kwargs,
    ):
        if event.type == "status" and event.state == WorkflowRunState.IDLE:
            break

    assert len(agent1.captured_kwargs) >= 1
    assert agent1.captured_kwargs[0].get("client_kwargs") == {"temperature": 0.1}
    assert len(agent2.captured_kwargs) >= 1
    assert agent2.captured_kwargs[0].get("client_kwargs") == {"temperature": 0.9}


async def test_resolve_invocation_kwargs_logs_per_executor(caplog: "LogCaptureFixture") -> None:
    """Workflow._resolve_invocation_kwargs logs info when per-executor format is detected."""
    import logging

    agent = _KwargsCapturingAgent(name="agent1")
    workflow = SequentialBuilder(participants=[agent]).build()

    with caplog.at_level(logging.INFO):
        async for event in workflow.run(
            "test",
            stream=True,
            function_invocation_kwargs={"agent1": {"key": "val"}},
        ):
            if event.type == "status" and event.state == WorkflowRunState.IDLE:
                break

    per_executor_logs = [r for r in caplog.records if "per-executor" in r.message.lower()]
    assert len(per_executor_logs) >= 1


async def test_resolve_invocation_kwargs_logs_global(caplog: "LogCaptureFixture") -> None:
    """Workflow._resolve_invocation_kwargs logs info when global format is detected."""
    import logging

    agent = _KwargsCapturingAgent(name="agent1")
    workflow = SequentialBuilder(participants=[agent]).build()

    with caplog.at_level(logging.INFO):
        async for event in workflow.run(
            "test",
            stream=True,
            function_invocation_kwargs={"tool_key": "tool_val"},
        ):
            if event.type == "status" and event.state == WorkflowRunState.IDLE:
                break

    global_logs = [r for r in caplog.records if "global kwargs" in r.message.lower()]
    assert len(global_logs) >= 1


async def test_empty_function_invocation_kwargs_clears_previous() -> None:
    """Passing function_invocation_kwargs={} should clear previously stored kwargs on a new run."""
    agent = _KwargsCapturingAgent(name="clearing_agent")
    workflow = SequentialBuilder(participants=[agent]).build()

    # First run: provide kwargs
    await workflow.run(
        "first",
        function_invocation_kwargs={"key": "value"},
    )

    assert len(agent.captured_kwargs) >= 1
    assert agent.captured_kwargs[0].get("function_invocation_kwargs") == {"key": "value"}

    # Second run: pass empty dict to explicitly clear
    await workflow.run(
        "second",
        function_invocation_kwargs={},
    )

    # Agent should receive None because the empty dict resolves to an empty
    # __global__ entry which is treated as "no kwargs" for each executor.
    assert len(agent.captured_kwargs) >= 2
    assert agent.captured_kwargs[-1].get("function_invocation_kwargs") == {}


async def test_empty_client_kwargs_clears_previous() -> None:
    """Passing client_kwargs={} should clear previously stored kwargs on a new run."""
    agent = _KwargsCapturingAgent(name="clearing_agent")
    workflow = SequentialBuilder(participants=[agent]).build()

    # First run: provide kwargs
    await workflow.run(
        "first",
        client_kwargs={"temperature": 0.5},
    )

    assert len(agent.captured_kwargs) >= 1
    assert agent.captured_kwargs[0].get("client_kwargs") == {"temperature": 0.5}

    # Second run: pass empty dict to explicitly clear
    await workflow.run(
        "second",
        client_kwargs={},
    )

    assert len(agent.captured_kwargs) >= 2
    assert agent.captured_kwargs[-1].get("client_kwargs") == {}


# endregion
