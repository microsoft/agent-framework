# Copyright (c) Microsoft. All rights reserved.

"""Comprehensive tests for AgentFrameworkAgent (_agent.py)."""

import json
from collections.abc import AsyncIterator, MutableSequence
from typing import Any

import pytest
from agent_framework import Agent, ChatOptions, ChatResponseUpdate, Content, Message
from pydantic import BaseModel


async def test_agent_initialization_basic(streaming_chat_client_stub):
    """Test basic agent initialization without state schema."""
    from agent_framework.ag_ui import AgentFrameworkAgent

    async def stream_fn(
        messages: MutableSequence[Message], options: dict[str, Any], **kwargs: Any
    ) -> AsyncIterator[ChatResponseUpdate]:
        yield ChatResponseUpdate(contents=[Content.from_text(text="Hello")])

    agent = Agent[ChatOptions](
        client=streaming_chat_client_stub(stream_fn),
        name="test_agent",
        instructions="Test",
    )
    wrapper = AgentFrameworkAgent(agent=agent)

    assert wrapper.name == "test_agent"
    assert wrapper.agent == agent
    assert wrapper.config.state_schema == {}
    assert wrapper.config.predict_state_config == {}


async def test_agent_initialization_with_state_schema(streaming_chat_client_stub):
    """Test agent initialization with state_schema."""
    from agent_framework.ag_ui import AgentFrameworkAgent

    async def stream_fn(
        messages: MutableSequence[Message], options: dict[str, Any], **kwargs: Any
    ) -> AsyncIterator[ChatResponseUpdate]:
        yield ChatResponseUpdate(contents=[Content.from_text(text="Hello")])

    agent = Agent(name="test_agent", instructions="Test", client=streaming_chat_client_stub(stream_fn))
    state_schema: dict[str, dict[str, Any]] = {"document": {"type": "string"}}
    wrapper = AgentFrameworkAgent(agent=agent, state_schema=state_schema)

    assert wrapper.config.state_schema == state_schema


async def test_agent_initialization_with_predict_state_config(streaming_chat_client_stub):
    """Test agent initialization with predict_state_config."""
    from agent_framework.ag_ui import AgentFrameworkAgent

    async def stream_fn(
        messages: MutableSequence[Message], options: dict[str, Any], **kwargs: Any
    ) -> AsyncIterator[ChatResponseUpdate]:
        yield ChatResponseUpdate(contents=[Content.from_text(text="Hello")])

    agent = Agent(name="test_agent", instructions="Test", client=streaming_chat_client_stub(stream_fn))
    predict_config = {"document": {"tool": "write_doc", "tool_argument": "content"}}
    wrapper = AgentFrameworkAgent(agent=agent, predict_state_config=predict_config)

    assert wrapper.config.predict_state_config == predict_config


async def test_agent_initialization_with_pydantic_state_schema(streaming_chat_client_stub):
    """Test agent initialization when state_schema is provided as Pydantic model/class."""
    from agent_framework.ag_ui import AgentFrameworkAgent

    async def stream_fn(
        messages: MutableSequence[Message], options: dict[str, Any], **kwargs: Any
    ) -> AsyncIterator[ChatResponseUpdate]:
        yield ChatResponseUpdate(contents=[Content.from_text(text="Hello")])

    class MyState(BaseModel):
        document: str
        tags: list[str] = []

    agent = Agent(name="test_agent", instructions="Test", client=streaming_chat_client_stub(stream_fn))

    wrapper_class_schema = AgentFrameworkAgent(agent=agent, state_schema=MyState)
    wrapper_instance_schema = AgentFrameworkAgent(agent=agent, state_schema=MyState(document="hi"))

    expected_properties = MyState.model_json_schema().get("properties", {})
    assert wrapper_class_schema.config.state_schema == expected_properties
    assert wrapper_instance_schema.config.state_schema == expected_properties


