# Copyright (c) Microsoft. All rights reserved.

from collections.abc import AsyncIterable
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest

from agent_framework import (
    ChatAgent,
    ChatMessage,
    ChatResponse,
    ChatResponseUpdate,
    Content,
    HandoffAgentUserRequest,
    HandoffBuilder,
    RequestInfoEvent,
    Role,
    WorkflowEvent,
    WorkflowOutputEvent,
    resolve_agent_id,
    use_function_invocation,
)


@use_function_invocation
class MockChatClient:
    """Mock chat client for testing handoff workflows."""

    additional_properties: dict[str, Any]

    def __init__(
        self,
        name: str,
        *,
        handoff_to: str | None = None,
    ) -> None:
        """Initialize the mock chat client.

        Args:
            name: The name of the agent using this chat client.
            handoff_to: The name of the agent to hand off to, or None for no handoff.
                This is hardcoded for testing purposes so that the agent always attempts to hand off.
        """
        self._name = name
        self._handoff_to = handoff_to
        self._call_index = 0

    async def get_response(self, messages: Any, **kwargs: Any) -> ChatResponse:
        contents = _build_reply_contents(self._name, self._handoff_to, self._next_call_id())
        reply = ChatMessage(
            role=Role.ASSISTANT,
            contents=contents,
        )
        return ChatResponse(messages=reply, response_id="mock_response")

    def get_streaming_response(self, messages: Any, **kwargs: Any) -> AsyncIterable[ChatResponseUpdate]:
        async def _stream() -> AsyncIterable[ChatResponseUpdate]:
            contents = _build_reply_contents(self._name, self._handoff_to, self._next_call_id())
            yield ChatResponseUpdate(contents=contents, role=Role.ASSISTANT)

        return _stream()

    def _next_call_id(self) -> str | None:
        if not self._handoff_to:
            return None
        call_id = f"{self._name}-handoff-{self._call_index}"
        self._call_index += 1
        return call_id


def _build_reply_contents(
    agent_name: str,
    handoff_to: str | None,
    call_id: str | None,
) -> list[Content]:
    contents: list[Content] = []
    if handoff_to and call_id:
        contents.append(
            Content.from_function_call(
                call_id=call_id, name=f"handoff_to_{handoff_to}", arguments={"handoff_to": handoff_to}
            )
        )
    text = f"{agent_name} reply"
    contents.append(Content.from_text(text=text))
    return contents


class MockHandoffAgent(ChatAgent):
    """Mock agent that can hand off to another agent."""

    def __init__(
        self,
        *,
        name: str,
        handoff_to: str | None = None,
    ) -> None:
        """Initialize the mock handoff agent.

        Args:
            name: The name of the agent.
            handoff_to: The name of the agent to hand off to, or None for no handoff.
                This is hardcoded for testing purposes so that the agent always attempts to hand off.
        """
        super().__init__(chat_client=MockChatClient(name, handoff_to=handoff_to), name=name, id=name)


async def _drain(stream: AsyncIterable[WorkflowEvent]) -> list[WorkflowEvent]:
    return [event async for event in stream]


async def test_handoff():
    """Test that agents can hand off to each other."""

    # `triage` hands off to `specialist`, who then hands off to `escalation`.
    # `escalation` has no handoff, so the workflow should request user input to continue.
    triage = MockHandoffAgent(name="triage", handoff_to="specialist")
    specialist = MockHandoffAgent(name="specialist", handoff_to="escalation")
    escalation = MockHandoffAgent(name="escalation")

    # Without explicitly defining handoffs, the builder will create connections
    # between all agents.
    workflow = (
        HandoffBuilder(participants=[triage, specialist, escalation])
        .with_start_agent(triage)
        .with_termination_condition(lambda conv: sum(1 for m in conv if m.role == Role.USER) >= 2)
        .build()
    )

    # Start conversation - triage hands off to specialist then escalation
    # escalation won't trigger a handoff, so the response from it will become
    # a request for user input because autonomous mode is not enabled by default.
    events = await _drain(workflow.run_stream("Need technical support"))
    requests = [ev for ev in events if isinstance(ev, RequestInfoEvent)]

    assert requests
    assert len(requests) == 1

    request = requests[0]
    assert isinstance(request.data, HandoffAgentUserRequest)
    assert request.source_executor_id == escalation.name


