# Copyright (c) Microsoft. All rights reserved.

from collections.abc import AsyncIterable, Callable
from typing import Any, cast

import pytest
from pydantic import BaseModel

from agent_framework import (
    MAGENTIC_EVENT_TYPE_AGENT_DELTA,
    MAGENTIC_EVENT_TYPE_ORCHESTRATOR,
    AgentRunResponse,
    AgentRunResponseUpdate,
    AgentRunUpdateEvent,
    AgentThread,
    BaseAgent,
    ChatMessage,
    Executor,
    GroupChatBuilder,
    GroupChatDirective,
    GroupChatStateSnapshot,
    MagenticBuilder,
    MagenticContext,
    MagenticManagerBase,
    Role,
    TextContent,
    Workflow,
    WorkflowContext,
    WorkflowOutputEvent,
    handler,
)
from agent_framework._workflows._checkpoint import InMemoryCheckpointStorage
from agent_framework._workflows._group_chat import (
    GroupChatOrchestratorExecutor,
    ManagerSelectionResponse,
    _default_orchestrator_factory,  # type: ignore
    _default_participant_factory,  # type: ignore
    _GroupChatConfig,  # type: ignore
    _SpeakerSelectorAdapter,  # type: ignore
    assemble_group_chat_workflow,
)
from agent_framework._workflows._magentic import (
    _MagenticProgressLedger,  # type: ignore
    _MagenticProgressLedgerItem,  # type: ignore
    _MagenticStartMessage,  # type: ignore
)
from agent_framework._workflows._participant_utils import GroupChatParticipantSpec
from agent_framework._workflows._workflow_builder import WorkflowBuilder