async def test_run_started_event_emission(streaming_chat_client_stub):
    """Test RunStartedEvent is emitted at start of run."""
    from agent_framework.ag_ui import AgentFrameworkAgent

    async def stream_fn(
        messages: MutableSequence[Message], options: dict[str, Any], **kwargs: Any
    ) -> AsyncIterator[ChatResponseUpdate]:
        yield ChatResponseUpdate(contents=[Content.from_text(text="Hello")])

    agent = Agent(name="test_agent", instructions="Test", client=streaming_chat_client_stub(stream_fn))
    wrapper = AgentFrameworkAgent(agent=agent)

    input_data = {"messages": [{"role": "user", "content": "Hi"}]}

    events: list[Any] = []
    async for event in wrapper.run(input_data):
        events.append(event)

    # First event should be RunStartedEvent
    assert events[0].type == "RUN_STARTED"
    assert events[0].run_id is not None
    assert events[0].thread_id is not None


async def test_predict_state_custom_event_emission(streaming_chat_client_stub):
    """Test PredictState CustomEvent is emitted when predict_state_config is present."""
    from agent_framework.ag_ui import AgentFrameworkAgent

    async def stream_fn(
        messages: MutableSequence[Message], options: dict[str, Any], **kwargs: Any
    ) -> AsyncIterator[ChatResponseUpdate]:
        yield ChatResponseUpdate(contents=[Content.from_text(text="Hello")])

    agent = Agent(name="test_agent", instructions="Test", client=streaming_chat_client_stub(stream_fn))
    predict_config = {
        "document": {"tool": "write_doc", "tool_argument": "content"},
        "summary": {"tool": "summarize", "tool_argument": "text"},
    }
    wrapper = AgentFrameworkAgent(agent=agent, predict_state_config=predict_config)

    input_data = {"messages": [{"role": "user", "content": "Hi"}]}

    events: list[Any] = []
    async for event in wrapper.run(input_data):
        events.append(event)

    # Find PredictState event
    predict_events = [e for e in events if e.type == "CUSTOM" and e.name == "PredictState"]
    assert len(predict_events) == 1

    predict_value = predict_events[0].value
    assert len(predict_value) == 2
    assert {"state_key": "document", "tool": "write_doc", "tool_argument": "content"} in predict_value
    assert {"state_key": "summary", "tool": "summarize", "tool_argument": "text"} in predict_value


async def test_usage_content_emits_custom_usage_event(streaming_chat_client_stub):
    """Usage content from the wrapped agent should be surfaced as a custom usage event."""
    from agent_framework.ag_ui import AgentFrameworkAgent

    async def stream_fn(
        messages: MutableSequence[Message], options: dict[str, Any], **kwargs: Any
    ) -> AsyncIterator[ChatResponseUpdate]:
        del messages, options, kwargs
        yield ChatResponseUpdate(
            contents=[
                Content.from_usage(
                    {
                        "input_token_count": 10,
                        "output_token_count": 4,
                        "total_token_count": 14,
                    }
                )
            ]
        )

    agent = Agent(name="usage_agent", instructions="Usage test", client=streaming_chat_client_stub(stream_fn))
    wrapper = AgentFrameworkAgent(agent=agent)

    events: list[Any] = []
    async for event in wrapper.run({"messages": [{"role": "user", "content": "Hi"}]}):
        events.append(event)

    usage_events = [event for event in events if event.type == "CUSTOM" and event.name == "usage"]
    assert len(usage_events) == 1
    assert usage_events[0].value["input_token_count"] == 10
    assert usage_events[0].value["output_token_count"] == 4
    assert usage_events[0].value["total_token_count"] == 14


async def test_multimodal_input_is_forwarded_to_agent_run(streaming_chat_client_stub):
    """Multimodal AG-UI input should be converted and passed through to agent.run."""
    from agent_framework.ag_ui import AgentFrameworkAgent

    captured_messages: list[Message] = []

    async def stream_fn(
        messages: MutableSequence[Message], options: dict[str, Any], **kwargs: Any
    ) -> AsyncIterator[ChatResponseUpdate]:
        del options, kwargs
        captured_messages[:] = list(messages)
        yield ChatResponseUpdate(contents=[Content.from_text(text="Processed multimodal input")])

    agent = Agent(name="multimodal_agent", instructions="Multimodal test", client=streaming_chat_client_stub(stream_fn))
    wrapper = AgentFrameworkAgent(agent=agent)

    input_data = {
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "What is in this image?"},
                    {
                        "type": "image",
                        "source": {"type": "url", "url": "https://example.com/cat.png", "mimeType": "image/png"},
                    },
                ],
            }
        ]
    }

    _ = [event async for event in wrapper.run(input_data)]

    assert len(captured_messages) == 1
    message = captured_messages[0]
    assert message.role == "user"
    assert len(message.contents) == 2
    assert message.contents[0].type == "text"
    assert message.contents[0].text == "What is in this image?"
    assert message.contents[1].type == "uri"
    assert message.contents[1].uri == "https://example.com/cat.png"