async def test_autonomous_mode_yields_output_without_user_request():
    """Ensure autonomous interaction mode yields output without requesting user input."""
    triage = MockHandoffAgent(name="triage", handoff_to="specialist")
    specialist = MockHandoffAgent(name="specialist")

    workflow = (
        HandoffBuilder(participants=[triage, specialist])
        .with_start_agent(triage)
        # Since specialist has no handoff, the specialist will be generating normal responses.
        # With autonomous mode, this should continue until the termination condition is met.
        .with_autonomous_mode(
            agents=[specialist],
            turn_limits={resolve_agent_id(specialist): 1},
        )
        # This termination condition ensures the workflow runs through both agents.
        # First message is the user message to triage, second is triage's response, which
        # is a handoff to specialist, third is specialist's response that should not request
        # user input due to autonomous mode. Fourth message will come from the specialist
        # again and will trigger termination.
        .with_termination_condition(lambda conv: len(conv) >= 4)
        .build()
    )

    events = await _drain(workflow.run_stream("Package arrived broken"))
    requests = [ev for ev in events if isinstance(ev, RequestInfoEvent)]
    assert not requests, "Autonomous mode should not request additional user input"

    outputs = [ev for ev in events if isinstance(ev, WorkflowOutputEvent)]
    assert outputs, "Autonomous mode should yield a workflow output"

    final_conversation = outputs[-1].data
    assert isinstance(final_conversation, list)
    conversation_list = cast(list[ChatMessage], final_conversation)
    assert any(
        msg.role == Role.ASSISTANT and (msg.text or "").startswith("specialist reply") for msg in conversation_list
    )


async def test_autonomous_mode_resumes_user_input_on_turn_limit():
    """Autonomous mode should resume user input request when turn limit is reached."""
    triage = MockHandoffAgent(name="triage", handoff_to="worker")
    worker = MockHandoffAgent(name="worker")

    workflow = (
        HandoffBuilder(participants=[triage, worker])
        .with_start_agent(triage)
        .with_autonomous_mode(agents=[worker], turn_limits={resolve_agent_id(worker): 2})
        .with_termination_condition(lambda conv: False)
        .build()
    )

    events = await _drain(workflow.run_stream("Start"))
    requests = [ev for ev in events if isinstance(ev, RequestInfoEvent)]
    assert requests and len(requests) == 1, "Turn limit should force a user input request"
    assert requests[0].source_executor_id == worker.name


def test_build_fails_without_start_agent():
    """Verify that build() raises ValueError when with_start_agent() was not called."""
    triage = MockHandoffAgent(name="triage")
    specialist = MockHandoffAgent(name="specialist")

    with pytest.raises(ValueError, match=r"Must call with_start_agent\(...\) before building the workflow."):
        HandoffBuilder(participants=[triage, specialist]).build()


def test_build_fails_without_participants():
    """Verify that build() raises ValueError when no participants are provided."""
    with pytest.raises(
        ValueError, match=r"No participants provided\. Call \.participants\(\) or \.register_participants\(\) first."
    ):
        HandoffBuilder().build()


async def test_handoff_async_termination_condition() -> None:
    """Test that async termination conditions work correctly."""
    termination_call_count = 0

    async def async_termination(conv: list[ChatMessage]) -> bool:
        nonlocal termination_call_count
        termination_call_count += 1
        user_count = sum(1 for msg in conv if msg.role == Role.USER)
        return user_count >= 2

    coordinator = MockHandoffAgent(name="coordinator", handoff_to="worker")
    worker = MockHandoffAgent(name="worker")

    workflow = (
        HandoffBuilder(participants=[coordinator, worker])
        .with_start_agent(coordinator)
        .with_termination_condition(async_termination)
        .build()
    )

    events = await _drain(workflow.run_stream("First user message"))
    requests = [ev for ev in events if isinstance(ev, RequestInfoEvent)]
    assert requests

    events = await _drain(
        workflow.send_responses_streaming({
            requests[-1].request_id: [ChatMessage(role=Role.USER, text="Second user message")]
        })
    )
    outputs = [ev for ev in events if isinstance(ev, WorkflowOutputEvent)]
    assert len(outputs) == 1

    final_conversation = outputs[0].data
    assert isinstance(final_conversation, list)
    final_conv_list = cast(list[ChatMessage], final_conversation)
    user_messages = [msg for msg in final_conv_list if msg.role == Role.USER]
    assert len(user_messages) == 2
    assert termination_call_count > 0


