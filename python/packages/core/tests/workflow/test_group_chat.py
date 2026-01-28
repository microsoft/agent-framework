# Copyright (c) Microsoft. All rights reserved.

from collections.abc import AsyncIterable, Callable, Sequence
from typing import Any, cast

import pytest

from agent_framework import (
    AgentExecutorResponse,
    AgentRequestInfoResponse,
    AgentResponse,
    AgentResponseUpdate,
    AgentThread,
    BaseAgent,
    BaseGroupChatOrchestrator,
    ChatAgent,
    ChatMessage,
    ChatResponse,
    ChatResponseUpdate,
    Content,
    GroupChatBuilder,
    GroupChatState,
    MagenticContext,
    MagenticManagerBase,
    MagenticProgressLedger,
    MagenticProgressLedgerItem,
    RequestInfoEvent,
    Role,
    WorkflowOutputEvent,
    WorkflowRunState,
    WorkflowStatusEvent,
)
from agent_framework._workflows._checkpoint import InMemoryCheckpointStorage


class StubAgent(BaseAgent):
    def __init__(self, agent_name: str, reply_text: str, **kwargs: Any) -> None:
        super().__init__(name=agent_name, description=f"Stub agent {agent_name}", **kwargs)
        self._reply_text = reply_text

    async def run(  # type: ignore[override]
        self,
        messages: str | ChatMessage | Sequence[str | ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> AgentResponse:
        response = ChatMessage(role=Role.ASSISTANT, text=self._reply_text, author_name=self.name)
        return AgentResponse(messages=[response])

    def run_stream(  # type: ignore[override]
        self,
        messages: str | ChatMessage | Sequence[str | ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> AsyncIterable[AgentResponseUpdate]:
        async def _stream() -> AsyncIterable[AgentResponseUpdate]:
            yield AgentResponseUpdate(
                contents=[Content.from_text(text=self._reply_text)], role=Role.ASSISTANT, author_name=self.name
            )

        return _stream()


class MockChatClient:
    """Mock chat client that raises NotImplementedError for all methods."""

    additional_properties: dict[str, Any]

    async def get_response(self, messages: Any, **kwargs: Any) -> ChatResponse:
        raise NotImplementedError

    def get_streaming_response(self, messages: Any, **kwargs: Any) -> AsyncIterable[ChatResponseUpdate]:
        raise NotImplementedError


class StubManagerAgent(ChatAgent):
    def __init__(self) -> None:
        super().__init__(chat_client=MockChatClient(), name="manager_agent", description="Stub manager")
        self._call_count = 0

    async def run(
        self,
        messages: str | ChatMessage | Sequence[str | ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> AgentResponse:
        if self._call_count == 0:
            self._call_count += 1
            # First call: select the agent (using AgentOrchestrationOutput format)
            payload = {"terminate": False, "reason": "Selecting agent", "next_speaker": "agent", "final_message": None}
            return AgentResponse(
                messages=[
                    ChatMessage(
                        role=Role.ASSISTANT,
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
                ChatMessage(
                    role=Role.ASSISTANT,
                    text=(
                        '{"terminate": true, "reason": "Task complete", '
                        '"next_speaker": null, "final_message": "agent manager final"}'
                    ),
                    author_name=self.name,
                )
            ],
            value=payload,
        )

    def run_stream(
        self,
        messages: str | ChatMessage | Sequence[str | ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> AsyncIterable[AgentResponseUpdate]:
        if self._call_count == 0:
            self._call_count += 1

            async def _stream_initial() -> AsyncIterable[AgentResponseUpdate]:
                yield AgentResponseUpdate(
                    contents=[
                        Content.from_text(
                            text=(
                                '{"terminate": false, "reason": "Selecting agent", '
                                '"next_speaker": "agent", "final_message": null}'
                            )
                        )
                    ],
                    role=Role.ASSISTANT,
                    author_name=self.name,
                )

            return _stream_initial()

        async def _stream_final() -> AsyncIterable[AgentResponseUpdate]:
            yield AgentResponseUpdate(
                contents=[
                    Content.from_text(
                        text=(
                            '{"terminate": true, "reason": "Task complete", '
                            '"next_speaker": null, "final_message": "agent manager final"}'
                        )
                    )
                ],
                role=Role.ASSISTANT,
                author_name=self.name,
            )

        return _stream_final()


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

    async def plan(self, magentic_context: MagenticContext) -> ChatMessage:
        return ChatMessage(role=Role.ASSISTANT, text="plan", author_name="magentic_manager")

    async def replan(self, magentic_context: MagenticContext) -> ChatMessage:
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

    async def prepare_final_answer(self, magentic_context: MagenticContext) -> ChatMessage:
        return ChatMessage(role=Role.ASSISTANT, text="final", author_name="magentic_manager")


async def test_group_chat_builder_basic_flow() -> None:
    selector = make_sequence_selector()
    alpha = StubAgent("alpha", "ack from alpha")
    beta = StubAgent("beta", "ack from beta")

    workflow = (
        GroupChatBuilder()
        .with_orchestrator(selection_func=selector, orchestrator_name="manager")
        .participants([alpha, beta])
        .with_max_rounds(2)  # Limit rounds to prevent infinite loop
        .build()
    )

    outputs: list[list[ChatMessage]] = []
    async for event in workflow.run_stream("coordinate task"):
        if isinstance(event, WorkflowOutputEvent):
            data = event.data
            if isinstance(data, list):
                outputs.append(cast(list[ChatMessage], data))

    assert len(outputs) == 1
    assert len(outputs[0]) >= 1
    # Check that both agents contributed
    authors = {msg.author_name for msg in outputs[0] if msg.author_name in ["alpha", "beta"]}
    assert len(authors) == 2


async def test_group_chat_as_agent_accepts_conversation() -> None:
    selector = make_sequence_selector()
    alpha = StubAgent("alpha", "ack from alpha")
    beta = StubAgent("beta", "ack from beta")

    workflow = (
        GroupChatBuilder()
        .with_orchestrator(selection_func=selector, orchestrator_name="manager")
        .participants([alpha, beta])
        .with_max_rounds(2)  # Limit rounds to prevent infinite loop
        .build()
    )

    agent = workflow.as_agent(name="group-chat-agent")
    conversation = [
        ChatMessage(role=Role.USER, text="kickoff", author_name="user"),
        ChatMessage(role=Role.ASSISTANT, text="noted", author_name="alpha"),
    ]
    response = await agent.run(conversation)

    assert response.messages, "Expected agent conversation output"


# Comprehensive tests for group chat functionality


class TestGroupChatBuilder:
    """Tests for GroupChatBuilder validation and configuration."""

    def test_build_without_manager_raises_error(self) -> None:
        """Test that building without a manager raises ValueError."""
        agent = StubAgent("test", "response")

        builder = GroupChatBuilder().participants([agent])

        with pytest.raises(
            ValueError, match=r"No orchestrator has been configured\. Call with_orchestrator\(\) to set one\."
        ):
            builder.build()

    def test_build_without_participants_raises_error(self) -> None:
        """Test that building without participants raises ValueError."""

        def selector(state: GroupChatState) -> str:
            return "agent"

        builder = GroupChatBuilder().with_orchestrator(selection_func=selector)

        with pytest.raises(
            ValueError,
            match=r"No participants provided\. Call \.participants\(\) or \.register_participants\(\) first\.",
        ):
            builder.build()

    def test_duplicate_manager_configuration_raises_error(self) -> None:
        """Test that configuring multiple managers raises ValueError."""

        def selector(state: GroupChatState) -> str:
            return "agent"

        builder = GroupChatBuilder().with_orchestrator(selection_func=selector)

        with pytest.raises(
            ValueError,
            match=r"A selection function has already been configured\. Call with_orchestrator\(\.\.\.\) once only\.",
        ):
            builder.with_orchestrator(selection_func=selector)

    def test_empty_participants_raises_error(self) -> None:
        """Test that empty participants list raises ValueError."""

        def selector(state: GroupChatState) -> str:
            return "agent"

        builder = GroupChatBuilder().with_orchestrator(selection_func=selector)

        with pytest.raises(ValueError, match="participants cannot be empty"):
            builder.participants([])

    def test_duplicate_participant_names_raises_error(self) -> None:
        """Test that duplicate participant names raise ValueError."""
        agent1 = StubAgent("test", "response1")
        agent2 = StubAgent("test", "response2")

        def selector(state: GroupChatState) -> str:
            return "agent"

        builder = GroupChatBuilder().with_orchestrator(selection_func=selector)

        with pytest.raises(ValueError, match="Duplicate participant name 'test'"):
            builder.participants([agent1, agent2])

    def test_agent_without_name_raises_error(self) -> None:
        """Test that agent without name attribute raises ValueError."""

        class AgentWithoutName(BaseAgent):
            def __init__(self) -> None:
                super().__init__(name="", description="test")

            async def run(self, messages: Any = None, *, thread: Any = None, **kwargs: Any) -> AgentResponse:
                return AgentResponse(messages=[])

            def run_stream(
                self, messages: Any = None, *, thread: Any = None, **kwargs: Any
            ) -> AsyncIterable[AgentResponseUpdate]:
                async def _stream() -> AsyncIterable[AgentResponseUpdate]:
                    yield AgentResponseUpdate(contents=[])

                return _stream()

        agent = AgentWithoutName()

        def selector(state: GroupChatState) -> str:
            return "agent"

        builder = GroupChatBuilder().with_orchestrator(selection_func=selector)

        with pytest.raises(ValueError, match="AgentProtocol participants must have a non-empty name"):
            builder.participants([agent])

    def test_empty_participant_name_raises_error(self) -> None:
        """Test that empty participant name raises ValueError."""
        agent = StubAgent("", "response")  # Agent with empty name

        def selector(state: GroupChatState) -> str:
            return "agent"

        builder = GroupChatBuilder().with_orchestrator(selection_func=selector)

        with pytest.raises(ValueError, match="AgentProtocol participants must have a non-empty name"):
            builder.participants([agent])


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

        workflow = (
            GroupChatBuilder()
            .with_orchestrator(selection_func=selector)
            .participants([agent])
            .with_max_rounds(2)  # Limit to 2 rounds
            .build()
        )

        outputs: list[list[ChatMessage]] = []
        async for event in workflow.run_stream("test task"):
            if isinstance(event, WorkflowOutputEvent):
                data = event.data
                if isinstance(data, list):
                    outputs.append(cast(list[ChatMessage], data))

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

        def termination_condition(conversation: list[ChatMessage]) -> bool:
            replies = [msg for msg in conversation if msg.role == Role.ASSISTANT and msg.author_name == "agent"]
            return len(replies) >= 2

        agent = StubAgent("agent", "response")

        workflow = (
            GroupChatBuilder()
            .with_orchestrator(selection_func=selector)
            .participants([agent])
            .with_termination_condition(termination_condition)
            .build()
        )

        outputs: list[list[ChatMessage]] = []
        async for event in workflow.run_stream("test task"):
            if isinstance(event, WorkflowOutputEvent):
                data = event.data
                if isinstance(data, list):
                    outputs.append(cast(list[ChatMessage], data))

        assert outputs, "Expected termination to yield output"
        conversation = outputs[-1]
        agent_replies = [msg for msg in conversation if msg.author_name == "agent" and msg.role == Role.ASSISTANT]
        assert len(agent_replies) == 2
        final_output = conversation[-1]
        # The orchestrator uses its ID as author_name by default
        assert "termination condition" in final_output.text.lower()

    async def test_termination_condition_agent_manager_finalizes(self) -> None:
        """Test that termination condition with agent orchestrator produces default termination message."""
        manager = StubManagerAgent()
        worker = StubAgent("agent", "response")

        workflow = (
            GroupChatBuilder()
            .with_orchestrator(agent=manager)
            .participants([worker])
            .with_termination_condition(lambda conv: any(msg.author_name == "agent" for msg in conv))
            .build()
        )

        outputs: list[list[ChatMessage]] = []
        async for event in workflow.run_stream("test task"):
            if isinstance(event, WorkflowOutputEvent):
                data = event.data
                if isinstance(data, list):
                    outputs.append(cast(list[ChatMessage], data))

        assert outputs, "Expected termination to yield output"
        conversation = outputs[-1]
        assert conversation[-1].text == BaseGroupChatOrchestrator.TERMINATION_CONDITION_MET_MESSAGE
        assert conversation[-1].author_name == manager.name

    async def test_unknown_participant_error(self) -> None:
        """Test that unknown participant selection raises error."""

        def selector(state: GroupChatState) -> str:
            return "unknown_agent"  # Return non-existent participant

        agent = StubAgent("agent", "response")

        workflow = GroupChatBuilder().with_orchestrator(selection_func=selector).participants([agent]).build()

        with pytest.raises(RuntimeError, match="Selection function returned unknown participant 'unknown_agent'"):
            async for _ in workflow.run_stream("test task"):
                pass


class TestCheckpointing:
    """Tests for checkpointing functionality."""

    async def test_workflow_with_checkpointing(self) -> None:
        """Test that workflow works with checkpointing enabled."""

        def selector(state: GroupChatState) -> str:
            return "agent"

        agent = StubAgent("agent", "response")
        storage = InMemoryCheckpointStorage()

        workflow = (
            GroupChatBuilder()
            .with_orchestrator(selection_func=selector)
            .participants([agent])
            .with_max_rounds(1)
            .with_checkpointing(storage)
            .build()
        )

        outputs: list[list[ChatMessage]] = []
        async for event in workflow.run_stream("test task"):
            if isinstance(event, WorkflowOutputEvent):
                data = event.data
                if isinstance(data, list):
                    outputs.append(cast(list[ChatMessage], data))

        assert len(outputs) == 1  # Should complete normally


class TestConversationHandling:
    """Tests for different conversation input types."""

    async def test_handle_empty_conversation_raises_error(self) -> None:
        """Test that empty conversation list raises ValueError."""

        def selector(state: GroupChatState) -> str:
            return "agent"

        agent = StubAgent("agent", "response")

        workflow = (
            GroupChatBuilder()
            .with_orchestrator(selection_func=selector)
            .participants([agent])
            .with_max_rounds(1)
            .build()
        )

        with pytest.raises(ValueError, match="At least one ChatMessage is required to start the group chat workflow."):
            async for _ in workflow.run_stream([]):
                pass

    async def test_handle_string_input(self) -> None:
        """Test handling string input creates proper ChatMessage."""

        def selector(state: GroupChatState) -> str:
            # Verify the conversation has the user message
            assert len(state.conversation) > 0
            assert state.conversation[0].role == Role.USER
            assert state.conversation[0].text == "test string"
            return "agent"

        agent = StubAgent("agent", "response")

        workflow = (
            GroupChatBuilder()
            .with_orchestrator(selection_func=selector)
            .participants([agent])
            .with_max_rounds(1)
            .build()
        )

        outputs: list[list[ChatMessage]] = []
        async for event in workflow.run_stream("test string"):
            if isinstance(event, WorkflowOutputEvent):
                data = event.data
                if isinstance(data, list):
                    outputs.append(cast(list[ChatMessage], data))

        assert len(outputs) == 1

    async def test_handle_chat_message_input(self) -> None:
        """Test handling ChatMessage input directly."""
        task_message = ChatMessage(role=Role.USER, text="test message")

        def selector(state: GroupChatState) -> str:
            # Verify the task message was preserved in conversation
            assert len(state.conversation) > 0
            assert state.conversation[0] == task_message
            return "agent"

        agent = StubAgent("agent", "response")

        workflow = (
            GroupChatBuilder()
            .with_orchestrator(selection_func=selector)
            .participants([agent])
            .with_max_rounds(1)
            .build()
        )

        outputs: list[list[ChatMessage]] = []
        async for event in workflow.run_stream(task_message):
            if isinstance(event, WorkflowOutputEvent):
                data = event.data
                if isinstance(data, list):
                    outputs.append(cast(list[ChatMessage], data))

        assert len(outputs) == 1

    async def test_handle_conversation_list_input(self) -> None:
        """Test handling conversation list preserves context."""
        conversation = [
            ChatMessage(role=Role.SYSTEM, text="system message"),
            ChatMessage(role=Role.USER, text="user message"),
        ]

        def selector(state: GroupChatState) -> str:
            # Verify conversation context is preserved
            assert len(state.conversation) >= 2
            assert state.conversation[-1].text == "user message"
            return "agent"

        agent = StubAgent("agent", "response")

        workflow = (
            GroupChatBuilder()
            .with_orchestrator(selection_func=selector)
            .participants([agent])
            .with_max_rounds(1)
            .build()
        )

        outputs: list[list[ChatMessage]] = []
        async for event in workflow.run_stream(conversation):
            if isinstance(event, WorkflowOutputEvent):
                data = event.data
                if isinstance(data, list):
                    outputs.append(cast(list[ChatMessage], data))

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

        workflow = (
            GroupChatBuilder()
            .with_orchestrator(selection_func=selector)
            .participants([agent])
            .with_max_rounds(1)  # Very low limit
            .build()
        )

        outputs: list[list[ChatMessage]] = []
        async for event in workflow.run_stream("test"):
            if isinstance(event, WorkflowOutputEvent):
                data = event.data
                if isinstance(data, list):
                    outputs.append(cast(list[ChatMessage], data))

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

        workflow = (
            GroupChatBuilder()
            .with_orchestrator(selection_func=selector)
            .participants([agent])
            .with_max_rounds(1)  # Hit limit after first response
            .build()
        )

        outputs: list[list[ChatMessage]] = []
        async for event in workflow.run_stream("test"):
            if isinstance(event, WorkflowOutputEvent):
                data = event.data
                if isinstance(data, list):
                    outputs.append(cast(list[ChatMessage], data))

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

    wf = (
        GroupChatBuilder()
        .participants([agent_a, agent_b])
        .with_orchestrator(selection_func=selector)
        .with_max_rounds(2)
        .build()
    )

    baseline_output: list[ChatMessage] | None = None
    async for ev in wf.run_stream("runtime checkpoint test", checkpoint_storage=storage):
        if isinstance(ev, WorkflowOutputEvent):
            baseline_output = cast(list[ChatMessage], ev.data) if isinstance(ev.data, list) else None  # type: ignore
        if isinstance(ev, WorkflowStatusEvent) and ev.state in (
            WorkflowRunState.IDLE,
            WorkflowRunState.IDLE_WITH_PENDING_REQUESTS,
        ):
            break

    assert baseline_output is not None

    checkpoints = await storage.list_checkpoints()
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

        wf = (
            GroupChatBuilder()
            .participants([agent_a, agent_b])
            .with_orchestrator(selection_func=selector)
            .with_max_rounds(2)
            .with_checkpointing(buildtime_storage)
            .build()
        )
        baseline_output: list[ChatMessage] | None = None
        async for ev in wf.run_stream("override test", checkpoint_storage=runtime_storage):
            if isinstance(ev, WorkflowOutputEvent):
                baseline_output = cast(list[ChatMessage], ev.data) if isinstance(ev.data, list) else None  # type: ignore
            if isinstance(ev, WorkflowStatusEvent) and ev.state in (
                WorkflowRunState.IDLE,
                WorkflowRunState.IDLE_WITH_PENDING_REQUESTS,
            ):
                break

        assert baseline_output is not None

        buildtime_checkpoints = await buildtime_storage.list_checkpoints()
        runtime_checkpoints = await runtime_storage.list_checkpoints()

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
        GroupChatBuilder()
        .with_orchestrator(selection_func=selector, orchestrator_name="manager")
        .participants([alpha, beta])
        .with_max_rounds(2)
        .with_request_info(agents=["beta"])  # Only pause before beta runs
        .build()
    )

    # Run until we get a request info event (should be before beta, not alpha)
    request_events: list[RequestInfoEvent] = []
    async for event in workflow.run_stream("test task"):
        if isinstance(event, RequestInfoEvent) and isinstance(event.data, AgentExecutorResponse):
            request_events.append(event)
            # Don't break - let stream complete naturally when paused

    # Should have exactly one request event before beta
    assert len(request_events) == 1
    request_event = request_events[0]

    # The target agent should be beta's executor ID
    assert isinstance(request_event.data, AgentExecutorResponse)
    assert request_event.source_executor_id == "beta"

    # Continue the workflow with a response
    outputs: list[WorkflowOutputEvent] = []
    async for event in workflow.send_responses_streaming({
        request_event.request_id: AgentRequestInfoResponse.approve()
    }):
        if isinstance(event, WorkflowOutputEvent):
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
        GroupChatBuilder()
        .with_orchestrator(selection_func=selector, orchestrator_name="manager")
        .participants([alpha])
        .with_max_rounds(1)
        .with_request_info()  # No filter - pause for all
        .build()
    )

    # Run until we get a request info event
    request_events: list[RequestInfoEvent] = []
    async for event in workflow.run_stream("test task"):
        if isinstance(event, RequestInfoEvent) and isinstance(event.data, AgentExecutorResponse):
            request_events.append(event)
            break

    # Should pause before alpha
    assert len(request_events) == 1
    assert request_events[0].source_executor_id == "alpha"


def test_group_chat_builder_with_request_info_returns_self():
    """Test that with_request_info() returns self for method chaining."""
    builder = GroupChatBuilder()
    result = builder.with_request_info()
    assert result is builder

    # Also test with agents parameter
    builder2 = GroupChatBuilder()
    result2 = builder2.with_request_info(agents=["test"])
    assert result2 is builder2


# region Participant Factory Tests


def test_group_chat_builder_rejects_empty_participant_factories():
    """Test that GroupChatBuilder rejects empty participant_factories list."""

    def selector(state: GroupChatState) -> str:
        return list(state.participants.keys())[0]

    with pytest.raises(ValueError, match=r"participant_factories cannot be empty"):
        GroupChatBuilder().register_participants([])

    with pytest.raises(
        ValueError,
        match=r"No participants provided\. Call \.participants\(\) or \.register_participants\(\) first\.",
    ):
        GroupChatBuilder().with_orchestrator(selection_func=selector).build()


def test_group_chat_builder_rejects_mixing_participants_and_factories():
    """Test that mixing .participants() and .register_participants() raises an error."""
    alpha = StubAgent("alpha", "reply from alpha")

    # Case 1: participants first, then register_participants
    with pytest.raises(ValueError, match="Cannot mix .participants"):
        GroupChatBuilder().participants([alpha]).register_participants([lambda: StubAgent("beta", "reply from beta")])

    # Case 2: register_participants first, then participants
    with pytest.raises(ValueError, match="Cannot mix .participants"):
        GroupChatBuilder().register_participants([lambda: alpha]).participants([StubAgent("beta", "reply from beta")])


def test_group_chat_builder_rejects_multiple_calls_to_register_participants():
    """Test that multiple calls to .register_participants() raises an error."""
    with pytest.raises(
        ValueError, match=r"register_participants\(\) has already been called on this builder instance."
    ):
        (
            GroupChatBuilder()
            .register_participants([lambda: StubAgent("alpha", "reply from alpha")])
            .register_participants([lambda: StubAgent("beta", "reply from beta")])
        )


def test_group_chat_builder_rejects_multiple_calls_to_participants():
    """Test that multiple calls to .participants() raises an error."""
    with pytest.raises(ValueError, match="participants have already been set"):
        (
            GroupChatBuilder()
            .participants([StubAgent("alpha", "reply from alpha")])
            .participants([StubAgent("beta", "reply from beta")])
        )


async def test_group_chat_with_participant_factories():
    """Test workflow creation using participant_factories."""
    call_count = 0

    def create_alpha() -> StubAgent:
        nonlocal call_count
        call_count += 1
        return StubAgent("alpha", "reply from alpha")

    def create_beta() -> StubAgent:
        nonlocal call_count
        call_count += 1
        return StubAgent("beta", "reply from beta")

    selector = make_sequence_selector()

    workflow = (
        GroupChatBuilder()
        .register_participants([create_alpha, create_beta])
        .with_orchestrator(selection_func=selector)
        .with_max_rounds(2)
        .build()
    )

    # Factories should be called during build
    assert call_count == 2

    outputs: list[WorkflowOutputEvent] = []
    async for event in workflow.run_stream("coordinate task"):
        if isinstance(event, WorkflowOutputEvent):
            outputs.append(event)

    assert len(outputs) == 1


async def test_group_chat_participant_factories_reusable_builder():
    """Test that the builder can be reused to build multiple workflows with factories."""
    call_count = 0

    def create_alpha() -> StubAgent:
        nonlocal call_count
        call_count += 1
        return StubAgent("alpha", "reply from alpha")

    def create_beta() -> StubAgent:
        nonlocal call_count
        call_count += 1
        return StubAgent("beta", "reply from beta")

    selector = make_sequence_selector()

    builder = (
        GroupChatBuilder()
        .register_participants([create_alpha, create_beta])
        .with_orchestrator(selection_func=selector)
        .with_max_rounds(2)
    )

    # Build first workflow
    wf1 = builder.build()
    assert call_count == 2

    # Build second workflow
    wf2 = builder.build()
    assert call_count == 4

    # Verify that the two workflows have different agent instances
    assert wf1.executors["alpha"] is not wf2.executors["alpha"]
    assert wf1.executors["beta"] is not wf2.executors["beta"]


async def test_group_chat_participant_factories_with_checkpointing():
    """Test checkpointing with participant_factories."""
    storage = InMemoryCheckpointStorage()

    def create_alpha() -> StubAgent:
        return StubAgent("alpha", "reply from alpha")

    def create_beta() -> StubAgent:
        return StubAgent("beta", "reply from beta")

    selector = make_sequence_selector()

    workflow = (
        GroupChatBuilder()
        .register_participants([create_alpha, create_beta])
        .with_orchestrator(selection_func=selector)
        .with_checkpointing(storage)
        .with_max_rounds(2)
        .build()
    )

    outputs: list[WorkflowOutputEvent] = []
    async for event in workflow.run_stream("checkpoint test"):
        if isinstance(event, WorkflowOutputEvent):
            outputs.append(event)

    assert outputs, "Should have workflow output"

    checkpoints = await storage.list_checkpoints()
    assert checkpoints, "Checkpoints should be created during workflow execution"


# endregion

# region Orchestrator Factory Tests


def test_group_chat_builder_rejects_multiple_orchestrator_configurations():
    """Test that configuring multiple orchestrators raises ValueError."""

    def selector(state: GroupChatState) -> str:
        return list(state.participants.keys())[0]

    def agent_factory() -> ChatAgent:
        return cast(ChatAgent, StubManagerAgent())

    builder = GroupChatBuilder().with_orchestrator(selection_func=selector)

    # Already has a selection_func, should fail on second call
    with pytest.raises(ValueError, match=r"A selection function has already been configured"):
        builder.with_orchestrator(selection_func=selector)

    # Test with agent_factory
    builder2 = GroupChatBuilder().with_orchestrator(agent=agent_factory)
    with pytest.raises(ValueError, match=r"A factory has already been configured"):
        builder2.with_orchestrator(agent=agent_factory)


def test_group_chat_builder_requires_exactly_one_orchestrator_option():
    """Test that exactly one orchestrator option must be provided."""

    def selector(state: GroupChatState) -> str:
        return list(state.participants.keys())[0]

    def agent_factory() -> ChatAgent:
        return cast(ChatAgent, StubManagerAgent())

    # No options provided
    with pytest.raises(ValueError, match="Exactly one of"):
        GroupChatBuilder().with_orchestrator()  # type: ignore

    # Multiple options provided
    with pytest.raises(ValueError, match="Exactly one of"):
        GroupChatBuilder().with_orchestrator(selection_func=selector, agent=agent_factory)  # type: ignore


async def test_group_chat_with_orchestrator_factory_returning_chat_agent():
    """Test workflow creation using orchestrator_factory that returns ChatAgent."""
    factory_call_count = 0

    class DynamicManagerAgent(ChatAgent):
        """Manager agent that dynamically selects from available participants."""

        def __init__(self) -> None:
            super().__init__(chat_client=MockChatClient(), name="dynamic_manager", description="Dynamic manager")
            self._call_count = 0

        async def run(
            self,
            messages: str | ChatMessage | Sequence[str | ChatMessage] | None = None,
            *,
            thread: AgentThread | None = None,
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
                        ChatMessage(
                            role=Role.ASSISTANT,
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
                    ChatMessage(
                        role=Role.ASSISTANT,
                        text=(
                            '{"terminate": true, "reason": "Task complete", '
                            '"next_speaker": null, "final_message": "dynamic manager final"}'
                        ),
                        author_name=self.name,
                    )
                ],
                value=payload,
            )

    def agent_factory() -> ChatAgent:
        nonlocal factory_call_count
        factory_call_count += 1
        return cast(ChatAgent, DynamicManagerAgent())

    alpha = StubAgent("alpha", "reply from alpha")
    beta = StubAgent("beta", "reply from beta")

    workflow = GroupChatBuilder().participants([alpha, beta]).with_orchestrator(agent=agent_factory).build()

    # Factory should be called during build
    assert factory_call_count == 1

    outputs: list[WorkflowOutputEvent] = []
    async for event in workflow.run_stream("coordinate task"):
        if isinstance(event, WorkflowOutputEvent):
            outputs.append(event)

    assert len(outputs) == 1
    # The DynamicManagerAgent terminates after second call with final_message
    final_messages = outputs[0].data
    assert isinstance(final_messages, list)
    assert any(
        msg.text == "dynamic manager final"
        for msg in cast(list[ChatMessage], final_messages)
        if msg.author_name == "dynamic_manager"
    )


def test_group_chat_with_orchestrator_factory_returning_base_orchestrator():
    """Test that orchestrator_factory returning BaseGroupChatOrchestrator is used as-is."""
    factory_call_count = 0
    selector = make_sequence_selector()

    def orchestrator_factory() -> BaseGroupChatOrchestrator:
        nonlocal factory_call_count
        factory_call_count += 1
        from agent_framework._workflows._base_group_chat_orchestrator import ParticipantRegistry
        from agent_framework._workflows._group_chat import GroupChatOrchestrator

        # Create a custom orchestrator; when returning BaseGroupChatOrchestrator,
        # the builder uses it as-is without modifying its participant registry
        return GroupChatOrchestrator(
            id="custom_orchestrator",
            participant_registry=ParticipantRegistry([]),
            selection_func=selector,
            max_rounds=2,
        )

    alpha = StubAgent("alpha", "reply from alpha")

    workflow = GroupChatBuilder().participants([alpha]).with_orchestrator(orchestrator=orchestrator_factory).build()

    # Factory should be called during build
    assert factory_call_count == 1
    # Verify the custom orchestrator is in the workflow
    assert "custom_orchestrator" in workflow.executors


async def test_group_chat_orchestrator_factory_reusable_builder():
    """Test that the builder can be reused to build multiple workflows with orchestrator factory."""
    factory_call_count = 0

    def agent_factory() -> ChatAgent:
        nonlocal factory_call_count
        factory_call_count += 1
        return cast(ChatAgent, StubManagerAgent())

    alpha = StubAgent("alpha", "reply from alpha")
    beta = StubAgent("beta", "reply from beta")

    builder = GroupChatBuilder().participants([alpha, beta]).with_orchestrator(agent=agent_factory)

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
        match=r"Orchestrator factory must return ChatAgent or BaseGroupChatOrchestrator instance",
    ):
        (GroupChatBuilder().participants([alpha]).with_orchestrator(orchestrator=invalid_factory).build())

    with pytest.raises(
        TypeError,
        match=r"Orchestrator factory must return ChatAgent or BaseGroupChatOrchestrator instance",
    ):
        (GroupChatBuilder().participants([alpha]).with_orchestrator(agent=invalid_factory).build())


def test_group_chat_with_both_participant_and_orchestrator_factories():
    """Test workflow creation using both participant_factories and orchestrator_factory."""
    participant_factory_call_count = 0
    agent_factory_call_count = 0

    def create_alpha() -> StubAgent:
        nonlocal participant_factory_call_count
        participant_factory_call_count += 1
        return StubAgent("alpha", "reply from alpha")

    def create_beta() -> StubAgent:
        nonlocal participant_factory_call_count
        participant_factory_call_count += 1
        return StubAgent("beta", "reply from beta")

    def agent_factory() -> ChatAgent:
        nonlocal agent_factory_call_count
        agent_factory_call_count += 1
        return cast(ChatAgent, StubManagerAgent())

    workflow = (
        GroupChatBuilder()
        .register_participants([create_alpha, create_beta])
        .with_orchestrator(agent=agent_factory)
        .build()
    )

    # All factories should be called during build
    assert participant_factory_call_count == 2
    assert agent_factory_call_count == 1

    # Verify all executors are present in the workflow
    assert "alpha" in workflow.executors
    assert "beta" in workflow.executors
    assert "manager_agent" in workflow.executors


async def test_group_chat_factories_reusable_for_multiple_workflows():
    """Test that both factories are reused correctly for multiple workflow builds."""
    participant_factory_call_count = 0
    agent_factory_call_count = 0

    def create_alpha() -> StubAgent:
        nonlocal participant_factory_call_count
        participant_factory_call_count += 1
        return StubAgent("alpha", "reply from alpha")

    def create_beta() -> StubAgent:
        nonlocal participant_factory_call_count
        participant_factory_call_count += 1
        return StubAgent("beta", "reply from beta")

    def agent_factory() -> ChatAgent:
        nonlocal agent_factory_call_count
        agent_factory_call_count += 1
        return cast(ChatAgent, StubManagerAgent())

    builder = (
        GroupChatBuilder().register_participants([create_alpha, create_beta]).with_orchestrator(agent=agent_factory)
    )

    # Build first workflow
    wf1 = builder.build()
    assert participant_factory_call_count == 2
    assert agent_factory_call_count == 1

    # Build second workflow
    wf2 = builder.build()
    assert participant_factory_call_count == 4
    assert agent_factory_call_count == 2

    # Verify that the workflows have different agent and orchestrator instances
    assert wf1.executors["alpha"] is not wf2.executors["alpha"]
    assert wf1.executors["beta"] is not wf2.executors["beta"]
    assert wf1.executors["manager_agent"] is not wf2.executors["manager_agent"]


# endregion