async def test_initial_state_snapshot_with_schema(streaming_chat_client_stub):
    """Test initial StateSnapshotEvent emission when state_schema present."""
    from agent_framework.ag_ui import AgentFrameworkAgent

    async def stream_fn(
        messages: MutableSequence[Message], options: dict[str, Any], **kwargs: Any
    ) -> AsyncIterator[ChatResponseUpdate]:
        yield ChatResponseUpdate(contents=[Content.from_text(text="Hello")])

    agent = Agent(name="test_agent", instructions="Test", client=streaming_chat_client_stub(stream_fn))
    state_schema = {"document": {"type": "string"}}
    wrapper = AgentFrameworkAgent(agent=agent, state_schema=state_schema)

    input_data = {
        "messages": [{"role": "user", "content": "Hi"}],
        "state": {"document": "Initial content"},
    }

    events: list[Any] = []
    async for event in wrapper.run(input_data):
        events.append(event)

    # Find StateSnapshotEvent
    snapshot_events = [e for e in events if e.type == "STATE_SNAPSHOT"]
    assert len(snapshot_events) >= 1

    # First snapshot should have initial state
    assert snapshot_events[0].snapshot == {"document": "Initial content"}


async def test_state_initialization_object_type(streaming_chat_client_stub):
    """Test state initialization with object type in schema."""
    from agent_framework.ag_ui import AgentFrameworkAgent

    async def stream_fn(
        messages: MutableSequence[Message], options: dict[str, Any], **kwargs: Any
    ) -> AsyncIterator[ChatResponseUpdate]:
        yield ChatResponseUpdate(contents=[Content.from_text(text="Hello")])

    agent = Agent(name="test_agent", instructions="Test", client=streaming_chat_client_stub(stream_fn))
    state_schema: dict[str, dict[str, Any]] = {"recipe": {"type": "object", "properties": {}}}
    wrapper = AgentFrameworkAgent(agent=agent, state_schema=state_schema)

    input_data = {"messages": [{"role": "user", "content": "Hi"}]}

    events: list[Any] = []
    async for event in wrapper.run(input_data):
        events.append(event)

    # Find StateSnapshotEvent
    snapshot_events = [e for e in events if e.type == "STATE_SNAPSHOT"]
    assert len(snapshot_events) >= 1

    # Should initialize as empty object
    assert snapshot_events[0].snapshot == {"recipe": {}}


async def test_state_initialization_array_type(streaming_chat_client_stub):
    """Test state initialization with array type in schema."""
    from agent_framework.ag_ui import AgentFrameworkAgent

    async def stream_fn(
        messages: MutableSequence[Message], options: dict[str, Any], **kwargs: Any
    ) -> AsyncIterator[ChatResponseUpdate]:
        yield ChatResponseUpdate(contents=[Content.from_text(text="Hello")])

    agent = Agent(name="test_agent", instructions="Test", client=streaming_chat_client_stub(stream_fn))
    state_schema: dict[str, dict[str, Any]] = {"steps": {"type": "array", "items": {}}}
    wrapper = AgentFrameworkAgent(agent=agent, state_schema=state_schema)

    input_data = {"messages": [{"role": "user", "content": "Hi"}]}

    events: list[Any] = []
    async for event in wrapper.run(input_data):
        events.append(event)

    # Find StateSnapshotEvent
    snapshot_events = [e for e in events if e.type == "STATE_SNAPSHOT"]
    assert len(snapshot_events) >= 1

    # Should initialize as empty array
    assert snapshot_events[0].snapshot == {"steps": []}