async def test_tool_choice_preserved_from_agent_config():
    """Verify that agent-level tool_choice configuration is preserved and not overridden."""
    # Create a mock chat client that records the tool_choice used
    recorded_tool_choices: list[Any] = []

    async def mock_get_response(messages: Any, options: dict[str, Any] | None = None, **kwargs: Any) -> ChatResponse:
        if options:
            recorded_tool_choices.append(options.get("tool_choice"))
        return ChatResponse(
            messages=[ChatMessage(role=Role.ASSISTANT, text="Response")],
            response_id="test_response",
        )

    mock_client = MagicMock()
    mock_client.get_response = AsyncMock(side_effect=mock_get_response)

    # Create agent with specific tool_choice configuration via default_options
    agent = ChatAgent(
        chat_client=mock_client,
        name="test_agent",
        default_options={"tool_choice": {"mode": "required"}},  # type: ignore
    )

    # Run the agent
    await agent.run("Test message")

    # Verify tool_choice was preserved
    assert len(recorded_tool_choices) > 0, "No tool_choice recorded"
    last_tool_choice = recorded_tool_choices[-1]
    assert last_tool_choice is not None, "tool_choice should not be None"
    assert last_tool_choice == {"mode": "required"}, f"Expected 'required', got {last_tool_choice}"


# region Participant Factory Tests


def test_handoff_builder_rejects_empty_participant_factories():
    """Test that HandoffBuilder rejects empty participant_factories dictionary."""
    # Empty factories are rejected immediately when calling participant_factories()
    with pytest.raises(ValueError, match=r"participant_factories cannot be empty"):
        HandoffBuilder().register_participants({})

    with pytest.raises(
        ValueError, match=r"No participants provided\. Call \.participants\(\) or \.register_participants\(\) first\."
    ):
        HandoffBuilder(participant_factories={}).build()


def test_handoff_builder_rejects_mixing_participants_and_factories():
    """Test that mixing participants and participant_factories in __init__ raises an error."""
    triage = MockHandoffAgent(name="triage")
    with pytest.raises(ValueError, match="Cannot mix .participants"):
        HandoffBuilder(participants=[triage], participant_factories={"triage": lambda: triage})


def test_handoff_builder_rejects_mixing_participants_and_participant_factories_methods():
    """Test that mixing .participants() and .participant_factories() raises an error."""
    triage = MockHandoffAgent(name="triage")

    # Case 1: participants first, then participant_factories
    with pytest.raises(ValueError, match="Cannot mix .participants"):
        HandoffBuilder(participants=[triage]).register_participants({
            "specialist": lambda: MockHandoffAgent(name="specialist")
        })

    # Case 2: participant_factories first, then participants
    with pytest.raises(ValueError, match="Cannot mix .participants"):
        HandoffBuilder(participant_factories={"triage": lambda: triage}).participants([
            MockHandoffAgent(name="specialist")
        ])

    # Case 3: participants(), then participant_factories()
    with pytest.raises(ValueError, match="Cannot mix .participants"):
        HandoffBuilder().participants([triage]).register_participants({
            "specialist": lambda: MockHandoffAgent(name="specialist")
        })

    # Case 4: participant_factories(), then participants()
    with pytest.raises(ValueError, match="Cannot mix .participants"):
        HandoffBuilder().register_participants({"triage": lambda: triage}).participants([
            MockHandoffAgent(name="specialist")
        ])

    # Case 5: mix during initialization
    with pytest.raises(ValueError, match="Cannot mix .participants"):
        HandoffBuilder(
            participants=[triage], participant_factories={"specialist": lambda: MockHandoffAgent(name="specialist")}
        )


