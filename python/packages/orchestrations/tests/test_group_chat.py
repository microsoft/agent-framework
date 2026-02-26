# Copyright (c) Microsoft. All rights reserved.

from collections.abc import AsyncIterable, Awaitable, Callable, Sequence
from typing import Any, cast

import pytest
from agent_framework import (
    Agent,
    AgentExecutorResponse,
    AgentResponse,
    AgentResponseUpdate,
    AgentSession,
    BaseAgent,
    ChatResponse,
    ChatResponseUpdate,
    Content,
    Message,
    WorkflowEvent,
    WorkflowRunState,
)
from agent_framework._workflows._checkpoint import InMemoryCheckpointStorage
from agent_framework.orchestrations import (
    AgentRequestInfoResponse,
    BaseGroupChatOrchestrator,
    GroupChatBuilder,
    GroupChatState,
    MagenticContext,
    MagenticManagerBase,
    MagenticProgressLedger,
    MagenticProgressLedgerItem,
)


class StubAgent(BaseAgent):
    def __init__(self, agent_name: str, reply_text: str, **kwargs: Any) -> None:
        super().__init__(name=agent_name, description=f"Stub agent {agent_name}", **kwargs)
        self._reply_text = reply_text

    def run(  # type: ignore[override]
        self,
        messages: str | Content | Message | Sequence[str | Content | Message] | None = None,
        *,
        stream: bool = False,
        session: AgentSession | None = None,
        **kwargs: Any,
    ) -> Awaitable[AgentResponse] | AsyncIterable[AgentResponseUpdate]:
        if stream:
            return self._run_stream_impl()
        return self._run_impl()

    async def _run_impl(self) -> AgentResponse:
        response = Message(role="assistant", text=self._reply_text, author_name=self.name)
        return AgentResponse(messages=[response])

    async def _run_stream_impl(self) -> AsyncIterable[AgentResponseUpdate]:
        yield AgentResponseUpdate(
            contents=[Content.from_text(text=self._reply_text)], role="assistant", author_name=self.name
        )


class MockChatClient:
    """Mock chat client that raises NotImplementedError for all methods."""

    additional_properties: dict[str, Any]

    async def get_response(
        self, messages: Any, stream: bool = False, **kwargs: Any
    ) -> ChatResponse | AsyncIterable[ChatResponseUpdate]:
        raise NotImplementedError


class StubManagerAgent(Agent):
    def __init__(self) -> None:
        super().__init__(client=MockChatClient(), name="manager_agent", description="Stub manager")
        self._call_count = 0

    async def run(
        self,
        messages: str | Content | Message | Sequence[str | Content | Message] | None = None,
        *,
        session: AgentSession | None = None,
        **kwargs: Any,
    ) -> AgentResponse:
        if self._call_count == 0:
            self._call_count += 1
            # First call: select the agent (using AgentOrchestrationOutput format)
            payload = {"terminate": False, "reason": "Selecting agent", "next_speaker": "agent", "final_message": None}
            return AgentResponse(
                messages=[
                    Message(
                        role="assistant",
                        text=(
                            '{"terminate": false, "reason": "Selecting agent", '
                            '"next_speaker": "agent", "final_message": null}'
                        ),
                        author_name=self.name,
                    )
                ],
                value=payload,
            )

        # Second call: terminate
        payload = {
            "terminate": True,
            "reason": "Task complete",
            "next_speaker": None,
            "final_message": "agent manager final",
        }
        return AgentResponse(
            messages=[
                Message(
                    role="assistant",
                    text=(
                        '{"terminate": true, "reason": "Task complete", '
                        '"next_speaker": null, "final_message": "agent manager final"}'
                    ),
                    author_name=self.name,
                )
            ],
            value=payload,
        )