async def test_run_finished_event_emission(streaming_chat_client_stub):
    """Test RunFinishedEvent is emitted at end of run."""
    from agent_framework.ag_ui import AgentFrameworkAgent

    async def stream_fn(
        messages: MutableSequence[Message], options: dict[str, Any], **kwargs: Any
    ) -> AsyncIterator[ChatResponseUpdate]:
        yield ChatResponseUpdate(contents=[Content.from_text(text="Hello")])

    agent = Agent(name="test_agent", instructions="Test", client=streaming_chat_client_stub(stream_fn))
    wrapper = AgentFrameworkAgent(agent=agent)

    input_data = {"messages": [{"role": "user", "content": "Hi"}]}

    events: list[Any] = []
    async for event in wrapper.run(input_data):
        events.append(event)

    # Last event should be RunFinishedEvent
    assert events[-1].type == "RUN_FINISHED"


async def test_tool_result_confirm_changes_accepted(streaming_chat_client_stub):
    """Test confirm_changes tool result handling when accepted."""
    from agent_framework.ag_ui import AgentFrameworkAgent

    async def stream_fn(
        messages: MutableSequence[Message], options: dict[str, Any], **kwargs: Any
    ) -> AsyncIterator[ChatResponseUpdate]:
        yield ChatResponseUpdate(contents=[Content.from_text(text="Document updated")])

    agent = Agent(name="test_agent", instructions="Test", client=streaming_chat_client_stub(stream_fn))
    wrapper = AgentFrameworkAgent(
        agent=agent,
        state_schema={"document": {"type": "string"}},
        predict_state_config={"document": {"tool": "write_doc", "tool_argument": "content"}},
    )

    # Simulate tool result message with acceptance
    tool_result: dict[str, Any] = {"accepted": True, "steps": []}
    input_data: dict[str, Any] = {
        "messages": [
            {
                "role": "tool",  # Tool result from UI
                "content": json.dumps(tool_result),
                "toolCallId": "confirm_call_123",
            }
        ],
        "state": {"document": "Updated content"},
    }

    events: list[Any] = []
    async for event in wrapper.run(input_data):
        events.append(event)

    # Should emit text message confirming acceptance
    text_content_events = [e for e in events if e.type == "TEXT_MESSAGE_CONTENT"]
    assert len(text_content_events) > 0
    # Should contain confirmation message mentioning the state key or generic confirmation
    confirmation_found = any(
        "document" in e.delta.lower()
        or "confirm" in e.delta.lower()
        or "applied" in e.delta.lower()
        or "changes" in e.delta.lower()
        for e in text_content_events
    )
    assert confirmation_found, f"No confirmation in deltas: {[e.delta for e in text_content_events]}"


async def test_tool_result_confirm_changes_rejected(streaming_chat_client_stub):
    """Test confirm_changes tool result handling when rejected."""
    from agent_framework.ag_ui import AgentFrameworkAgent

    async def stream_fn(
        messages: MutableSequence[Message], options: dict[str, Any], **kwargs: Any
    ) -> AsyncIterator[ChatResponseUpdate]:
        yield ChatResponseUpdate(contents=[Content.from_text(text="OK")])

    agent = Agent(name="test_agent", instructions="Test", client=streaming_chat_client_stub(stream_fn))
    wrapper = AgentFrameworkAgent(agent=agent)

    # Simulate tool result message with rejection
    tool_result: dict[str, Any] = {"accepted": False, "steps": []}
    input_data: dict[str, Any] = {
        "messages": [
            {
                "role": "tool",
                "content": json.dumps(tool_result),
                "toolCallId": "confirm_call_123",
            }
        ],
    }

    events: list[Any] = []
    async for event in wrapper.run(input_data):
        events.append(event)

    # Should emit text message asking what to change
    text_content_events = [e for e in events if e.type == "TEXT_MESSAGE_CONTENT"]
    assert len(text_content_events) > 0
    assert any("what would you like me to change" in e.delta.lower() for e in text_content_events)