def test_handoff_builder_rejects_multiple_calls_to_participant_factories():
    """Test that multiple calls to .participant_factories() raises an error."""
    with pytest.raises(
        ValueError, match=r"register_participants\(\) has already been called on this builder instance."
    ):
        (
            HandoffBuilder()
            .register_participants({"agent1": lambda: MockHandoffAgent(name="agent1")})
            .register_participants({"agent2": lambda: MockHandoffAgent(name="agent2")})
        )


def test_handoff_builder_rejects_multiple_calls_to_participants():
    """Test that multiple calls to .participants() raises an error."""
    with pytest.raises(ValueError, match="participants have already been assigned"):
        (
            HandoffBuilder()
            .participants([MockHandoffAgent(name="agent1")])
            .participants([MockHandoffAgent(name="agent2")])
        )


def test_handoff_builder_rejects_instance_coordinator_with_factories():
    """Test that using an agent instance for set_coordinator when using factories raises an error."""

    def create_triage() -> MockHandoffAgent:
        return MockHandoffAgent(name="triage")

    def create_specialist() -> MockHandoffAgent:
        return MockHandoffAgent(name="specialist")

    # Create an agent instance
    coordinator_instance = MockHandoffAgent(name="coordinator")

    with pytest.raises(ValueError, match=r"Call participants\(\.\.\.\) before with_start_agent\(\.\.\.\)"):
        (
            HandoffBuilder(
                participant_factories={"triage": create_triage, "specialist": create_specialist}
            ).with_start_agent(coordinator_instance)  # Instance, not factory name
        )


def test_handoff_builder_rejects_factory_name_coordinator_with_instances():
    """Test that using a factory name for set_coordinator when using instances raises an error."""
    triage = MockHandoffAgent(name="triage")
    specialist = MockHandoffAgent(name="specialist")

    with pytest.raises(ValueError, match=r"Call register_participants\(...\) before with_start_agent\(...\)"):
        (
            HandoffBuilder(participants=[triage, specialist]).with_start_agent(
                "triage"
            )  # String factory name, not instance
        )


def test_handoff_builder_rejects_mixed_types_in_add_handoff_source():
    """Test that add_handoff rejects factory name source with instance-based participants."""
    triage = MockHandoffAgent(name="triage")
    specialist = MockHandoffAgent(name="specialist")

    with pytest.raises(TypeError, match="Cannot mix factory names \\(str\\) and AgentProtocol.*instances"):
        (
            HandoffBuilder(participants=[triage, specialist])
            .with_start_agent(triage)
            .add_handoff("triage", [specialist])  # String source with instance participants
        )


def test_handoff_builder_accepts_all_factory_names_in_add_handoff():
    """Test that add_handoff accepts all factory names when using participant_factories."""

    def create_triage() -> MockHandoffAgent:
        return MockHandoffAgent(name="triage")

    def create_specialist_a() -> MockHandoffAgent:
        return MockHandoffAgent(name="specialist_a")

    def create_specialist_b() -> MockHandoffAgent:
        return MockHandoffAgent(name="specialist_b")

    # This should work - all strings with participant_factories
    builder = (
        HandoffBuilder(
            participant_factories={
                "triage": create_triage,
                "specialist_a": create_specialist_a,
                "specialist_b": create_specialist_b,
            }
        )
        .with_start_agent("triage")
        .add_handoff("triage", ["specialist_a", "specialist_b"])
    )

    workflow = builder.build()
    assert "triage" in workflow.executors
    assert "specialist_a" in workflow.executors
    assert "specialist_b" in workflow.executors


def test_handoff_builder_accepts_all_instances_in_add_handoff():
    """Test that add_handoff accepts all instances when using participants."""
    triage = MockHandoffAgent(name="triage", handoff_to="specialist_a")
    specialist_a = MockHandoffAgent(name="specialist_a")
    specialist_b = MockHandoffAgent(name="specialist_b")

    # This should work - all instances with participants
    builder = (
        HandoffBuilder(participants=[triage, specialist_a, specialist_b])
        .with_start_agent(triage)
        .add_handoff(triage, [specialist_a, specialist_b])
    )

    workflow = builder.build()
    assert "triage" in workflow.executors
    assert "specialist_a" in workflow.executors
    assert "specialist_b" in workflow.executors