class ConcatenatedJsonManagerAgent(Agent):
    """Manager agent that emits concatenated JSON in a single assistant message."""

    def __init__(self) -> None:
        super().__init__(client=MockChatClient(), name="concat_manager", description="Concatenated JSON manager")
        self._call_count = 0

    async def run(
        self,
        messages: str | Content | Message | Sequence[str | Content | Message] | None = None,
        *,
        session: AgentSession | None = None,
        **kwargs: Any,
    ) -> AgentResponse:
        if self._call_count == 0:
            self._call_count += 1
            return AgentResponse(
                messages=[
                    Message(
                        role="assistant",
                        text=(
                            '{"terminate": false, "reason": "invalid candidate", '
                            '"next_speaker": "unknown", "final_message": null} '
                            '{"terminate": false, "reason": "pick known participant", '
                            '"next_speaker": "agent", "final_message": null}'
                        ),
                        author_name=self.name,
                    )
                ]
            )

        return AgentResponse(
            messages=[
                Message(
                    role="assistant",
                    text=(
                        '{"terminate": true, "reason": "Task complete", '
                        '"next_speaker": null, "final_message": "concatenated manager final"}'
                    ),
                    author_name=self.name,
                )
            ]
        )


def make_sequence_selector() -> Callable[[GroupChatState], str]:
    state_counter = {"value": 0}

    def _selector(state: GroupChatState) -> str:
        participants = list(state.participants.keys())
        step = state_counter["value"]
        state_counter["value"] = step + 1
        if step == 0:
            return participants[0]
        if step == 1 and len(participants) > 1:
            return participants[1]
        # Return first participant to continue (will be limited by max_rounds in tests)
        return participants[0]

    return _selector


class StubMagenticManager(MagenticManagerBase):
    def __init__(self) -> None:
        super().__init__(max_stall_count=3, max_round_count=5)
        self._round = 0

    async def plan(self, magentic_context: MagenticContext) -> Message:
        return Message(role="assistant", text="plan", author_name="magentic_manager")

    async def replan(self, magentic_context: MagenticContext) -> Message:
        return await self.plan(magentic_context)

    async def create_progress_ledger(self, magentic_context: MagenticContext) -> MagenticProgressLedger:
        participants = list(magentic_context.participant_descriptions.keys())
        target = participants[0] if participants else "agent"
        if self._round == 0:
            self._round += 1
            return MagenticProgressLedger(
                is_request_satisfied=MagenticProgressLedgerItem(reason="", answer=False),
                is_in_loop=MagenticProgressLedgerItem(reason="", answer=False),
                is_progress_being_made=MagenticProgressLedgerItem(reason="", answer=True),
                next_speaker=MagenticProgressLedgerItem(reason="", answer=target),
                instruction_or_question=MagenticProgressLedgerItem(reason="", answer="respond"),
            )
        return MagenticProgressLedger(
            is_request_satisfied=MagenticProgressLedgerItem(reason="", answer=True),
            is_in_loop=MagenticProgressLedgerItem(reason="", answer=False),
            is_progress_being_made=MagenticProgressLedgerItem(reason="", answer=True),
            next_speaker=MagenticProgressLedgerItem(reason="", answer=target),
            instruction_or_question=MagenticProgressLedgerItem(reason="", answer=""),
        )

    async def prepare_final_answer(self, magentic_context: MagenticContext) -> Message:
        return Message(role="assistant", text="final", author_name="magentic_manager")


async def test_group_chat_builder_basic_flow() -> None:
    selector = make_sequence_selector()
    alpha = StubAgent("alpha", "ack from alpha")
    beta = StubAgent("beta", "ack from beta")

    workflow = GroupChatBuilder(
        participants=[alpha, beta],
        max_rounds=2,  # Limit rounds to prevent infinite loop
        selection_func=selector,
        orchestrator_name="manager",
    ).build()

    outputs: list[list[Message]] = []
    async for event in workflow.run("coordinate task", stream=True):
        if event.type == "output":
            data = event.data
            if isinstance(data, list):
                outputs.append(cast(list[Message], data))

    assert len(outputs) == 1
    assert len(outputs[0]) >= 1
    # Check that both agents contributed
    authors = {msg.author_name for msg in outputs[0] if msg.author_name in ["alpha", "beta"]}
    assert len(authors) == 2


async def test_group_chat_as_agent_accepts_conversation() -> None:
    selector = make_sequence_selector()
    alpha = StubAgent("alpha", "ack from alpha")
    beta = StubAgent("beta", "ack from beta")

    workflow = GroupChatBuilder(
        participants=[alpha, beta],
        max_rounds=2,  # Limit rounds to prevent infinite loop
        selection_func=selector,
        orchestrator_name="manager",
    ).build()

    agent = workflow.as_agent(name="group-chat-agent")
    conversation = [
        Message(role="user", text="kickoff", author_name="user"),
        Message(role="assistant", text="noted", author_name="alpha"),
    ]
    response = await agent.run(conversation)

    assert response.messages, "Expected agent conversation output"