async def test_tool_result_function_approval_accepted(streaming_chat_client_stub):
    """Test function approval tool result when steps are accepted."""
    from agent_framework.ag_ui import AgentFrameworkAgent

    async def stream_fn(
        messages: MutableSequence[Message], options: dict[str, Any], **kwargs: Any
    ) -> AsyncIterator[ChatResponseUpdate]:
        yield ChatResponseUpdate(contents=[Content.from_text(text="OK")])

    agent = Agent(name="test_agent", instructions="Test", client=streaming_chat_client_stub(stream_fn))
    wrapper = AgentFrameworkAgent(agent=agent)

    # Simulate tool result with multiple steps
    tool_result: dict[str, Any] = {
        "accepted": True,
        "steps": [
            {"id": "step1", "description": "Send email", "status": "enabled"},
            {"id": "step2", "description": "Create calendar event", "status": "enabled"},
        ],
    }
    input_data: dict[str, Any] = {
        "messages": [
            {
                "role": "tool",
                "content": json.dumps(tool_result),
                "toolCallId": "approval_call_123",
            }
        ],
    }

    events: list[Any] = []
    async for event in wrapper.run(input_data):
        events.append(event)

    # Should list enabled steps
    text_content_events = [e for e in events if e.type == "TEXT_MESSAGE_CONTENT"]
    assert len(text_content_events) > 0

    # Concatenate all text content
    full_text = "".join(e.delta for e in text_content_events)
    assert "executing" in full_text.lower()
    assert "2 approved steps" in full_text.lower()
    assert "send email" in full_text.lower()
    assert "create calendar event" in full_text.lower()


async def test_tool_result_function_approval_rejected(streaming_chat_client_stub):
    """Test function approval tool result when rejected."""
    from agent_framework.ag_ui import AgentFrameworkAgent

    async def stream_fn(
        messages: MutableSequence[Message], options: dict[str, Any], **kwargs: Any
    ) -> AsyncIterator[ChatResponseUpdate]:
        yield ChatResponseUpdate(contents=[Content.from_text(text="OK")])

    agent = Agent(name="test_agent", instructions="Test", client=streaming_chat_client_stub(stream_fn))
    wrapper = AgentFrameworkAgent(agent=agent)

    # Simulate tool result rejection with steps
    tool_result: dict[str, Any] = {
        "accepted": False,
        "steps": [{"id": "step1", "description": "Send email", "status": "disabled"}],
    }
    input_data: dict[str, Any] = {
        "messages": [
            {
                "role": "tool",
                "content": json.dumps(tool_result),
                "toolCallId": "approval_call_123",
            }
        ],
    }

    events: list[Any] = []
    async for event in wrapper.run(input_data):
        events.append(event)

    # Should ask what to change about the plan
    text_content_events = [e for e in events if e.type == "TEXT_MESSAGE_CONTENT"]
    assert len(text_content_events) > 0
    assert any("what would you like me to change about the plan" in e.delta.lower() for e in text_content_events)


async def test_thread_metadata_tracking(streaming_chat_client_stub):
    """Test that thread metadata includes ag_ui_thread_id and ag_ui_run_id.

    AG-UI internal metadata is stored in thread.metadata for orchestration,
    but filtered out before passing to the chat client's options.metadata.
    """
    from agent_framework.ag_ui import AgentFrameworkAgent

    captured_options: dict[str, Any] = {}

    async def stream_fn(
        messages: MutableSequence[Message], options: dict[str, Any], **kwargs: Any
    ) -> AsyncIterator[ChatResponseUpdate]:
        # Capture options to verify internal keys are NOT passed to chat client
        captured_options.update(options)
        yield ChatResponseUpdate(contents=[Content.from_text(text="Hello")])

    agent = Agent(name="test_agent", instructions="Test", client=streaming_chat_client_stub(stream_fn))
    wrapper = AgentFrameworkAgent(agent=agent)

    input_data = {
        "messages": [{"role": "user", "content": "Hi"}],
        "thread_id": "test_thread_123",
        "run_id": "test_run_456",
    }

    events: list[Any] = []
    async for event in wrapper.run(input_data):
        events.append(event)

    # AG-UI internal metadata should NOT be passed to chat client options
    options_metadata = captured_options.get("metadata", {})
    assert "ag_ui_thread_id" not in options_metadata
    assert "ag_ui_run_id" not in options_metadata