async def test_handoff_with_participant_factories():
    """Test workflow creation using participant_factories."""
    call_count = 0

    def create_triage() -> MockHandoffAgent:
        nonlocal call_count
        call_count += 1
        return MockHandoffAgent(name="triage", handoff_to="specialist")

    def create_specialist() -> MockHandoffAgent:
        nonlocal call_count
        call_count += 1
        return MockHandoffAgent(name="specialist")

    workflow = (
        HandoffBuilder(participant_factories={"triage": create_triage, "specialist": create_specialist})
        .with_start_agent("triage")
        .with_termination_condition(lambda conv: sum(1 for m in conv if m.role == Role.USER) >= 2)
        .build()
    )

    # Factories should be called during build
    assert call_count == 2

    events = await _drain(workflow.run_stream("Need help"))
    requests = [ev for ev in events if isinstance(ev, RequestInfoEvent)]
    assert requests

    # Follow-up message
    events = await _drain(
        workflow.send_responses_streaming({requests[-1].request_id: [ChatMessage(role=Role.USER, text="More details")]})
    )
    outputs = [ev for ev in events if isinstance(ev, WorkflowOutputEvent)]
    assert outputs


async def test_handoff_participant_factories_reusable_builder():
    """Test that the builder can be reused to build multiple workflows with factories."""
    call_count = 0

    def create_triage() -> MockHandoffAgent:
        nonlocal call_count
        call_count += 1
        return MockHandoffAgent(name="triage", handoff_to="specialist")

    def create_specialist() -> MockHandoffAgent:
        nonlocal call_count
        call_count += 1
        return MockHandoffAgent(name="specialist")

    builder = HandoffBuilder(
        participant_factories={"triage": create_triage, "specialist": create_specialist}
    ).with_start_agent("triage")

    # Build first workflow
    wf1 = builder.build()
    assert call_count == 2

    # Build second workflow
    wf2 = builder.build()
    assert call_count == 4

    # Verify that the two workflows have different agent instances
    assert wf1.executors["triage"] is not wf2.executors["triage"]
    assert wf1.executors["specialist"] is not wf2.executors["specialist"]


async def test_handoff_with_participant_factories_and_add_handoff():
    """Test that .add_handoff() works correctly with participant_factories."""

    def create_triage() -> MockHandoffAgent:
        return MockHandoffAgent(name="triage", handoff_to="specialist_a")

    def create_specialist_a() -> MockHandoffAgent:
        return MockHandoffAgent(name="specialist_a", handoff_to="specialist_b")

    def create_specialist_b() -> MockHandoffAgent:
        return MockHandoffAgent(name="specialist_b")

    workflow = (
        HandoffBuilder(
            participant_factories={
                "triage": create_triage,
                "specialist_a": create_specialist_a,
                "specialist_b": create_specialist_b,
            }
        )
        .with_start_agent("triage")
        .add_handoff("triage", ["specialist_a", "specialist_b"])
        .add_handoff("specialist_a", ["specialist_b"])
        .with_termination_condition(lambda conv: sum(1 for m in conv if m.role == Role.USER) >= 3)
        .build()
    )

    # Start conversation - triage hands off to specialist_a
    events = await _drain(workflow.run_stream("Initial request"))
    requests = [ev for ev in events if isinstance(ev, RequestInfoEvent)]
    assert requests

    # Verify specialist_a executor exists and was called
    assert "specialist_a" in workflow.executors

    # Second user message - specialist_a hands off to specialist_b
    events = await _drain(
        workflow.send_responses_streaming({
            requests[-1].request_id: [ChatMessage(role=Role.USER, text="Need escalation")]
        })
    )
    requests = [ev for ev in events if isinstance(ev, RequestInfoEvent)]
    assert requests

    # Verify specialist_b executor exists
    assert "specialist_b" in workflow.executors