async def test_agent_manager_handles_concatenated_json_output() -> None:
    manager = ConcatenatedJsonManagerAgent()
    worker = StubAgent("agent", "worker response")

    workflow = GroupChatBuilder(
        participants=[worker],
        orchestrator_agent=manager,
    ).build()

    outputs: list[list[Message]] = []
    async for event in workflow.run("coordinate task", stream=True):
        if event.type == "output":
            data = event.data
            if isinstance(data, list):
                outputs.append(cast(list[Message], data))

    assert outputs
    conversation = outputs[-1]
    assert any(msg.author_name == "agent" and msg.text == "worker response" for msg in conversation)
    assert conversation[-1].author_name == manager.name
    assert conversation[-1].text == "concatenated manager final"


# Comprehensive tests for group chat functionality


class TestGroupChatBuilder:
    """Tests for GroupChatBuilder validation and configuration."""

    def test_build_without_manager_raises_error(self) -> None:
        """Test that building without a manager raises ValueError."""
        agent = StubAgent("test", "response")

        builder = GroupChatBuilder(participants=[agent])

        with pytest.raises(
            ValueError,
            match=r"No orchestrator has been configured\.",
        ):
            builder.build()

    def test_build_without_participants_raises_error(self) -> None:
        """Test that constructing with empty participants raises ValueError."""
        with pytest.raises(ValueError):
            GroupChatBuilder(participants=[])

    def test_duplicate_manager_configuration_raises_error(self) -> None:
        """Test that configuring multiple orchestrator options raises ValueError."""
        agent = StubAgent("test", "response")

        def selector(state: GroupChatState) -> str:
            return "agent"

        with pytest.raises(
            ValueError,
            match=r"Exactly one of",
        ):
            GroupChatBuilder(participants=[agent], selection_func=selector, orchestrator_agent=StubManagerAgent())

    def test_empty_participants_raises_error(self) -> None:
        """Test that empty participants list raises ValueError."""
        with pytest.raises(ValueError, match="participants cannot be empty"):
            GroupChatBuilder(participants=[])

    def test_duplicate_participant_names_raises_error(self) -> None:
        """Test that duplicate participant names raise ValueError."""
        agent1 = StubAgent("test", "response1")
        agent2 = StubAgent("test", "response2")

        with pytest.raises(ValueError, match="Duplicate participant name 'test'"):
            GroupChatBuilder(participants=[agent1, agent2])

    def test_agent_without_name_raises_error(self) -> None:
        """Test that agent without name attribute raises ValueError."""

        class AgentWithoutName(BaseAgent):
            def __init__(self) -> None:
                super().__init__(name="", description="test")

            def run(
                self, messages: Any = None, *, stream: bool = False, session: Any = None, **kwargs: Any
            ) -> AgentResponse | AsyncIterable[AgentResponseUpdate]:
                if stream:

                    async def _stream() -> AsyncIterable[AgentResponseUpdate]:
                        yield AgentResponseUpdate(contents=[])

                    return _stream()
                return self._run_impl()

            async def _run_impl(self) -> AgentResponse:
                return AgentResponse(messages=[])

        agent = AgentWithoutName()

        with pytest.raises(ValueError, match="SupportsAgentRun participants must have a non-empty name"):
            GroupChatBuilder(participants=[agent])

    def test_empty_participant_name_raises_error(self) -> None:
        """Test that empty participant name raises ValueError."""
        agent = StubAgent("", "response")  # Agent with empty name

        with pytest.raises(ValueError, match="SupportsAgentRun participants must have a non-empty name"):
            GroupChatBuilder(participants=[agent])