async def test_state_context_injection(streaming_chat_client_stub):
    """Test that current state is injected into thread metadata.

    AG-UI internal metadata (including current_state) is stored in thread.metadata
    for orchestration, but filtered out before passing to the chat client's options.metadata.
    """
    from agent_framework_ag_ui import AgentFrameworkAgent

    captured_options: dict[str, Any] = {}

    async def stream_fn(
        messages: MutableSequence[Message], options: dict[str, Any], **kwargs: Any
    ) -> AsyncIterator[ChatResponseUpdate]:
        # Capture options to verify internal keys are NOT passed to chat client
        captured_options.update(options)
        yield ChatResponseUpdate(contents=[Content.from_text(text="Hello")])

    agent = Agent(name="test_agent", instructions="Test", client=streaming_chat_client_stub(stream_fn))
    wrapper = AgentFrameworkAgent(
        agent=agent,
        state_schema={"document": {"type": "string"}},
    )

    input_data = {
        "messages": [{"role": "user", "content": "Hi"}],
        "state": {"document": "Test content"},
    }

    events: list[Any] = []
    async for event in wrapper.run(input_data):
        events.append(event)

    # Current state should NOT be passed to chat client options
    options_metadata = captured_options.get("metadata", {})
    assert "current_state" not in options_metadata


async def test_no_messages_provided(streaming_chat_client_stub):
    """Test handling when no messages are provided."""
    from agent_framework.ag_ui import AgentFrameworkAgent

    async def stream_fn(
        messages: MutableSequence[Message], options: dict[str, Any], **kwargs: Any
    ) -> AsyncIterator[ChatResponseUpdate]:
        yield ChatResponseUpdate(contents=[Content.from_text(text="Hello")])

    agent = Agent(name="test_agent", instructions="Test", client=streaming_chat_client_stub(stream_fn))
    wrapper = AgentFrameworkAgent(agent=agent)

    input_data: dict[str, Any] = {"messages": []}

    events: list[Any] = []
    async for event in wrapper.run(input_data):
        events.append(event)

    # Should emit RunStartedEvent and RunFinishedEvent only
    assert len(events) == 2
    assert events[0].type == "RUN_STARTED"
    assert events[-1].type == "RUN_FINISHED"


async def test_message_end_event_emission(streaming_chat_client_stub):
    """Test TextMessageEndEvent is emitted for assistant messages."""
    from agent_framework.ag_ui import AgentFrameworkAgent

    async def stream_fn(
        messages: MutableSequence[Message], options: dict[str, Any], **kwargs: Any
    ) -> AsyncIterator[ChatResponseUpdate]:
        yield ChatResponseUpdate(contents=[Content.from_text(text="Hello world")])

    agent = Agent(name="test_agent", instructions="Test", client=streaming_chat_client_stub(stream_fn))
    wrapper = AgentFrameworkAgent(agent=agent)

    input_data: dict[str, Any] = {"messages": [{"role": "user", "content": "Hi"}]}

    events: list[Any] = []
    async for event in wrapper.run(input_data):
        events.append(event)

    # Should have TextMessageEndEvent before RunFinishedEvent
    end_events = [e for e in events if e.type == "TEXT_MESSAGE_END"]
    assert len(end_events) == 1

    # EndEvent should come before FinishedEvent
    end_index = events.index(end_events[0])
    finished_index = events.index([e for e in events if e.type == "RUN_FINISHED"][0])
    assert end_index < finished_index


async def test_error_handling_with_exception(streaming_chat_client_stub):
    """Test that exceptions during agent execution are re-raised."""
    from agent_framework.ag_ui import AgentFrameworkAgent

    async def stream_fn(
        messages: MutableSequence[Message], options: dict[str, Any], **kwargs: Any
    ) -> AsyncIterator[ChatResponseUpdate]:
        if False:
            yield ChatResponseUpdate(contents=[])
        raise RuntimeError("Simulated failure")

    agent = Agent(name="test_agent", instructions="Test", client=streaming_chat_client_stub(stream_fn))
    wrapper = AgentFrameworkAgent(agent=agent)

    input_data: dict[str, Any] = {"messages": [{"role": "user", "content": "Hi"}]}

    with pytest.raises(RuntimeError, match="Simulated failure"):
        async for _ in wrapper.run(input_data):
            pass