async def test_handoff_participant_factories_with_checkpointing():
    """Test checkpointing with participant_factories."""
    from agent_framework._workflows._checkpoint import InMemoryCheckpointStorage

    storage = InMemoryCheckpointStorage()

    def create_triage() -> MockHandoffAgent:
        return MockHandoffAgent(name="triage", handoff_to="specialist")

    def create_specialist() -> MockHandoffAgent:
        return MockHandoffAgent(name="specialist")

    workflow = (
        HandoffBuilder(participant_factories={"triage": create_triage, "specialist": create_specialist})
        .with_start_agent("triage")
        .with_checkpointing(storage)
        .with_termination_condition(lambda conv: sum(1 for m in conv if m.role == Role.USER) >= 2)
        .build()
    )

    # Run workflow and capture output
    events = await _drain(workflow.run_stream("checkpoint test"))
    requests = [ev for ev in events if isinstance(ev, RequestInfoEvent)]
    assert requests

    events = await _drain(
        workflow.send_responses_streaming({requests[-1].request_id: [ChatMessage(role=Role.USER, text="follow up")]})
    )
    outputs = [ev for ev in events if isinstance(ev, WorkflowOutputEvent)]
    assert outputs, "Should have workflow output after termination condition is met"

    # List checkpoints - just verify they were created
    checkpoints = await storage.list_checkpoints()
    assert checkpoints, "Checkpoints should be created during workflow execution"


def test_handoff_set_coordinator_with_factory_name():
    """Test that set_coordinator accepts factory name as string."""

    def create_triage() -> MockHandoffAgent:
        return MockHandoffAgent(name="triage")

    def create_specialist() -> MockHandoffAgent:
        return MockHandoffAgent(name="specialist")

    builder = HandoffBuilder(
        participant_factories={"triage": create_triage, "specialist": create_specialist}
    ).with_start_agent("triage")

    workflow = builder.build()
    assert "triage" in workflow.executors


def test_handoff_add_handoff_with_factory_names():
    """Test that add_handoff accepts factory names as strings."""

    def create_triage() -> MockHandoffAgent:
        return MockHandoffAgent(name="triage", handoff_to="specialist_a")

    def create_specialist_a() -> MockHandoffAgent:
        return MockHandoffAgent(name="specialist_a")

    def create_specialist_b() -> MockHandoffAgent:
        return MockHandoffAgent(name="specialist_b")

    builder = (
        HandoffBuilder(
            participant_factories={
                "triage": create_triage,
                "specialist_a": create_specialist_a,
                "specialist_b": create_specialist_b,
            }
        )
        .with_start_agent("triage")
        .add_handoff("triage", ["specialist_a", "specialist_b"])
    )

    workflow = builder.build()
    assert "triage" in workflow.executors
    assert "specialist_a" in workflow.executors
    assert "specialist_b" in workflow.executors


async def test_handoff_participant_factories_autonomous_mode():
    """Test autonomous mode with participant_factories."""

    def create_triage() -> MockHandoffAgent:
        return MockHandoffAgent(name="triage", handoff_to="specialist")

    def create_specialist() -> MockHandoffAgent:
        return MockHandoffAgent(name="specialist")

    workflow = (
        HandoffBuilder(participant_factories={"triage": create_triage, "specialist": create_specialist})
        .with_start_agent("triage")
        .with_autonomous_mode(agents=["specialist"], turn_limits={"specialist": 1})
        .build()
    )

    events = await _drain(workflow.run_stream("Issue"))
    requests = [ev for ev in events if isinstance(ev, RequestInfoEvent)]
    assert requests and len(requests) == 1
    assert requests[0].source_executor_id == "specialist"


def test_handoff_participant_factories_invalid_coordinator_name():
    """Test that set_coordinator raises error for non-existent factory name."""

    def create_triage() -> MockHandoffAgent:
        return MockHandoffAgent(name="triage")

    with pytest.raises(
        ValueError, match="Start agent factory name 'nonexistent' is not in the participant_factories list"
    ):
        (HandoffBuilder(participant_factories={"triage": create_triage}).with_start_agent("nonexistent").build())


def test_handoff_participant_factories_invalid_handoff_target():
    """Test that add_handoff raises error for non-existent target factory name."""

    def create_triage() -> MockHandoffAgent:
        return MockHandoffAgent(name="triage")

    def create_specialist() -> MockHandoffAgent:
        return MockHandoffAgent(name="specialist")

    with pytest.raises(ValueError, match="Target factory name 'nonexistent' is not in the participant_factories list"):
        (
            HandoffBuilder(participant_factories={"triage": create_triage, "specialist": create_specialist})
            .with_start_agent("triage")
            .add_handoff("triage", ["nonexistent"])
            .build()
        )


# endregion Participant Factory Tests