class TestGroupChatWorkflow:
    """Tests for GroupChat workflow functionality."""

    async def test_max_rounds_enforcement(self) -> None:
        """Test that max_rounds properly limits conversation rounds."""
        call_count = {"value": 0}

        def selector(state: GroupChatState) -> str:
            call_count["value"] += 1
            # Always return the agent name to try to continue indefinitely
            return "agent"

        agent = StubAgent("agent", "response")

        workflow = GroupChatBuilder(
            participants=[agent],
            max_rounds=2,  # Limit to 2 rounds
            selection_func=selector,
        ).build()

        outputs: list[list[Message]] = []
        async for event in workflow.run("test task", stream=True):
            if event.type == "output":
                data = event.data
                if isinstance(data, list):
                    outputs.append(cast(list[Message], data))

        # Should have terminated due to max_rounds, expect at least one output
        assert len(outputs) >= 1
        # The final message in the conversation should be about round limit
        conversation = outputs[-1]
        assert len(conversation) >= 1
        final_output = conversation[-1]
        assert "maximum number of rounds" in final_output.text.lower()

    async def test_termination_condition_halts_conversation(self) -> None:
        """Test that a custom termination condition stops the workflow."""

        def selector(state: GroupChatState) -> str:
            return "agent"

        def termination_condition(conversation: list[Message]) -> bool:
            replies = [msg for msg in conversation if msg.role == "assistant" and msg.author_name == "agent"]
            return len(replies) >= 2

        agent = StubAgent("agent", "response")

        workflow = GroupChatBuilder(
            participants=[agent],
            termination_condition=termination_condition,
            selection_func=selector,
        ).build()

        outputs: list[list[Message]] = []
        async for event in workflow.run("test task", stream=True):
            if event.type == "output":
                data = event.data
                if isinstance(data, list):
                    outputs.append(cast(list[Message], data))

        assert outputs, "Expected termination to yield output"
        conversation = outputs[-1]
        agent_replies = [msg for msg in conversation if msg.author_name == "agent" and msg.role == "assistant"]
        assert len(agent_replies) == 2
        final_output = conversation[-1]
        # The orchestrator uses its ID as author_name by default
        assert "termination condition" in final_output.text.lower()

    async def test_termination_condition_agent_manager_finalizes(self) -> None:
        """Test that termination condition with agent orchestrator produces default termination message."""
        manager = StubManagerAgent()
        worker = StubAgent("agent", "response")

        workflow = GroupChatBuilder(
            participants=[worker],
            termination_condition=lambda conv: any(msg.author_name == "agent" for msg in conv),
            orchestrator_agent=manager,
        ).build()

        outputs: list[list[Message]] = []
        async for event in workflow.run("test task", stream=True):
            if event.type == "output":
                data = event.data
                if isinstance(data, list):
                    outputs.append(cast(list[Message], data))

        assert outputs, "Expected termination to yield output"
        conversation = outputs[-1]
        assert conversation[-1].text == BaseGroupChatOrchestrator.TERMINATION_CONDITION_MET_MESSAGE
        assert conversation[-1].author_name == manager.name

    async def test_unknown_participant_error(self) -> None:
        """Test that unknown participant selection raises error."""

        def selector(state: GroupChatState) -> str:
            return "unknown_agent"  # Return non-existent participant

        agent = StubAgent("agent", "response")

        workflow = GroupChatBuilder(participants=[agent], selection_func=selector).build()

        with pytest.raises(RuntimeError, match="Selection function returned unknown participant 'unknown_agent'"):
            async for _ in workflow.run("test task", stream=True):
                pass


class TestCheckpointing:
    """Tests for checkpointing functionality."""

    async def test_workflow_with_checkpointing(self) -> None:
        """Test that workflow works with checkpointing enabled."""

        def selector(state: GroupChatState) -> str:
            return "agent"

        agent = StubAgent("agent", "response")
        storage = InMemoryCheckpointStorage()

        workflow = GroupChatBuilder(
            participants=[agent],
            max_rounds=1,
            checkpoint_storage=storage,
            selection_func=selector,
        ).build()

        outputs: list[list[Message]] = []
        async for event in workflow.run("test task", stream=True):
            if event.type == "output":
                data = event.data
                if isinstance(data, list):
                    outputs.append(cast(list[Message], data))

        assert len(outputs) == 1  # Should complete normally