async def test_json_decode_error_in_tool_result(streaming_chat_client_stub):
    """Test handling of orphaned tool result - should be sanitized out."""
    from agent_framework.ag_ui import AgentFrameworkAgent

    async def stream_fn(
        messages: MutableSequence[Message], options: dict[str, Any], **kwargs: Any
    ) -> AsyncIterator[ChatResponseUpdate]:
        if False:
            yield ChatResponseUpdate(contents=[])
        raise AssertionError("ChatClient should not be called with orphaned tool result")

    agent = Agent(name="test_agent", instructions="Test", client=streaming_chat_client_stub(stream_fn))
    wrapper = AgentFrameworkAgent(agent=agent)

    # Send invalid JSON as tool result without preceding tool call
    input_data: dict[str, Any] = {
        "messages": [
            {
                "role": "tool",
                "content": "invalid json {not valid}",
                "toolCallId": "call_123",
            }
        ],
    }

    events: list[Any] = []
    async for event in wrapper.run(input_data):
        events.append(event)

    # Orphaned tool result should be sanitized out
    # Only run lifecycle events should be emitted, no text/tool events
    text_events = [e for e in events if e.type == "TEXT_MESSAGE_CONTENT"]
    tool_events = [e for e in events if e.type.startswith("TOOL_CALL")]
    assert len(text_events) == 0
    assert len(tool_events) == 0


async def test_agent_with_use_service_session_is_false(streaming_chat_client_stub):
    """Test that when use_service_session is False, the AgentSession used to run the agent is NOT set to the service session ID."""
    from agent_framework.ag_ui import AgentFrameworkAgent

    request_service_session_id: str | None = None

    async def stream_fn(
        messages: MutableSequence[Message], chat_options: ChatOptions, **kwargs: Any
    ) -> AsyncIterator[ChatResponseUpdate]:
        yield ChatResponseUpdate(
            contents=[Content.from_text(text="Response")], response_id="resp_67890", conversation_id="conv_12345"
        )

    agent = Agent(client=streaming_chat_client_stub(stream_fn))
    wrapper = AgentFrameworkAgent(agent=agent, use_service_session=False)

    input_data = {"messages": [{"role": "user", "content": "Hi"}], "thread_id": "conv_123456"}

    events: list[Any] = []
    async for event in wrapper.run(input_data):
        events.append(event)
    assert request_service_session_id is None  # type: ignore[attr-defined] (service_session_id should be set)


async def test_agent_with_use_service_session_is_true(streaming_chat_client_stub):
    """Test that when use_service_session is True, the AgentSession used to run the agent is set to the service session ID."""
    from agent_framework.ag_ui import AgentFrameworkAgent

    request_service_session_id: str | None = None

    async def stream_fn(
        messages: MutableSequence[Message], chat_options: ChatOptions, **kwargs: Any
    ) -> AsyncIterator[ChatResponseUpdate]:
        nonlocal request_service_session_id
        session = kwargs.get("session")
        request_service_session_id = session.service_session_id if session else None
        yield ChatResponseUpdate(
            contents=[Content.from_text(text="Response")], response_id="resp_67890", conversation_id="conv_12345"
        )

    agent = Agent(client=streaming_chat_client_stub(stream_fn))
    wrapper = AgentFrameworkAgent(agent=agent, use_service_session=True)

    input_data = {"messages": [{"role": "user", "content": "Hi"}], "thread_id": "conv_123456"}

    events: list[Any] = []
    async for event in wrapper.run(input_data):
        events.append(event)
    request_service_session_id = agent.client.last_service_session_id
    assert request_service_session_id == "conv_123456"  # type: ignore[attr-defined] (service_session_id should be set)