class StubAgent(BaseAgent):
    def __init__(self, agent_name: str, reply_text: str, **kwargs: Any) -> None:
        super().__init__(name=agent_name, description=f"Stub agent {agent_name}", **kwargs)
        self._reply_text = reply_text

    async def run(  # type: ignore[override]
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> AgentRunResponse:
        response = ChatMessage(role=Role.ASSISTANT, text=self._reply_text, author_name=self.name)
        return AgentRunResponse(messages=[response])

    def run_stream(  # type: ignore[override]
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> AsyncIterable[AgentRunResponseUpdate]:
        async def _stream() -> AsyncIterable[AgentRunResponseUpdate]:
            yield AgentRunResponseUpdate(
                contents=[TextContent(text=self._reply_text)], role=Role.ASSISTANT, author_name=self.name
            )

        return _stream()


class StubManagerAgent(BaseAgent):
    def __init__(self) -> None:
        super().__init__(name="manager_agent", description="Stub manager")
        self._call_count = 0

    async def run(
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> AgentRunResponse:  # type: ignore[override]
        if self._call_count == 0:
            self._call_count += 1
            payload = {"selected_participant": "agent", "finish": False, "final_message": None}
            return AgentRunResponse(
                messages=[
                    ChatMessage(
                        role=Role.ASSISTANT,
                        text='{"selected_participant": "agent", "finish": false}',
                        author_name=self.name,
                    )
                ],
                value=payload,
            )

        payload = {"selected_participant": None, "finish": True, "final_message": "agent manager final"}
        return AgentRunResponse(
            messages=[
                ChatMessage(
                    role=Role.ASSISTANT,
                    text='{"finish": true, "final_message": "agent manager final"}',
                    author_name=self.name,
                )
            ],
            value=payload,
        )

    def run_stream(
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> AsyncIterable[AgentRunResponseUpdate]:  # type: ignore[override]
        if self._call_count == 0:
            self._call_count += 1

            async def _stream_initial() -> AsyncIterable[AgentRunResponseUpdate]:
                yield AgentRunResponseUpdate(
                    contents=[TextContent(text='{"selected_participant": "agent", "finish": false}')],
                    role=Role.ASSISTANT,
                    author_name=self.name,
                )

            return _stream_initial()

        async def _stream_final() -> AsyncIterable[AgentRunResponseUpdate]:
            yield AgentRunResponseUpdate(
                contents=[TextContent(text='{"finish": true, "final_message": "agent manager final"}')],
                role=Role.ASSISTANT,
                author_name=self.name,
            )

        return _stream_final()


def make_sequence_selector() -> Callable[[GroupChatStateSnapshot], Any]:
    state_counter = {"value": 0}

    async def _selector(state: GroupChatStateSnapshot) -> str | None:
        participants = list(state["participants"].keys())
        step = state_counter["value"]
        if step == 0:
            state_counter["value"] = step + 1
            return participants[0]
        if step == 1 and len(participants) > 1:
            state_counter["value"] = step + 1
            return participants[1]
        return None

    _selector.name = "manager"  # type: ignore[attr-defined]
    return _selector


class StubMagenticManager(MagenticManagerBase):
    def __init__(self) -> None:
        super().__init__(max_stall_count=3, max_round_count=5)
        self._round = 0

    async def plan(self, magentic_context: MagenticContext) -> ChatMessage:
        return ChatMessage(role=Role.ASSISTANT, text="plan", author_name="magentic_manager")

    async def replan(self, magentic_context: MagenticContext) -> ChatMessage:
        return await self.plan(magentic_context)

    async def create_progress_ledger(self, magentic_context: MagenticContext) -> _MagenticProgressLedger:
        participants = list(magentic_context.participant_descriptions.keys())
        target = participants[0] if participants else "agent"
        if self._round == 0:
            self._round += 1
            return _MagenticProgressLedger(
                is_request_satisfied=_MagenticProgressLedgerItem(reason="", answer=False),
                is_in_loop=_MagenticProgressLedgerItem(reason="", answer=False),
                is_progress_being_made=_MagenticProgressLedgerItem(reason="", answer=True),
                next_speaker=_MagenticProgressLedgerItem(reason="", answer=target),
                instruction_or_question=_MagenticProgressLedgerItem(reason="", answer="respond"),
            )
        return _MagenticProgressLedger(
            is_request_satisfied=_MagenticProgressLedgerItem(reason="", answer=True),
            is_in_loop=_MagenticProgressLedgerItem(reason="", answer=False),
            is_progress_being_made=_MagenticProgressLedgerItem(reason="", answer=True),
            next_speaker=_MagenticProgressLedgerItem(reason="", answer=target),
            instruction_or_question=_MagenticProgressLedgerItem(reason="", answer=""),
        )

    async def prepare_final_answer(self, magentic_context: MagenticContext) -> ChatMessage:
        return ChatMessage(role=Role.ASSISTANT, text="final", author_name="magentic_manager")


class PassthroughExecutor(Executor):
    @handler
    async def forward(self, message: Any, ctx: WorkflowContext[Any]) -> None:
        await ctx.send_message(message)


class CountingWorkflowBuilder(WorkflowBuilder):
    def __init__(self) -> None:
        super().__init__()
        self.start_calls = 0

    def set_start_executor(self, executor: Any) -> "CountingWorkflowBuilder":
        self.start_calls += 1
        return cast("CountingWorkflowBuilder", super().set_start_executor(executor))


async def test_group_chat_builder_basic_flow() -> None:
    selector = make_sequence_selector()
    alpha = StubAgent("alpha", "ack from alpha")
    beta = StubAgent("beta", "ack from beta")

    workflow = (
        GroupChatBuilder()
        .set_select_speakers_func(selector, display_name="manager", final_message="done")
        .participants(alpha=alpha, beta=beta)
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
    # The final message should be "done" from the manager
    assert outputs[0][-1].text == "done"
    assert outputs[0][-1].author_name == "manager"


async def test_magentic_builder_returns_workflow_and_runs() -> None:
    manager = StubMagenticManager()
    agent = StubAgent("writer", "first draft")

    workflow = MagenticBuilder().participants(writer=agent).with_standard_manager(manager=manager).build()

    assert isinstance(workflow, Workflow)

    outputs: list[ChatMessage] = []
    orchestrator_event_count = 0
    agent_event_count = 0
    start_message = _MagenticStartMessage.from_string("compose summary")
    async for event in workflow.run_stream(start_message):
        if isinstance(event, AgentRunUpdateEvent):
            props = event.data.additional_properties if event.data else None
            event_type = props.get("magentic_event_type") if props else None
            if event_type == MAGENTIC_EVENT_TYPE_ORCHESTRATOR:
                orchestrator_event_count += 1
            elif event_type == MAGENTIC_EVENT_TYPE_AGENT_DELTA:
                agent_event_count += 1
        if isinstance(event, WorkflowOutputEvent):
            msg = event.data
            if isinstance(msg, list):
                outputs.append(cast(list[ChatMessage], msg))

    assert outputs, "Expected a final output message"
    conversation = outputs[-1]
    assert len(conversation) >= 1
    final = conversation[-1]
    assert final.text == "final"
    assert final.author_name == "magentic_manager"
    assert orchestrator_event_count > 0, "Expected orchestrator events to be emitted"
    assert agent_event_count > 0, "Expected agent delta events to be emitted"


async def test_group_chat_as_agent_accepts_conversation() -> None:
    selector = make_sequence_selector()
    alpha = StubAgent("alpha", "ack from alpha")
    beta = StubAgent("beta", "ack from beta")

    workflow = (
        GroupChatBuilder()
        .set_select_speakers_func(selector, display_name="manager", final_message="done")
        .participants(alpha=alpha, beta=beta)
        .build()
    )

    agent = workflow.as_agent(name="group-chat-agent")
    conversation = [
        ChatMessage(role=Role.USER, text="kickoff", author_name="user"),
        ChatMessage(role=Role.ASSISTANT, text="noted", author_name="alpha"),
    ]
    response = await agent.run(conversation)

    assert response.messages, "Expected agent conversation output"


async def test_magentic_as_agent_accepts_conversation() -> None:
    manager = StubMagenticManager()
    writer = StubAgent("writer", "draft")

    workflow = MagenticBuilder().participants(writer=writer).with_standard_manager(manager=manager).build()

    agent = workflow.as_agent(name="magentic-agent")
    conversation = [
        ChatMessage(role=Role.SYSTEM, text="Guidelines", author_name="system"),
        ChatMessage(role=Role.USER, text="Summarize the findings", author_name="requester"),
    ]
    response = await agent.run(conversation)

    assert isinstance(response, AgentRunResponse)


# Comprehensive tests for group chat functionality


class TestGroupChatBuilder:
    """Tests for GroupChatBuilder validation and configuration."""

    def test_build_without_manager_raises_error(self) -> None:
        """Test that building without a manager raises ValueError."""
        agent = StubAgent("test", "response")

        builder = GroupChatBuilder().participants([agent])

        with pytest.raises(ValueError, match="manager must be configured before build"):
            builder.build()

    def test_build_without_participants_raises_error(self) -> None:
        """Test that building without participants raises ValueError."""

        def selector(state: GroupChatStateSnapshot) -> str | None:
            return None

        builder = GroupChatBuilder().set_select_speakers_func(selector)

        with pytest.raises(ValueError, match="participants must be configured before build"):
            builder.build()

    def test_duplicate_manager_configuration_raises_error(self) -> None:
        """Test that configuring multiple managers raises ValueError."""

        def selector(state: GroupChatStateSnapshot) -> str | None:
            return None

        builder = GroupChatBuilder().set_select_speakers_func(selector)

        with pytest.raises(ValueError, match="already has a manager configured"):
            builder.set_select_speakers_func(selector)

    def test_empty_participants_raises_error(self) -> None:
        """Test that empty participants list raises ValueError."""

        def selector(state: GroupChatStateSnapshot) -> str | None:
            return None

        builder = GroupChatBuilder().set_select_speakers_func(selector)

        with pytest.raises(ValueError, match="participants cannot be empty"):
            builder.participants([])

    def test_duplicate_participant_names_raises_error(self) -> None:
        """Test that duplicate participant names raise ValueError."""
        agent1 = StubAgent("test", "response1")
        agent2 = StubAgent("test", "response2")

        def selector(state: GroupChatStateSnapshot) -> str | None:
            return None

        builder = GroupChatBuilder().set_select_speakers_func(selector)

        with pytest.raises(ValueError, match="Duplicate participant name 'test'"):
            builder.participants([agent1, agent2])

    def test_agent_without_name_raises_error(self) -> None:
        """Test that agent without name attribute raises ValueError."""

        class AgentWithoutName(BaseAgent):
            def __init__(self) -> None:
                super().__init__(name="", description="test")

            async def run(self, messages: Any = None, *, thread: Any = None, **kwargs: Any) -> AgentRunResponse:
                return AgentRunResponse(messages=[])

            def run_stream(
                self, messages: Any = None, *, thread: Any = None, **kwargs: Any
            ) -> AsyncIterable[AgentRunResponseUpdate]:
                async def _stream() -> AsyncIterable[AgentRunResponseUpdate]:
                    yield AgentRunResponseUpdate(contents=[])

                return _stream()

        agent = AgentWithoutName()

        def selector(state: GroupChatStateSnapshot) -> str | None:
            return None

        builder = GroupChatBuilder().set_select_speakers_func(selector)

        with pytest.raises(ValueError, match="must define a non-empty 'name' attribute"):
            builder.participants([agent])

    def test_empty_participant_name_raises_error(self) -> None:
        """Test that empty participant name raises ValueError."""
        agent = StubAgent("test", "response")

        def selector(state: GroupChatStateSnapshot) -> str | None:
            return None

        builder = GroupChatBuilder().set_select_speakers_func(selector)

        with pytest.raises(ValueError, match="participant names must be non-empty strings"):
            builder.participants({"": agent})

    def test_assemble_group_chat_respects_existing_start_executor(self) -> None:
        """Ensure assemble_group_chat_workflow does not override preconfigured start executor."""

        async def manager(_: GroupChatStateSnapshot) -> GroupChatDirective:
            return GroupChatDirective(finish=True)

        builder = CountingWorkflowBuilder()
        entry = PassthroughExecutor(id="entry")
        builder = builder.set_start_executor(entry)

        participant = PassthroughExecutor(id="participant")
        participant_spec = GroupChatParticipantSpec(
            name="participant",
            participant=participant,
            description="participant",
        )

        wiring = _GroupChatConfig(
            manager=manager,
            manager_participant=None,
            manager_name="manager",
            participants={"participant": participant_spec},
            max_rounds=None,
            termination_condition=None,
            participant_aliases={},
            participant_executors={"participant": participant},
        )

        result = assemble_group_chat_workflow(
            wiring=wiring,
            participant_factory=_default_participant_factory,
            orchestrator_factory=_default_orchestrator_factory,
            builder=builder,
            return_builder=True,
        )

        assert isinstance(result, tuple)
        assembled_builder, _ = result
        assert assembled_builder is builder
        assert builder.start_calls == 1
        assert assembled_builder._start_executor is entry  # type: ignore


class TestGroupChatOrchestrator:
    """Tests for GroupChatOrchestratorExecutor core functionality."""

    async def test_max_rounds_enforcement(self) -> None:
        """Test that max_rounds properly limits conversation rounds."""
        call_count = {"value": 0}

        def selector(state: GroupChatStateSnapshot) -> str | None:
            call_count["value"] += 1
            # Always return the agent name to try to continue indefinitely
            return "agent"

        agent = StubAgent("agent", "response")

        workflow = (
            GroupChatBuilder()
            .set_select_speakers_func(selector)
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
        assert "round limit" in final_output.text.lower()

    async def test_termination_condition_halts_conversation(self) -> None:
        """Test that a custom termination condition stops the workflow."""

        def selector(state: GroupChatStateSnapshot) -> str | None:
            return "agent"

        def termination_condition(conversation: list[ChatMessage]) -> bool:
            replies = [msg for msg in conversation if msg.role == Role.ASSISTANT and msg.author_name == "agent"]
            return len(replies) >= 2

        agent = StubAgent("agent", "response")

        workflow = (
            GroupChatBuilder()
            .set_select_speakers_func(selector)
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
        assert final_output.author_name == "manager"
        assert "termination condition" in final_output.text.lower()

    async def test_termination_condition_uses_manager_final_message(self) -> None:
        """Test that manager-provided final message is used on termination."""

        async def selector(state: GroupChatStateSnapshot) -> str | None:
            return None

        agent = StubAgent("agent", "response")
        final_text = "manager summary on termination"

        workflow = (
            GroupChatBuilder()
            .set_select_speakers_func(selector, final_message=final_text)
            .participants([agent])
            .with_termination_condition(lambda _: True)
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
        assert conversation[-1].text == final_text
        assert conversation[-1].author_name == "manager"

    async def test_termination_condition_agent_manager_finalizes(self) -> None:
        """Test that agent-based manager can provide final message on termination."""
        manager = StubManagerAgent()
        worker = StubAgent("agent", "response")

        workflow = (
            GroupChatBuilder()
            .set_manager(manager, display_name="Manager")
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
        assert conversation[-1].text == "agent manager final"
        assert conversation[-1].author_name == "Manager"

    async def test_unknown_participant_error(self) -> None:
        """Test that _apply_directive raises error for unknown participants."""

        def selector(state: GroupChatStateSnapshot) -> str | None:
            return "unknown_agent"  # Return non-existent participant

        agent = StubAgent("agent", "response")

        workflow = GroupChatBuilder().set_select_speakers_func(selector).participants([agent]).build()

        with pytest.raises(ValueError, match="Manager selected unknown participant 'unknown_agent'"):
            async for _ in workflow.run_stream("test task"):
                pass

    async def test_directive_without_agent_name_raises_error(self) -> None:
        """Test that directive without agent_name raises error when finish=False."""

        def bad_selector(state: GroupChatStateSnapshot) -> GroupChatDirective:
            # Return a GroupChatDirective object instead of string to trigger error
            return GroupChatDirective(finish=False, agent_name=None)  # type: ignore

        agent = StubAgent("agent", "response")

        # The _SpeakerSelectorAdapter will catch this and raise TypeError
        workflow = GroupChatBuilder().set_select_speakers_func(bad_selector).participants([agent]).build()  # type: ignore

        # This should raise a TypeError because selector doesn't return str or None
        with pytest.raises(TypeError, match="must return a participant name \\(str\\) or None"):
            async for _ in workflow.run_stream("test"):
                pass

    async def test_handle_empty_conversation_raises_error(self) -> None:
        """Test that empty conversation list raises ValueError."""

        def selector(state: GroupChatStateSnapshot) -> str | None:
            return None

        agent = StubAgent("agent", "response")

        workflow = GroupChatBuilder().set_select_speakers_func(selector).participants([agent]).build()

        with pytest.raises(ValueError, match="requires at least one chat message"):
            async for _ in workflow.run_stream([]):
                pass

    async def test_unknown_participant_response_raises_error(self) -> None:
        """Test that responses from unknown participants raise errors."""

        def selector(state: GroupChatStateSnapshot) -> str | None:
            return "agent"

        # Create orchestrator to test _ingest_participant_message directly
        orchestrator = GroupChatOrchestratorExecutor(
            manager=selector,  # type: ignore
            participants={"agent": "test agent"},
            manager_name="test_manager",  # type: ignore
        )

        # Mock the workflow context
        class MockContext:
            async def yield_output(self, message: ChatMessage) -> None:
                pass

        ctx = MockContext()

        # Initialize orchestrator state
        orchestrator._task_message = ChatMessage(role=Role.USER, text="test")  # type: ignore
        orchestrator._conversation = [orchestrator._task_message]  # type: ignore
        orchestrator._history = []  # type: ignore
        orchestrator._pending_agent = None  # type: ignore
        orchestrator._round_index = 0  # type: ignore

        # Test with unknown participant
        message = ChatMessage(role=Role.ASSISTANT, text="response")

        with pytest.raises(ValueError, match="Received response from unknown participant 'unknown'"):
            await orchestrator._ingest_participant_message("unknown", message, ctx)  # type: ignore

    async def test_state_build_before_initialization_raises_error(self) -> None:
        """Test that _build_state raises error before task message initialization."""

        def selector(state: GroupChatStateSnapshot) -> str | None:
            return None

        orchestrator = GroupChatOrchestratorExecutor(
            manager=selector,  # type: ignore
            participants={"agent": "test agent"},
            manager_name="test_manager",  # type: ignore
        )

        with pytest.raises(RuntimeError, match="state not initialized with task message"):
            orchestrator._build_state()  # type: ignore


class TestSpeakerSelectorAdapter:
    """Tests for _SpeakerSelectorAdapter functionality."""

    async def test_selector_returning_list_with_multiple_items_raises_error(self) -> None:
        """Test that selector returning list with multiple items raises error."""

        def bad_selector(state: GroupChatStateSnapshot) -> list[str]:
            return ["agent1", "agent2"]  # Multiple items

        adapter = _SpeakerSelectorAdapter(bad_selector, manager_name="manager")

        state = {
            "participants": {"agent1": "desc1", "agent2": "desc2"},
            "task": ChatMessage(role=Role.USER, text="test"),
            "conversation": (),
            "history": (),
            "round_index": 0,
            "pending_agent": None,
        }

        with pytest.raises(ValueError, match="must return a single participant name"):
            await adapter(state)

    async def test_selector_returning_non_string_raises_error(self) -> None:
        """Test that selector returning non-string raises TypeError."""

        def bad_selector(state: GroupChatStateSnapshot) -> int:
            return 42  # Not a string

        adapter = _SpeakerSelectorAdapter(bad_selector, manager_name="manager")

        state = {
            "participants": {"agent": "desc"},
            "task": ChatMessage(role=Role.USER, text="test"),
            "conversation": (),
            "history": (),
            "round_index": 0,
            "pending_agent": None,
        }

        with pytest.raises(TypeError, match="must return a participant name \\(str\\) or None"):
            await adapter(state)

    async def test_selector_returning_empty_list_finishes(self) -> None:
        """Test that selector returning empty list finishes conversation."""

        def empty_selector(state: GroupChatStateSnapshot) -> list[str]:
            return []  # Empty list should finish

        adapter = _SpeakerSelectorAdapter(empty_selector, manager_name="manager")

        state = {
            "participants": {"agent": "desc"},
            "task": ChatMessage(role=Role.USER, text="test"),
            "conversation": (),
            "history": (),
            "round_index": 0,
            "pending_agent": None,
        }

        directive = await adapter(state)
        assert directive.finish is True
        assert directive.final_message is not None


class TestCheckpointing:
    """Tests for checkpointing functionality."""

    async def test_workflow_with_checkpointing(self) -> None:
        """Test that workflow works with checkpointing enabled."""

        def selector(state: GroupChatStateSnapshot) -> str | None:
            if state["round_index"] >= 1:
                return None
            return "agent"

        agent = StubAgent("agent", "response")
        storage = InMemoryCheckpointStorage()

        workflow = (
            GroupChatBuilder()
            .set_select_speakers_func(selector)
            .participants([agent])
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


class TestAgentManagerConfiguration:
    """Tests for agent-based manager configuration."""

    async def test_set_manager_configures_response_format(self) -> None:
        """Ensure ChatAgent managers receive default ManagerSelectionResponse formatting."""
        from unittest.mock import MagicMock

        from agent_framework import ChatAgent

        chat_client = MagicMock()
        manager_agent = ChatAgent(chat_client=chat_client, name="Coordinator")
        assert manager_agent.chat_options.response_format is None

        worker = StubAgent("worker", "response")

        builder = GroupChatBuilder().set_manager(manager_agent).participants([worker])

        assert manager_agent.chat_options.response_format is ManagerSelectionResponse
        assert builder._manager_participant is manager_agent  # type: ignore[attr-defined]

    async def test_set_manager_accepts_agent_manager(self) -> None:
        """Verify agent-based manager can be set and workflow builds."""
        from unittest.mock import MagicMock

        from agent_framework import ChatAgent

        chat_client = MagicMock()
        manager_agent = ChatAgent(chat_client=chat_client, name="Coordinator")
        worker = StubAgent("worker", "response")

        builder = GroupChatBuilder().set_manager(manager_agent, display_name="Orchestrator")
        builder = builder.participants([worker]).with_max_rounds(1)

        assert builder._manager_participant is manager_agent  # type: ignore[attr-defined]
        assert "worker" in builder._participants  # type: ignore[attr-defined]

    async def test_set_manager_rejects_custom_response_format(self) -> None:
        """Reject custom response_format on ChatAgent managers."""
        from unittest.mock import MagicMock

        from agent_framework import ChatAgent

        class CustomResponse(BaseModel):
            value: str

        chat_client = MagicMock()
        manager_agent = ChatAgent(chat_client=chat_client, name="Coordinator", response_format=CustomResponse)
        worker = StubAgent("worker", "response")

        with pytest.raises(ValueError, match="response_format must be ManagerSelectionResponse"):
            GroupChatBuilder().set_manager(manager_agent).participants([worker])

        assert manager_agent.chat_options.response_format is CustomResponse


class TestFactoryFunctions:
    """Tests for factory functions."""

    def test_default_orchestrator_factory_without_manager_raises_error(self) -> None:
        """Test that default factory requires manager to be set."""
        config = _GroupChatConfig(manager=None, manager_participant=None, manager_name="test", participants={})

        with pytest.raises(RuntimeError, match="requires a manager to be configured"):
            _default_orchestrator_factory(config)


class TestConversationHandling:
    """Tests for different conversation input types."""

    async def test_handle_string_input(self) -> None:
        """Test handling string input creates proper ChatMessage."""

        def selector(state: GroupChatStateSnapshot) -> str | None:
            # Verify the task was properly converted
            assert state["task"].role == Role.USER
            assert state["task"].text == "test string"
            return None

        agent = StubAgent("agent", "response")

        workflow = GroupChatBuilder().set_select_speakers_func(selector).participants([agent]).build()

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

        def selector(state: GroupChatStateSnapshot) -> str | None:
            # Verify the task message was preserved
            assert state["task"] == task_message
            return None

        agent = StubAgent("agent", "response")

        workflow = GroupChatBuilder().set_select_speakers_func(selector).participants([agent]).build()

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

        def selector(state: GroupChatStateSnapshot) -> str | None:
            # Verify conversation context is preserved
            assert len(state["conversation"]) == 2
            assert state["task"].text == "user message"
            return None

        agent = StubAgent("agent", "response")

        workflow = GroupChatBuilder().set_select_speakers_func(selector).participants([agent]).build()

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
        """Test round limit enforcement in _apply_directive."""
        rounds_called = {"count": 0}

        def selector(state: GroupChatStateSnapshot) -> str | None:
            rounds_called["count"] += 1
            # Keep trying to select agent to test limit enforcement
            return "agent"

        agent = StubAgent("agent", "response")

        workflow = (
            GroupChatBuilder()
            .set_select_speakers_func(selector)
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
        assert "round limit" in final_output.text.lower()

    async def test_round_limit_in_ingest_participant_message(self) -> None:
        """Test round limit enforcement after participant response."""
        responses_received = {"count": 0}

        def selector(state: GroupChatStateSnapshot) -> str | None:
            responses_received["count"] += 1
            if responses_received["count"] == 1:
                return "agent"  # First call selects agent
            return "agent"  # Try to continue, but should hit limit

        agent = StubAgent("agent", "response from agent")

        workflow = (
            GroupChatBuilder()
            .set_select_speakers_func(selector)
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
        assert "round limit" in final_output.text.lower()


async def test_group_chat_checkpoint_runtime_only() -> None:
    """Test checkpointing configured ONLY at runtime, not at build time."""
    from agent_framework import WorkflowRunState, WorkflowStatusEvent

    storage = InMemoryCheckpointStorage()

    agent_a = StubAgent("agentA", "Reply from A")
    agent_b = StubAgent("agentB", "Reply from B")
    selector = make_sequence_selector()

    wf = GroupChatBuilder().participants([agent_a, agent_b]).set_select_speakers_func(selector).build()

    baseline_output: list[ChatMessage] | None = None
    async for ev in wf.run_stream("runtime checkpoint test", checkpoint_storage=storage):
        if isinstance(ev, WorkflowOutputEvent):
            baseline_output = cast(list[ChatMessage], ev.data) if isinstance(ev.data, list) else None
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
        from agent_framework import WorkflowRunState, WorkflowStatusEvent
        from agent_framework._workflows._checkpoint import FileCheckpointStorage

        buildtime_storage = FileCheckpointStorage(temp_dir1)
        runtime_storage = FileCheckpointStorage(temp_dir2)

        agent_a = StubAgent("agentA", "Reply from A")
        agent_b = StubAgent("agentB", "Reply from B")
        selector = make_sequence_selector()

        wf = (
            GroupChatBuilder()
            .participants([agent_a, agent_b])
            .set_select_speakers_func(selector)
            .with_checkpointing(buildtime_storage)
            .build()
        )

        baseline_output: list[ChatMessage] | None = None
        async for ev in wf.run_stream("override test", checkpoint_storage=runtime_storage):
            if isinstance(ev, WorkflowOutputEvent):
                baseline_output = cast(list[ChatMessage], ev.data) if isinstance(ev.data, list) else None
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


class _StubExecutor(Executor):
    """Minimal executor used to satisfy workflow wiring in tests."""

    def __init__(self, id: str) -> None:
        super().__init__(id=id)

    @handler
    async def handle(self, message: object, ctx: WorkflowContext[ChatMessage]) -> None:
        await ctx.yield_output(message)


def test_set_manager_builds_with_agent_manager() -> None:
    """GroupChatBuilder should build when using an agent-based manager."""

    manager = _StubExecutor("manager_executor")
    participant = _StubExecutor("participant_executor")

    workflow = (
        GroupChatBuilder().set_manager(manager, display_name="Moderator").participants({"worker": participant}).build()
    )

    orchestrator = workflow.get_start_executor()

    assert isinstance(orchestrator, GroupChatOrchestratorExecutor)
    assert orchestrator._is_manager_agent()