class TestConversationHandling:
    """Tests for different conversation input types."""

    async def test_handle_empty_conversation_raises_error(self) -> None:
        """Test that empty conversation list raises ValueError."""

        def selector(state: GroupChatState) -> str:
            return "agent"

        agent = StubAgent("agent", "response")

        workflow = GroupChatBuilder(participants=[agent], max_rounds=1, selection_func=selector).build()

        with pytest.raises(ValueError, match="At least one Message is required to start the group chat workflow."):
            async for _ in workflow.run([], stream=True):
                pass

    async def test_handle_string_input(self) -> None:
        """Test handling string input creates proper Message."""

        def selector(state: GroupChatState) -> str:
            # Verify the conversation has the user message
            assert len(state.conversation) > 0
            assert state.conversation[0].role == "user"
            assert state.conversation[0].text == "test string"
            return "agent"

        agent = StubAgent("agent", "response")

        workflow = GroupChatBuilder(participants=[agent], max_rounds=1, selection_func=selector).build()

        outputs: list[list[Message]] = []
        async for event in workflow.run("test string", stream=True):
            if event.type == "output":
                data = event.data
                if isinstance(data, list):
                    outputs.append(cast(list[Message], data))

        assert len(outputs) == 1

    async def test_handle_chat_message_input(self) -> None:
        """Test handling Message input directly."""
        task_message = Message(role="user", text="test message")

        def selector(state: GroupChatState) -> str:
            # Verify the task message was preserved in conversation
            assert len(state.conversation) > 0
            assert state.conversation[0] == task_message
            return "agent"

        agent = StubAgent("agent", "response")

        workflow = GroupChatBuilder(participants=[agent], max_rounds=1, selection_func=selector).build()

        outputs: list[list[Message]] = []
        async for event in workflow.run(task_message, stream=True):
            if event.type == "output":
                data = event.data
                if isinstance(data, list):
                    outputs.append(cast(list[Message], data))

        assert len(outputs) == 1

    async def test_handle_conversation_list_input(self) -> None:
        """Test handling conversation list preserves context."""
        conversation = [
            Message(role="system", text="system message"),
            Message(role="user", text="user message"),
        ]

        def selector(state: GroupChatState) -> str:
            # Verify conversation context is preserved
            assert len(state.conversation) >= 2
            assert state.conversation[-1].text == "user message"
            return "agent"

        agent = StubAgent("agent", "response")

        workflow = GroupChatBuilder(participants=[agent], max_rounds=1, selection_func=selector).build()

        outputs: list[list[Message]] = []
        async for event in workflow.run(conversation, stream=True):
            if event.type == "output":
                data = event.data
                if isinstance(data, list):
                    outputs.append(cast(list[Message], data))

        assert len(outputs) == 1


class TestRoundLimitEnforcement:
    """Tests for round limit checking functionality."""

    async def test_round_limit_in_apply_directive(self) -> None:
        """Test round limit enforcement."""
        rounds_called = {"count": 0}

        def selector(state: GroupChatState) -> str:
            rounds_called["count"] += 1
            # Keep trying to select agent to test limit enforcement
            return "agent"

        agent = StubAgent("agent", "response")

        workflow = GroupChatBuilder(
            participants=[agent],
            max_rounds=1,  # Very low limit
            selection_func=selector,
        ).build()

        outputs: list[list[Message]] = []
        async for event in workflow.run("test", stream=True):
            if event.type == "output":
                data = event.data
                if isinstance(data, list):
                    outputs.append(cast(list[Message], data))

        # Should have at least one output (the round limit message)
        assert len(outputs) >= 1
        # The last message in the conversation should be about round limit
        conversation = outputs[-1]
        assert len(conversation) >= 1
        final_output = conversation[-1]
        assert "maximum number of rounds" in final_output.text.lower()

    async def test_round_limit_in_ingest_participant_message(self) -> None:
        """Test round limit enforcement after participant response."""
        responses_received = {"count": 0}

        def selector(state: GroupChatState) -> str:
            responses_received["count"] += 1
            if responses_received["count"] == 1:
                return "agent"  # First call selects agent
            return "agent"  # Try to continue, but should hit limit

        agent = StubAgent("agent", "response from agent")

        workflow = GroupChatBuilder(
            participants=[agent],
            max_rounds=1,  # Hit limit after first response
            selection_func=selector,
        ).build()

        outputs: list[list[Message]] = []
        async for event in workflow.run("test", stream=True):
            if event.type == "output":
                data = event.data
                if isinstance(data, list):
                    outputs.append(cast(list[Message], data))

        # Should have at least one output (the round limit message)
        assert len(outputs) >= 1
        # The last message in the conversation should be about round limit
        conversation = outputs[-1]
        assert len(conversation) >= 1
        final_output = conversation[-1]
        assert "maximum number of rounds" in final_output.text.lower()