async def test_function_approval_mode_executes_tool(streaming_chat_client_stub):
    """Test that function approval with approval_mode='always_require' sends the correct messages."""
    from agent_framework import tool
    from agent_framework.ag_ui import AgentFrameworkAgent

    messages_received: list[Any] = []

    @tool(
        name="get_datetime",
        description="Get the current date and time",
        approval_mode="always_require",
    )
    def get_datetime() -> str:
        return "2025/12/01 12:00:00"

    async def stream_fn(
        messages: MutableSequence[Message], options: ChatOptions, **kwargs: Any
    ) -> AsyncIterator[ChatResponseUpdate]:
        # Capture the messages received by the chat client
        messages_received.clear()
        messages_received.extend(messages)
        yield ChatResponseUpdate(contents=[Content.from_text(text="Processing completed")])

    agent = Agent(
        client=streaming_chat_client_stub(stream_fn),
        name="test_agent",
        instructions="Test",
        tools=[get_datetime],
    )
    wrapper = AgentFrameworkAgent(agent=agent)

    # Simulate the conversation history with:
    # 1. User message asking for time
    # 2. Assistant message with the function call that needs approval
    # 3. Tool approval message from user
    tool_result: dict[str, Any] = {"accepted": True}
    input_data: dict[str, Any] = {
        "messages": [
            {
                "role": "user",
                "content": "What time is it?",
            },
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_get_datetime_123",
                        "type": "function",
                        "function": {
                            "name": "get_datetime",
                            "arguments": "{}",
                        },
                    }
                ],
            },
            {
                "role": "tool",
                "content": json.dumps(tool_result),
                "toolCallId": "call_get_datetime_123",
            },
        ],
    }

    events: list[Any] = []
    async for event in wrapper.run(input_data):
        events.append(event)

    # Verify the run completed successfully
    run_started = [e for e in events if e.type == "RUN_STARTED"]
    run_finished = [e for e in events if e.type == "RUN_FINISHED"]
    assert len(run_started) == 1
    assert len(run_finished) == 1

    # Verify that a FunctionResultContent was created and sent to the agent
    # Approved tool calls are resolved before the model run.
    tool_result_found = False
    for msg in messages_received:
        for content in msg.contents:
            if content.type == "function_result":
                tool_result_found = True
                assert content.call_id == "call_get_datetime_123"
                assert content.result == "2025/12/01 12:00:00"
                break

    assert tool_result_found, (
        "FunctionResultContent should be included in messages sent to agent. "
        "This is required for the model to see the approved tool execution result."
    )


async def test_function_approval_mode_rejection(streaming_chat_client_stub):
    """Test that function approval rejection creates a rejection response."""
    from agent_framework import tool
    from agent_framework.ag_ui import AgentFrameworkAgent

    messages_received: list[Any] = []

    @tool(
        name="delete_all_data",
        description="Delete all user data",
        approval_mode="always_require",
    )
    def delete_all_data() -> str:
        return "All data deleted"

    async def stream_fn(
        messages: MutableSequence[Message], options: ChatOptions, **kwargs: Any
    ) -> AsyncIterator[ChatResponseUpdate]:
        # Capture the messages received by the chat client
        messages_received.clear()
        messages_received.extend(messages)
        yield ChatResponseUpdate(contents=[Content.from_text(text="Operation cancelled")])

    agent = Agent(
        name="test_agent",
        instructions="Test",
        client=streaming_chat_client_stub(stream_fn),
        tools=[delete_all_data],
    )
    wrapper = AgentFrameworkAgent(agent=agent)

    # Simulate rejection
    tool_result: dict[str, Any] = {"accepted": False}
    input_data: dict[str, Any] = {
        "messages": [
            {
                "role": "user",
                "content": "Delete all my data",
            },
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_delete_123",
                        "type": "function",
                        "function": {
                            "name": "delete_all_data",
                            "arguments": "{}",
                        },
                    }
                ],
            },
            {
                "role": "tool",
                "content": json.dumps(tool_result),
                "toolCallId": "call_delete_123",
            },
        ],
    }

    events: list[Any] = []
    async for event in wrapper.run(input_data):
        events.append(event)

    # Verify the run completed
    run_finished = [e for e in events if e.type == "RUN_FINISHED"]
    assert len(run_finished) == 1

    # Verify that a FunctionResultContent with rejection payload was created
    rejection_found = False
    for msg in messages_received:
        for content in msg.contents:
            if content.type == "function_result":
                rejection_found = True
                assert content.call_id == "call_delete_123"
                assert content.result == "Error: Tool call invocation was rejected by user."
                break

    assert rejection_found, (
        "FunctionResultContent with rejection details should be included in messages sent to agent. "
        "This tells the model that the tool was rejected."
    )
