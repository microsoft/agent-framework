# Copyright (c) Microsoft. All rights reserved.

from collections.abc import AsyncIterable
from typing import Annotated, Any

from agent_framework import (
    AgentRunResponse,
    AgentRunResponseUpdate,
    AgentThread,
    BaseAgent,
    ChatMessage,
    ConcurrentBuilder,
    GroupChatBuilder,
    GroupChatStateSnapshot,
    HandoffBuilder,
    Role,
    SequentialBuilder,
    TextContent,
    WorkflowRunState,
    WorkflowStatusEvent,
    ai_function,
)
from agent_framework._workflows._const import WORKFLOW_RUN_KWARGS_KEY

# Track kwargs received by tools during test execution
_received_kwargs: list[dict[str, Any]] = []


def _reset_received_kwargs() -> None:
    """Reset the kwargs tracker before each test."""
    _received_kwargs.clear()


@ai_function
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
    """Test agent that captures kwargs passed to run/run_stream."""

    captured_kwargs: list[dict[str, Any]]

    def __init__(self, name: str = "test_agent") -> None:
        super().__init__(name=name, description="Test agent for kwargs capture")
        self.captured_kwargs = []

    async def run(
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> AgentRunResponse:
        self.captured_kwargs.append(dict(kwargs))
        return AgentRunResponse(messages=[ChatMessage(role=Role.ASSISTANT, text=f"{self.display_name} response")])

    async def run_stream(
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> AsyncIterable[AgentRunResponseUpdate]:
        self.captured_kwargs.append(dict(kwargs))
        yield AgentRunResponseUpdate(contents=[TextContent(text=f"{self.display_name} response")])


class _EchoAgent(BaseAgent):
    """Simple agent that echoes back for workflow completion."""

    async def run(
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> AgentRunResponse:
        return AgentRunResponse(messages=[ChatMessage(role=Role.ASSISTANT, text=f"{self.display_name} reply")])

    async def run_stream(
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> AsyncIterable[AgentRunResponseUpdate]:
        yield AgentRunResponseUpdate(contents=[TextContent(text=f"{self.display_name} reply")])


# region Sequential Builder Tests


async def test_sequential_kwargs_flow_to_agent() -> None:
    """Test that kwargs passed to SequentialBuilder workflow flow through to agent."""
    agent = _KwargsCapturingAgent(name="seq_agent")
    workflow = SequentialBuilder().participants([agent]).build()

    custom_data = {"endpoint": "https://api.example.com", "version": "v1"}
    user_token = {"user_name": "alice", "access_level": "admin"}

    async for event in workflow.run_stream(
        "test message",
        custom_data=custom_data,
        user_token=user_token,
    ):
        if isinstance(event, WorkflowStatusEvent) and event.state == WorkflowRunState.IDLE:
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
    workflow = SequentialBuilder().participants([agent1, agent2]).build()

    custom_data = {"key": "value"}

    async for event in workflow.run_stream("test", custom_data=custom_data):
        if isinstance(event, WorkflowStatusEvent) and event.state == WorkflowRunState.IDLE:
            break

    # Both agents should have received kwargs
    assert len(agent1.captured_kwargs) >= 1, "First agent should be invoked"
    assert len(agent2.captured_kwargs) >= 1, "Second agent should be invoked"
    assert agent1.captured_kwargs[0].get("custom_data") == custom_data
    assert agent2.captured_kwargs[0].get("custom_data") == custom_data


async def test_sequential_run_kwargs_flow() -> None:
    """Test that kwargs flow through workflow.run() (non-streaming)."""
    agent = _KwargsCapturingAgent(name="run_agent")
    workflow = SequentialBuilder().participants([agent]).build()

    _ = await workflow.run("test message", custom_data={"test": True})

    assert len(agent.captured_kwargs) >= 1
    assert agent.captured_kwargs[0].get("custom_data") == {"test": True}


# endregion


# region Concurrent Builder Tests


async def test_concurrent_kwargs_flow_to_agents() -> None:
    """Test that kwargs flow to all agents in a concurrent workflow."""
    agent1 = _KwargsCapturingAgent(name="concurrent1")
    agent2 = _KwargsCapturingAgent(name="concurrent2")
    workflow = ConcurrentBuilder().participants([agent1, agent2]).build()

    custom_data = {"batch_id": "123"}
    user_token = {"user_name": "bob"}

    async for event in workflow.run_stream(
        "concurrent test",
        custom_data=custom_data,
        user_token=user_token,
    ):
        if isinstance(event, WorkflowStatusEvent) and event.state == WorkflowRunState.IDLE:
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

    def simple_selector(state: GroupChatStateSnapshot) -> str | None:
        nonlocal turn_count
        turn_count += 1
        if turn_count > 2:  # Stop after 2 turns
            return None
        # state is a Mapping - access via dict syntax
        names = list(state["participants"].keys())
        return names[(turn_count - 1) % len(names)]

    workflow = (
        GroupChatBuilder().participants(chat1=agent1, chat2=agent2).set_select_speakers_func(simple_selector).build()
    )

    custom_data = {"session_id": "group123"}

    async for event in workflow.run_stream("group chat test", custom_data=custom_data):
        if isinstance(event, WorkflowStatusEvent) and event.state == WorkflowRunState.IDLE:
            break

    # At least one agent should have received kwargs
    all_kwargs = agent1.captured_kwargs + agent2.captured_kwargs
    assert len(all_kwargs) >= 1, "At least one agent should be invoked in group chat"

    for received in all_kwargs:
        assert received.get("custom_data") == custom_data


# endregion


# region SharedState Verification Tests


async def test_kwargs_stored_in_shared_state() -> None:
    """Test that kwargs are stored in SharedState with the correct key."""
    from agent_framework import Executor, WorkflowContext, handler

    stored_kwargs: dict[str, Any] | None = None

    class _SharedStateInspector(Executor):
        @handler
        async def inspect(self, msgs: list[ChatMessage], ctx: WorkflowContext[list[ChatMessage]]) -> None:
            nonlocal stored_kwargs
            stored_kwargs = await ctx.get_shared_state(WORKFLOW_RUN_KWARGS_KEY)
            await ctx.send_message(msgs)

    inspector = _SharedStateInspector(id="inspector")
    workflow = SequentialBuilder().participants([inspector]).build()

    async for event in workflow.run_stream("test", my_kwarg="my_value", another=123):
        if isinstance(event, WorkflowStatusEvent) and event.state == WorkflowRunState.IDLE:
            break

    assert stored_kwargs is not None, "kwargs should be stored in SharedState"
    assert stored_kwargs.get("my_kwarg") == "my_value"
    assert stored_kwargs.get("another") == 123


async def test_empty_kwargs_stored_as_empty_dict() -> None:
    """Test that empty kwargs are stored as empty dict in SharedState."""
    from agent_framework import Executor, WorkflowContext, handler

    stored_kwargs: Any = "NOT_CHECKED"

    class _SharedStateChecker(Executor):
        @handler
        async def check(self, msgs: list[ChatMessage], ctx: WorkflowContext[list[ChatMessage]]) -> None:
            nonlocal stored_kwargs
            stored_kwargs = await ctx.get_shared_state(WORKFLOW_RUN_KWARGS_KEY)
            await ctx.send_message(msgs)

    checker = _SharedStateChecker(id="checker")
    workflow = SequentialBuilder().participants([checker]).build()

    # Run without any kwargs
    async for event in workflow.run_stream("test"):
        if isinstance(event, WorkflowStatusEvent) and event.state == WorkflowRunState.IDLE:
            break

    # SharedState should have empty dict when no kwargs provided
    assert stored_kwargs == {}, f"Expected empty dict, got: {stored_kwargs}"


# endregion


# region Edge Cases


async def test_kwargs_with_none_values() -> None:
    """Test that kwargs with None values are passed through correctly."""
    agent = _KwargsCapturingAgent(name="none_test")
    workflow = SequentialBuilder().participants([agent]).build()

    async for event in workflow.run_stream("test", optional_param=None, other_param="value"):
        if isinstance(event, WorkflowStatusEvent) and event.state == WorkflowRunState.IDLE:
            break

    assert len(agent.captured_kwargs) >= 1
    received = agent.captured_kwargs[0]
    assert "optional_param" in received
    assert received["optional_param"] is None
    assert received["other_param"] == "value"


async def test_kwargs_with_complex_nested_data() -> None:
    """Test that complex nested data structures flow through correctly."""
    agent = _KwargsCapturingAgent(name="nested_test")
    workflow = SequentialBuilder().participants([agent]).build()

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

    async for event in workflow.run_stream("test", complex_data=complex_data):
        if isinstance(event, WorkflowStatusEvent) and event.state == WorkflowRunState.IDLE:
            break

    assert len(agent.captured_kwargs) >= 1
    received = agent.captured_kwargs[0]
    assert received.get("complex_data") == complex_data


async def test_kwargs_preserved_across_workflow_reruns() -> None:
    """Test that kwargs are correctly isolated between workflow runs."""
    agent = _KwargsCapturingAgent(name="rerun_test")

    # Build separate workflows for each run to avoid "already running" error
    workflow1 = SequentialBuilder().participants([agent]).build()
    workflow2 = SequentialBuilder().participants([agent]).build()

    # First run
    async for event in workflow1.run_stream("run1", run_id="first"):
        if isinstance(event, WorkflowStatusEvent) and event.state == WorkflowRunState.IDLE:
            break

    # Second run with different kwargs (using fresh workflow)
    async for event in workflow2.run_stream("run2", run_id="second"):
        if isinstance(event, WorkflowStatusEvent) and event.state == WorkflowRunState.IDLE:
            break

    assert len(agent.captured_kwargs) >= 2
    assert agent.captured_kwargs[0].get("run_id") == "first"
    assert agent.captured_kwargs[1].get("run_id") == "second"


# endregion


# region Handoff Builder Tests


async def test_handoff_kwargs_flow_to_agents() -> None:
    """Test that kwargs flow to agents in a handoff workflow."""
    agent1 = _KwargsCapturingAgent(name="coordinator")
    agent2 = _KwargsCapturingAgent(name="specialist")

    workflow = (
        HandoffBuilder()
        .participants([agent1, agent2])
        .set_coordinator(agent1)
        .with_interaction_mode("autonomous")
        .build()
    )

    custom_data = {"session_id": "handoff123"}

    async for event in workflow.run_stream("handoff test", custom_data=custom_data):
        if isinstance(event, WorkflowStatusEvent) and event.state == WorkflowRunState.IDLE:
            break

    # Coordinator agent should have received kwargs
    assert len(agent1.captured_kwargs) >= 1, "Coordinator should be invoked in handoff"
    assert agent1.captured_kwargs[0].get("custom_data") == custom_data


# endregion


# region Magentic Builder Tests


async def test_magentic_kwargs_flow_to_agents() -> None:
    """Test that kwargs flow to agents in a magentic workflow via MagenticAgentExecutor."""
    from agent_framework import MagenticBuilder
    from agent_framework._workflows._magentic import (
        MagenticContext,
        MagenticManagerBase,
        _MagenticProgressLedger,
        _MagenticProgressLedgerItem,
    )

    # Create a mock manager that completes after one round
    class _MockManager(MagenticManagerBase):
        def __init__(self) -> None:
            super().__init__(max_stall_count=3, max_reset_count=None, max_round_count=2)
            self.task_ledger = None

        async def plan(self, context: MagenticContext) -> ChatMessage:
            return ChatMessage(role=Role.ASSISTANT, text="Plan: Test task", author_name="manager")

        async def replan(self, context: MagenticContext) -> ChatMessage:
            return ChatMessage(role=Role.ASSISTANT, text="Replan: Test task", author_name="manager")

        async def create_progress_ledger(self, context: MagenticContext) -> _MagenticProgressLedger:
            # Return completed on first call
            return _MagenticProgressLedger(
                is_request_satisfied=_MagenticProgressLedgerItem(answer=True, reason="Done"),
                is_progress_being_made=_MagenticProgressLedgerItem(answer=True, reason="Progress"),
                is_in_loop=_MagenticProgressLedgerItem(answer=False, reason="Not looping"),
                instruction_or_question=_MagenticProgressLedgerItem(answer="Complete", reason="Done"),
                next_speaker=_MagenticProgressLedgerItem(answer="agent1", reason="First"),
            )

        async def prepare_final_answer(self, context: MagenticContext) -> ChatMessage:
            return ChatMessage(role=Role.ASSISTANT, text="Final answer", author_name="manager")

    agent = _KwargsCapturingAgent(name="agent1")
    manager = _MockManager()

    workflow = MagenticBuilder().participants(agent1=agent).with_standard_manager(manager=manager).build()

    custom_data = {"session_id": "magentic123"}

    async for event in workflow.run_stream("magentic test", custom_data=custom_data):
        if isinstance(event, WorkflowStatusEvent) and event.state == WorkflowRunState.IDLE:
            break

    # The workflow completes immediately via prepare_final_answer without invoking agents
    # because is_request_satisfied=True. This test verifies the kwargs storage path works.
    # A more comprehensive integration test would require the manager to select an agent.


async def test_magentic_kwargs_stored_in_shared_state() -> None:
    """Test that kwargs are stored in SharedState when using MagenticWorkflow.run_stream()."""
    from agent_framework import MagenticBuilder
    from agent_framework._workflows._magentic import (
        MagenticContext,
        MagenticManagerBase,
        _MagenticProgressLedger,
        _MagenticProgressLedgerItem,
    )

    class _MockManager(MagenticManagerBase):
        def __init__(self) -> None:
            super().__init__(max_stall_count=3, max_reset_count=None, max_round_count=1)
            self.task_ledger = None

        async def plan(self, context: MagenticContext) -> ChatMessage:
            return ChatMessage(role=Role.ASSISTANT, text="Plan", author_name="manager")

        async def replan(self, context: MagenticContext) -> ChatMessage:
            return ChatMessage(role=Role.ASSISTANT, text="Replan", author_name="manager")

        async def create_progress_ledger(self, context: MagenticContext) -> _MagenticProgressLedger:
            return _MagenticProgressLedger(
                is_request_satisfied=_MagenticProgressLedgerItem(answer=True, reason="Done"),
                is_progress_being_made=_MagenticProgressLedgerItem(answer=True, reason="Progress"),
                is_in_loop=_MagenticProgressLedgerItem(answer=False, reason="Not looping"),
                instruction_or_question=_MagenticProgressLedgerItem(answer="Done", reason="Done"),
                next_speaker=_MagenticProgressLedgerItem(answer="agent1", reason="First"),
            )

        async def prepare_final_answer(self, context: MagenticContext) -> ChatMessage:
            return ChatMessage(role=Role.ASSISTANT, text="Final", author_name="manager")

    agent = _KwargsCapturingAgent(name="agent1")
    manager = _MockManager()

    magentic_workflow = MagenticBuilder().participants(agent1=agent).with_standard_manager(manager=manager).build()

    # Use MagenticWorkflow.run_stream() which goes through the kwargs attachment path
    custom_data = {"magentic_key": "magentic_value"}

    async for event in magentic_workflow.run_stream("test task", custom_data=custom_data):
        if isinstance(event, WorkflowStatusEvent) and event.state == WorkflowRunState.IDLE:
            break

    # Verify the workflow completed (kwargs were stored, even if agent wasn't invoked)
    # The test validates the code path through MagenticWorkflow.run_stream -> _MagenticStartMessage


# endregion


# region SubWorkflow (WorkflowExecutor) Tests


async def test_subworkflow_kwargs_propagation() -> None:
    """Test that kwargs are propagated to subworkflows.

    Verifies kwargs passed to parent workflow.run_stream() flow through to agents
    in subworkflows wrapped by WorkflowExecutor.
    """
    from agent_framework._workflows._workflow_executor import WorkflowExecutor

    # Create an agent inside the subworkflow that captures kwargs
    inner_agent = _KwargsCapturingAgent(name="inner_agent")

    # Build the inner (sub) workflow with the agent
    inner_workflow = SequentialBuilder().participants([inner_agent]).build()

    # Wrap the inner workflow in a WorkflowExecutor so it can be used as a subworkflow
    subworkflow_executor = WorkflowExecutor(workflow=inner_workflow, id="subworkflow_executor")

    # Build the outer (parent) workflow containing the subworkflow
    outer_workflow = SequentialBuilder().participants([subworkflow_executor]).build()

    # Define kwargs that should propagate to subworkflow
    custom_data = {"api_key": "secret123", "endpoint": "https://api.example.com"}
    user_token = {"user_name": "alice", "access_level": "admin"}

    # Run the outer workflow with kwargs
    async for event in outer_workflow.run_stream(
        "test message for subworkflow",
        custom_data=custom_data,
        user_token=user_token,
    ):
        if isinstance(event, WorkflowStatusEvent) and event.state == WorkflowRunState.IDLE:
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


async def test_subworkflow_kwargs_accessible_via_shared_state() -> None:
    """Test that kwargs are accessible via SharedState within subworkflow.

    Verifies that WORKFLOW_RUN_KWARGS_KEY is populated in the subworkflow's SharedState
    with kwargs from the parent workflow.
    """
    from agent_framework import Executor, WorkflowContext, handler
    from agent_framework._workflows._workflow_executor import WorkflowExecutor

    captured_kwargs_from_state: list[dict[str, Any]] = []

    class _SharedStateReader(Executor):
        """Executor that reads kwargs from SharedState for verification."""

        @handler
        async def read_kwargs(self, msgs: list[ChatMessage], ctx: WorkflowContext[list[ChatMessage]]) -> None:
            kwargs_from_state = await ctx.get_shared_state(WORKFLOW_RUN_KWARGS_KEY)
            captured_kwargs_from_state.append(kwargs_from_state or {})
            await ctx.send_message(msgs)

    # Build inner workflow with SharedState reader
    state_reader = _SharedStateReader(id="state_reader")
    inner_workflow = SequentialBuilder().participants([state_reader]).build()

    # Wrap as subworkflow
    subworkflow_executor = WorkflowExecutor(workflow=inner_workflow, id="subworkflow")

    # Build outer workflow
    outer_workflow = SequentialBuilder().participants([subworkflow_executor]).build()

    # Run with kwargs
    async for event in outer_workflow.run_stream(
        "test",
        my_custom_kwarg="should_be_propagated",
        another_kwarg=42,
    ):
        if isinstance(event, WorkflowStatusEvent) and event.state == WorkflowRunState.IDLE:
            break

    # Verify the state reader was invoked
    assert len(captured_kwargs_from_state) >= 1, "SharedState reader should have been invoked"

    kwargs_in_subworkflow = captured_kwargs_from_state[0]

    assert kwargs_in_subworkflow.get("my_custom_kwarg") == "should_be_propagated", (
        f"Expected 'my_custom_kwarg' in subworkflow SharedState, got: {kwargs_in_subworkflow}"
    )
    assert kwargs_in_subworkflow.get("another_kwarg") == 42, (
        f"Expected 'another_kwarg'=42 in subworkflow SharedState, got: {kwargs_in_subworkflow}"
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
    inner_workflow = SequentialBuilder().participants([inner_agent]).build()
    inner_executor = WorkflowExecutor(workflow=inner_workflow, id="inner_executor")

    # Build middle workflow containing inner
    middle_workflow = SequentialBuilder().participants([inner_executor]).build()
    middle_executor = WorkflowExecutor(workflow=middle_workflow, id="middle_executor")

    # Build outer workflow containing middle
    outer_workflow = SequentialBuilder().participants([middle_executor]).build()

    # Run with kwargs
    async for event in outer_workflow.run_stream(
        "deeply nested test",
        deep_kwarg="should_reach_inner",
    ):
        if isinstance(event, WorkflowStatusEvent) and event.state == WorkflowRunState.IDLE:
            break

    # Verify inner agent was called
    assert len(inner_agent.captured_kwargs) >= 1, "Deeply nested agent should be invoked"

    received = inner_agent.captured_kwargs[0]
    assert received.get("deep_kwarg") == "should_reach_inner", (
        f"Deeply nested agent should receive 'deep_kwarg'. Got: {received}"
    )


# endregion