async def test_group_chat_checkpoint_runtime_only() -> None:
    """Test checkpointing configured ONLY at runtime, not at build time."""
    storage = InMemoryCheckpointStorage()

    agent_a = StubAgent("agentA", "Reply from A")
    agent_b = StubAgent("agentB", "Reply from B")
    selector = make_sequence_selector()

    wf = GroupChatBuilder(participants=[agent_a, agent_b], max_rounds=2, selection_func=selector).build()

    baseline_output: list[Message] | None = None
    async for ev in wf.run("runtime checkpoint test", checkpoint_storage=storage, stream=True):
        if ev.type == "output":
            baseline_output = cast(list[Message], ev.data) if isinstance(ev.data, list) else None  # type: ignore
        if ev.type == "status" and ev.state in (
            WorkflowRunState.IDLE,
            WorkflowRunState.IDLE_WITH_PENDING_REQUESTS,
        ):
            break

    assert baseline_output is not None

    checkpoints = await storage.list_checkpoints(workflow_name=wf.name)
    assert len(checkpoints) > 0, "Runtime-only checkpointing should have created checkpoints"


async def test_group_chat_checkpoint_runtime_overrides_buildtime() -> None:
    """Test that runtime checkpoint storage overrides build-time configuration."""
    import tempfile

    with tempfile.TemporaryDirectory() as temp_dir1, tempfile.TemporaryDirectory() as temp_dir2:
        from agent_framework._workflows._checkpoint import FileCheckpointStorage

        buildtime_storage = FileCheckpointStorage(temp_dir1)
        runtime_storage = FileCheckpointStorage(temp_dir2)

        agent_a = StubAgent("agentA", "Reply from A")
        agent_b = StubAgent("agentB", "Reply from B")
        selector = make_sequence_selector()

        wf = GroupChatBuilder(
            participants=[agent_a, agent_b],
            max_rounds=2,
            checkpoint_storage=buildtime_storage,
            selection_func=selector,
        ).build()
        baseline_output: list[Message] | None = None
        async for ev in wf.run("override test", checkpoint_storage=runtime_storage, stream=True):
            if ev.type == "output":
                baseline_output = cast(list[Message], ev.data) if isinstance(ev.data, list) else None  # type: ignore
            if ev.type == "status" and ev.state in (
                WorkflowRunState.IDLE,
                WorkflowRunState.IDLE_WITH_PENDING_REQUESTS,
            ):
                break

        assert baseline_output is not None

        buildtime_checkpoints = await buildtime_storage.list_checkpoints(workflow_name=wf.name)
        runtime_checkpoints = await runtime_storage.list_checkpoints(workflow_name=wf.name)

        assert len(runtime_checkpoints) > 0, "Runtime storage should have checkpoints"
        assert len(buildtime_checkpoints) == 0, "Build-time storage should have no checkpoints when overridden"


async def test_group_chat_with_request_info_filtering():
    """Test that with_request_info(agents=[...]) only pauses before specified agents run."""
    # Create agents - we want to verify only beta triggers pause
    alpha = StubAgent("alpha", "response from alpha")
    beta = StubAgent("beta", "response from beta")

    # Manager that selects alpha first, then beta, then finishes
    call_count = 0

    async def selector(state: GroupChatState) -> str:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return "alpha"
        if call_count == 2:
            return "beta"
        # Return to alpha to continue
        return "alpha"

    workflow = (
        GroupChatBuilder(
            participants=[alpha, beta],
            max_rounds=2,
            selection_func=selector,
            orchestrator_name="manager",
        )
        .with_request_info(agents=["beta"])  # Only pause before beta runs
        .build()
    )

    # Run until we get a request info event (should be before beta, not alpha)
    request_events: list[WorkflowEvent] = []
    async for event in workflow.run("test task", stream=True):
        if event.type == "request_info" and isinstance(event.data, AgentExecutorResponse):
            request_events.append(event)
            # Don't break - let stream complete naturally when paused

    # Should have exactly one request event before beta
    assert len(request_events) == 1
    request_event = request_events[0]

    # The target agent should be beta's executor ID
    assert isinstance(request_event.data, AgentExecutorResponse)
    assert request_event.source_executor_id == "beta"

    # Continue the workflow with a response
    outputs: list[WorkflowEvent] = []
    async for event in workflow.run(
        stream=True, responses={request_event.request_id: AgentRequestInfoResponse.approve()}
    ):
        if event.type == "output":
            outputs.append(event)

    # Workflow should complete
    assert len(outputs) == 1


async def test_group_chat_with_request_info_no_filter_pauses_all():
    """Test that with_request_info() without agents pauses before all participants."""
    # Create agents
    alpha = StubAgent("alpha", "response from alpha")

    # Manager selects alpha then finishes
    call_count = 0

    async def selector(state: GroupChatState) -> str:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return "alpha"
        # Keep returning alpha to continue
        return "alpha"

    workflow = (
        GroupChatBuilder(
            participants=[alpha],
            max_rounds=1,
            selection_func=selector,
            orchestrator_name="manager",
        )
        .with_request_info()  # No filter - pause for all
        .build()
    )

    # Run until we get a request info event
    request_events: list[WorkflowEvent] = []
    async for event in workflow.run("test task", stream=True):
        if event.type == "request_info" and isinstance(event.data, AgentExecutorResponse):
            request_events.append(event)
            break

    # Should pause before alpha
    assert len(request_events) == 1
    assert request_events[0].source_executor_id == "alpha"


def test_group_chat_builder_with_request_info_returns_self():
    """Test that with_request_info() returns self for method chaining."""
    agent = StubAgent("test", "response")
    builder = GroupChatBuilder(participants=[agent])
    result = builder.with_request_info()
    assert result is builder

    # Also test with agents parameter
    builder2 = GroupChatBuilder(participants=[agent])
    result2 = builder2.with_request_info(agents=["test"])
    assert result2 is builder2


# region Orchestrator Factory Tests


def test_group_chat_builder_rejects_multiple_orchestrator_configurations():
    """Test that configuring multiple orchestrators raises ValueError."""

    def selector(state: GroupChatState) -> str:
        return list(state.participants.keys())[0]

    def agent_factory() -> Agent:
        return cast(Agent, StubManagerAgent())

    agent = StubAgent("test", "response")

    # Both selection_func and orchestrator_agent provided simultaneously - should fail
    with pytest.raises(ValueError, match=r"Exactly one of"):
        GroupChatBuilder(participants=[agent], selection_func=selector, orchestrator_agent=StubManagerAgent())

    # Test with agent_factory - already has factory, should fail with second config
    with pytest.raises(ValueError, match=r"Exactly one of"):
        GroupChatBuilder(participants=[agent], orchestrator_agent=agent_factory, selection_func=selector)


def test_group_chat_builder_requires_exactly_one_orchestrator_option():
    """Test that exactly one orchestrator option must be provided."""

    def selector(state: GroupChatState) -> str:
        return list(state.participants.keys())[0]

    def agent_factory() -> Agent:
        return cast(Agent, StubManagerAgent())

    agent = StubAgent("test", "response")

    # No orchestrator options provided - only fails at build() time
    with pytest.raises(ValueError, match="No orchestrator has been configured"):
        GroupChatBuilder(participants=[agent]).build()

    # Multiple options provided
    with pytest.raises(ValueError, match="Exactly one of"):
        GroupChatBuilder(participants=[agent], selection_func=selector, orchestrator_agent=agent_factory)


async def test_group_chat_with_orchestrator_factory_returning_chat_agent():
    """Test workflow creation using orchestrator_factory that returns Agent."""
    factory_call_count = 0

    class DynamicManagerAgent(Agent):
        """Manager agent that dynamically selects from available participants."""

        def __init__(self) -> None:
            super().__init__(client=MockChatClient(), name="dynamic_manager", description="Dynamic manager")
            self._call_count = 0

        async def run(
            self,
            messages: str | Content | Message | Sequence[str | Content | Message] | None = None,
            *,
            session: AgentSession | None = None,
            **kwargs: Any,
        ) -> AgentResponse:
            if self._call_count == 0:
                self._call_count += 1
                payload = {
                    "terminate": False,
                    "reason": "Selecting alpha",
                    "next_speaker": "alpha",
                    "final_message": None,
                }
                return AgentResponse(
                    messages=[
                        Message(
                            role="assistant",
                            text=(
                                '{"terminate": false, "reason": "Selecting alpha", '
                                '"next_speaker": "alpha", "final_message": null}'
                            ),
                            author_name=self.name,
                        )
                    ],
                    value=payload,
                )

            payload = {
                "terminate": True,
                "reason": "Task complete",
                "next_speaker": None,
                "final_message": "dynamic manager final",
            }
            return AgentResponse(
                messages=[
                    Message(
                        role="assistant",
                        text=(
                            '{"terminate": true, "reason": "Task complete", '
                            '"next_speaker": null, "final_message": "dynamic manager final"}'
                        ),
                        author_name=self.name,
                    )
                ],
                value=payload,
            )

    def agent_factory() -> Agent:
        nonlocal factory_call_count
        factory_call_count += 1
        return cast(Agent, DynamicManagerAgent())

    alpha = StubAgent("alpha", "reply from alpha")
    beta = StubAgent("beta", "reply from beta")

    workflow = GroupChatBuilder(participants=[alpha, beta], orchestrator_agent=agent_factory).build()

    # Factory should be called during build
    assert factory_call_count == 1

    outputs: list[WorkflowEvent] = []
    async for event in workflow.run("coordinate task", stream=True):
        if event.type == "output":
            outputs.append(event)

    assert len(outputs) == 1
    # The DynamicManagerAgent terminates after second call with final_message
    final_messages = outputs[0].data
    assert isinstance(final_messages, list)
    assert any(
        msg.text == "dynamic manager final"
        for msg in cast(list[Message], final_messages)
        if msg.author_name == "dynamic_manager"
    )


def test_group_chat_with_orchestrator_factory_returning_base_orchestrator():
    """Test that orchestrator_factory returning BaseGroupChatOrchestrator is used as-is."""
    factory_call_count = 0
    selector = make_sequence_selector()

    def orchestrator_factory() -> BaseGroupChatOrchestrator:
        nonlocal factory_call_count
        factory_call_count += 1
        from agent_framework.orchestrations import GroupChatOrchestrator

        from agent_framework_orchestrations._base_group_chat_orchestrator import ParticipantRegistry

        # Create a custom orchestrator; when returning BaseGroupChatOrchestrator,
        # the builder uses it as-is without modifying its participant registry
        return GroupChatOrchestrator(
            id="custom_orchestrator",
            participant_registry=ParticipantRegistry([]),
            selection_func=selector,
            max_rounds=2,
        )

    alpha = StubAgent("alpha", "reply from alpha")

    workflow = GroupChatBuilder(participants=[alpha], orchestrator=orchestrator_factory).build()

    # Factory should be called during build
    assert factory_call_count == 1
    # Verify the custom orchestrator is in the workflow
    assert "custom_orchestrator" in workflow.executors


async def test_group_chat_orchestrator_factory_reusable_builder():
    """Test that the builder can be reused to build multiple workflows with orchestrator factory."""
    factory_call_count = 0

    def agent_factory() -> Agent:
        nonlocal factory_call_count
        factory_call_count += 1
        return cast(Agent, StubManagerAgent())

    alpha = StubAgent("alpha", "reply from alpha")
    beta = StubAgent("beta", "reply from beta")

    builder = GroupChatBuilder(participants=[alpha, beta], orchestrator_agent=agent_factory)

    # Build first workflow
    wf1 = builder.build()
    assert factory_call_count == 1

    # Build second workflow
    wf2 = builder.build()
    assert factory_call_count == 2

    # Verify that the two workflows have different orchestrator instances
    assert wf1.executors["manager_agent"] is not wf2.executors["manager_agent"]


def test_group_chat_orchestrator_factory_invalid_return_type():
    """Test that orchestrator_factory raising error for invalid return type."""

    def invalid_factory() -> Any:
        return "invalid type"

    alpha = StubAgent("alpha", "reply from alpha")

    with pytest.raises(
        TypeError,
        match=r"Orchestrator factory must return Agent or BaseGroupChatOrchestrator instance",
    ):
        GroupChatBuilder(participants=[alpha], orchestrator=invalid_factory).build()

    with pytest.raises(
        TypeError,
        match=r"Orchestrator factory must return Agent or BaseGroupChatOrchestrator instance",
    ):
        GroupChatBuilder(participants=[alpha], orchestrator_agent=invalid_factory).build()


# endregion
