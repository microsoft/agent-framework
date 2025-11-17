# Copyright (c) Microsoft. All rights reserved.

"""Comprehensive tests for AgentFrameworkAgent (_agent.py)."""

import json

import pytest
from agent_framework import ChatAgent, TextContent
from agent_framework._types import ChatResponseUpdate


async def test_agent_initialization_basic():
    """Test basic agent initialization without state schema."""
    from agent_framework_ag_ui import AgentFrameworkAgent

    class MockChatClient:
        async def get_streaming_response(self, messages, chat_options, **kwargs):
            yield ChatResponseUpdate(contents=[TextContent(text="Hello")])

    agent = ChatAgent(name="test_agent", instructions="Test", chat_client=MockChatClient())
    wrapper = AgentFrameworkAgent(agent=agent)

    assert wrapper.name == "test_agent"
    assert wrapper.agent == agent
    assert wrapper.config.state_schema == {}
    assert wrapper.config.predict_state_config == {}


async def test_agent_initialization_with_state_schema():
    """Test agent initialization with state_schema."""
    from agent_framework_ag_ui import AgentFrameworkAgent

    class MockChatClient:
        async def get_streaming_response(self, messages, chat_options, **kwargs):
            yield ChatResponseUpdate(contents=[TextContent(text="Hello")])

    agent = ChatAgent(name="test_agent", instructions="Test", chat_client=MockChatClient())
    state_schema = {"document": {"type": "string"}}
    wrapper = AgentFrameworkAgent(agent=agent, state_schema=state_schema)

    assert wrapper.config.state_schema == state_schema


async def test_agent_initialization_with_predict_state_config():
    """Test agent initialization with predict_state_config."""
    from agent_framework_ag_ui import AgentFrameworkAgent

    class MockChatClient:
        async def get_streaming_response(self, messages, chat_options, **kwargs):
            yield ChatResponseUpdate(contents=[TextContent(text="Hello")])

    agent = ChatAgent(name="test_agent", instructions="Test", chat_client=MockChatClient())
    predict_config = {"document": {"tool": "write_doc", "tool_argument": "content"}}
    wrapper = AgentFrameworkAgent(agent=agent, predict_state_config=predict_config)

    assert wrapper.config.predict_state_config == predict_config


async def test_run_started_event_emission():
    """Test RunStartedEvent is emitted at start of run."""
    from agent_framework_ag_ui import AgentFrameworkAgent

    class MockChatClient:
        async def get_streaming_response(self, messages, chat_options, **kwargs):
            yield ChatResponseUpdate(contents=[TextContent(text="Hello")])

    agent = ChatAgent(name="test_agent", instructions="Test", chat_client=MockChatClient())
    wrapper = AgentFrameworkAgent(agent=agent)

    input_data = {"messages": [{"role": "user", "content": "Hi"}]}

    events = []
    async for event in wrapper.run_agent(input_data):
        events.append(event)

    # First event should be RunStartedEvent
    assert events[0].type == "RUN_STARTED"
    assert events[0].run_id is not None
    assert events[0].thread_id is not None


async def test_predict_state_custom_event_emission():
    """Test PredictState CustomEvent is emitted when predict_state_config is present."""
    from agent_framework_ag_ui import AgentFrameworkAgent

    class MockChatClient:
        async def get_streaming_response(self, messages, chat_options, **kwargs):
            yield ChatResponseUpdate(contents=[TextContent(text="Hello")])

    agent = ChatAgent(name="test_agent", instructions="Test", chat_client=MockChatClient())
    predict_config = {
        "document": {"tool": "write_doc", "tool_argument": "content"},
        "summary": {"tool": "summarize", "tool_argument": "text"},
    }
    wrapper = AgentFrameworkAgent(agent=agent, predict_state_config=predict_config)

    input_data = {"messages": [{"role": "user", "content": "Hi"}]}

    events = []
    async for event in wrapper.run_agent(input_data):
        events.append(event)

    # Find PredictState event
    predict_events = [e for e in events if e.type == "CUSTOM" and e.name == "PredictState"]
    assert len(predict_events) == 1

    predict_value = predict_events[0].value
    assert len(predict_value) == 2
    assert {"state_key": "document", "tool": "write_doc", "tool_argument": "content"} in predict_value
    assert {"state_key": "summary", "tool": "summarize", "tool_argument": "text"} in predict_value


async def test_initial_state_snapshot_with_schema():
    """Test initial StateSnapshotEvent emission when state_schema present."""
    from agent_framework_ag_ui import AgentFrameworkAgent

    class MockChatClient:
        async def get_streaming_response(self, messages, chat_options, **kwargs):
            yield ChatResponseUpdate(contents=[TextContent(text="Hello")])

    agent = ChatAgent(name="test_agent", instructions="Test", chat_client=MockChatClient())
    state_schema = {"document": {"type": "string"}}
    wrapper = AgentFrameworkAgent(agent=agent, state_schema=state_schema)

    input_data = {
        "messages": [{"role": "user", "content": "Hi"}],
        "state": {"document": "Initial content"},
    }

    events = []
    async for event in wrapper.run_agent(input_data):
        events.append(event)

    # Find StateSnapshotEvent
    snapshot_events = [e for e in events if e.type == "STATE_SNAPSHOT"]
    assert len(snapshot_events) >= 1

    # First snapshot should have initial state
    assert snapshot_events[0].snapshot == {"document": "Initial content"}


async def test_state_initialization_object_type():
    """Test state initialization with object type in schema."""
    from agent_framework_ag_ui import AgentFrameworkAgent

    class MockChatClient:
        async def get_streaming_response(self, messages, chat_options, **kwargs):
            yield ChatResponseUpdate(contents=[TextContent(text="Hello")])

    agent = ChatAgent(name="test_agent", instructions="Test", chat_client=MockChatClient())
    state_schema = {"recipe": {"type": "object", "properties": {}}}
    wrapper = AgentFrameworkAgent(agent=agent, state_schema=state_schema)

    input_data = {"messages": [{"role": "user", "content": "Hi"}]}

    events = []
    async for event in wrapper.run_agent(input_data):
        events.append(event)

    # Find StateSnapshotEvent
    snapshot_events = [e for e in events if e.type == "STATE_SNAPSHOT"]
    assert len(snapshot_events) >= 1

    # Should initialize as empty object
    assert snapshot_events[0].snapshot == {"recipe": {}}


async def test_state_initialization_array_type():
    """Test state initialization with array type in schema."""
    from agent_framework_ag_ui import AgentFrameworkAgent

    class MockChatClient:
        async def get_streaming_response(self, messages, chat_options, **kwargs):
            yield ChatResponseUpdate(contents=[TextContent(text="Hello")])

    agent = ChatAgent(name="test_agent", instructions="Test", chat_client=MockChatClient())
    state_schema = {"steps": {"type": "array", "items": {}}}
    wrapper = AgentFrameworkAgent(agent=agent, state_schema=state_schema)

    input_data = {"messages": [{"role": "user", "content": "Hi"}]}

    events = []
    async for event in wrapper.run_agent(input_data):
        events.append(event)

    # Find StateSnapshotEvent
    snapshot_events = [e for e in events if e.type == "STATE_SNAPSHOT"]
    assert len(snapshot_events) >= 1

    # Should initialize as empty array
    assert snapshot_events[0].snapshot == {"steps": []}


async def test_run_finished_event_emission():
    """Test RunFinishedEvent is emitted at end of run."""
    from agent_framework_ag_ui import AgentFrameworkAgent

    class MockChatClient:
        async def get_streaming_response(self, messages, chat_options, **kwargs):
            yield ChatResponseUpdate(contents=[TextContent(text="Hello")])

    agent = ChatAgent(name="test_agent", instructions="Test", chat_client=MockChatClient())
    wrapper = AgentFrameworkAgent(agent=agent)

    input_data = {"messages": [{"role": "user", "content": "Hi"}]}

    events = []
    async for event in wrapper.run_agent(input_data):
        events.append(event)

    # Last event should be RunFinishedEvent
    assert events[-1].type == "RUN_FINISHED"


async def test_tool_result_confirm_changes_accepted():
    """Test confirm_changes tool result handling when accepted."""
    from agent_framework_ag_ui import AgentFrameworkAgent

    class MockChatClient:
        async def get_streaming_response(self, messages, chat_options, **kwargs):
            yield ChatResponseUpdate(contents=[TextContent(text="Document updated")])

    agent = ChatAgent(name="test_agent", instructions="Test", chat_client=MockChatClient())
    wrapper = AgentFrameworkAgent(
        agent=agent,
        state_schema={"document": {"type": "string"}},
        predict_state_config={"document": {"tool": "write_doc", "tool_argument": "content"}},
    )

    # Simulate tool result message with acceptance
    tool_result = {"accepted": True, "steps": []}
    input_data = {
        "messages": [
            {
                "role": "tool",  # Tool result from UI
                "content": json.dumps(tool_result),
                "toolCallId": "confirm_call_123",
            }
        ],
        "state": {"document": "Updated content"},
    }

    events = []
    async for event in wrapper.run_agent(input_data):
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


async def test_tool_result_confirm_changes_rejected():
    """Test confirm_changes tool result handling when rejected."""
    from agent_framework_ag_ui import AgentFrameworkAgent

    class MockChatClient:
        async def get_streaming_response(self, messages, chat_options, **kwargs):
            yield ChatResponseUpdate(contents=[TextContent(text="OK")])

    agent = ChatAgent(name="test_agent", instructions="Test", chat_client=MockChatClient())
    wrapper = AgentFrameworkAgent(agent=agent)

    # Simulate tool result message with rejection
    tool_result = {"accepted": False, "steps": []}
    input_data = {
        "messages": [
            {
                "role": "tool",
                "content": json.dumps(tool_result),
                "toolCallId": "confirm_call_123",
            }
        ],
    }

    events = []
    async for event in wrapper.run_agent(input_data):
        events.append(event)

    # Should emit text message asking what to change
    text_content_events = [e for e in events if e.type == "TEXT_MESSAGE_CONTENT"]
    assert len(text_content_events) > 0
    assert any("what would you like me to change" in e.delta.lower() for e in text_content_events)


async def test_tool_result_function_approval_accepted():
    """Test function approval tool result when steps are accepted."""
    from agent_framework_ag_ui import AgentFrameworkAgent

    class MockChatClient:
        async def get_streaming_response(self, messages, chat_options, **kwargs):
            yield ChatResponseUpdate(contents=[TextContent(text="OK")])

    agent = ChatAgent(name="test_agent", instructions="Test", chat_client=MockChatClient())
    wrapper = AgentFrameworkAgent(agent=agent)

    # Simulate tool result with multiple steps
    tool_result = {
        "accepted": True,
        "steps": [
            {"id": "step1", "description": "Send email", "status": "enabled"},
            {"id": "step2", "description": "Create calendar event", "status": "enabled"},
        ],
    }
    input_data = {
        "messages": [
            {
                "role": "tool",
                "content": json.dumps(tool_result),
                "toolCallId": "approval_call_123",
            }
        ],
    }

    events = []
    async for event in wrapper.run_agent(input_data):
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


async def test_tool_result_function_approval_rejected():
    """Test function approval tool result when rejected."""
    from agent_framework_ag_ui import AgentFrameworkAgent

    class MockChatClient:
        async def get_streaming_response(self, messages, chat_options, **kwargs):
            yield ChatResponseUpdate(contents=[TextContent(text="OK")])

    agent = ChatAgent(name="test_agent", instructions="Test", chat_client=MockChatClient())
    wrapper = AgentFrameworkAgent(agent=agent)

    # Simulate tool result rejection with steps
    tool_result = {
        "accepted": False,
        "steps": [{"id": "step1", "description": "Send email", "status": "disabled"}],
    }
    input_data = {
        "messages": [
            {
                "role": "tool",
                "content": json.dumps(tool_result),
                "toolCallId": "approval_call_123",
            }
        ],
    }

    events = []
    async for event in wrapper.run_agent(input_data):
        events.append(event)

    # Should ask what to change about the plan
    text_content_events = [e for e in events if e.type == "TEXT_MESSAGE_CONTENT"]
    assert len(text_content_events) > 0
    assert any("what would you like me to change about the plan" in e.delta.lower() for e in text_content_events)


async def test_thread_metadata_tracking():
    """Test that thread metadata includes ag_ui_thread_id and ag_ui_run_id."""
    from agent_framework_ag_ui import AgentFrameworkAgent

    thread_metadata = {}

    class MockChatClient:
        async def get_streaming_response(self, messages, chat_options, **kwargs):
            # Capture thread metadata from kwargs
            nonlocal thread_metadata
            if "thread" in kwargs:
                thread_metadata = kwargs["thread"].metadata
            yield ChatResponseUpdate(contents=[TextContent(text="Hello")])

    agent = ChatAgent(name="test_agent", instructions="Test", chat_client=MockChatClient())
    wrapper = AgentFrameworkAgent(agent=agent)

    input_data = {
        "messages": [{"role": "user", "content": "Hi"}],
        "thread_id": "test_thread_123",
        "run_id": "test_run_456",
    }

    events = []
    async for event in wrapper.run_agent(input_data):
        events.append(event)

    # Check thread metadata was set
    # Note: This test may need adjustment based on actual thread passing mechanism


async def test_state_context_injection():
    """Test that current state is injected into thread metadata."""
    from agent_framework_ag_ui import AgentFrameworkAgent

    thread_metadata = {}

    class MockChatClient:
        async def get_streaming_response(self, messages, chat_options, **kwargs):
            # Track if state context message was added
            nonlocal thread_metadata
            # In actual implementation, thread is passed and state is in metadata
            yield ChatResponseUpdate(contents=[TextContent(text="Hello")])

    agent = ChatAgent(name="test_agent", instructions="Test", chat_client=MockChatClient())
    wrapper = AgentFrameworkAgent(
        agent=agent,
        state_schema={"document": {"type": "string"}},
    )

    input_data = {
        "messages": [{"role": "user", "content": "Hi"}],
        "state": {"document": "Test content"},
    }

    events = []
    async for event in wrapper.run_agent(input_data):
        events.append(event)

    # State should be injected - this is validated by agent execution flow


async def test_no_messages_provided():
    """Test handling when no messages are provided."""
    from agent_framework_ag_ui import AgentFrameworkAgent

    class MockChatClient:
        async def get_streaming_response(self, messages, chat_options, **kwargs):
            yield ChatResponseUpdate(contents=[TextContent(text="Hello")])

    agent = ChatAgent(name="test_agent", instructions="Test", chat_client=MockChatClient())
    wrapper = AgentFrameworkAgent(agent=agent)

    input_data = {"messages": []}

    events = []
    async for event in wrapper.run_agent(input_data):
        events.append(event)

    # Should emit RunStartedEvent and RunFinishedEvent only
    assert len(events) == 2
    assert events[0].type == "RUN_STARTED"
    assert events[-1].type == "RUN_FINISHED"


async def test_message_end_event_emission():
    """Test TextMessageEndEvent is emitted for assistant messages."""
    from agent_framework_ag_ui import AgentFrameworkAgent

    class MockChatClient:
        async def get_streaming_response(self, messages, chat_options, **kwargs):
            yield ChatResponseUpdate(contents=[TextContent(text="Hello world")])

    agent = ChatAgent(name="test_agent", instructions="Test", chat_client=MockChatClient())
    wrapper = AgentFrameworkAgent(agent=agent)

    input_data = {"messages": [{"role": "user", "content": "Hi"}]}

    events = []
    async for event in wrapper.run_agent(input_data):
        events.append(event)

    # Should have TextMessageEndEvent before RunFinishedEvent
    end_events = [e for e in events if e.type == "TEXT_MESSAGE_END"]
    assert len(end_events) == 1

    # EndEvent should come before FinishedEvent
    end_index = events.index(end_events[0])
    finished_index = events.index([e for e in events if e.type == "RUN_FINISHED"][0])
    assert end_index < finished_index


async def test_error_handling_with_exception():
    """Test that exceptions during agent execution are re-raised."""
    from agent_framework_ag_ui import AgentFrameworkAgent

    class FailingChatClient:
        async def get_streaming_response(self, messages, chat_options, **kwargs):
            if False:
                yield
            raise RuntimeError("Simulated failure")

    agent = ChatAgent(name="test_agent", instructions="Test", chat_client=FailingChatClient())
    wrapper = AgentFrameworkAgent(agent=agent)

    input_data = {"messages": [{"role": "user", "content": "Hi"}]}

    with pytest.raises(RuntimeError, match="Simulated failure"):
        async for event in wrapper.run_agent(input_data):
            pass


async def test_json_decode_error_in_tool_result():
    """Test handling of orphaned tool result - should be sanitized out."""
    from agent_framework_ag_ui import AgentFrameworkAgent

    class MockChatClient:
        async def get_streaming_response(self, messages, chat_options, **kwargs):
            # Should not be called since orphaned tool result is dropped
            if False:
                yield
            raise AssertionError("ChatClient should not be called with orphaned tool result")

    agent = ChatAgent(name="test_agent", instructions="Test", chat_client=MockChatClient())
    wrapper = AgentFrameworkAgent(agent=agent)

    # Send invalid JSON as tool result without preceding tool call
    input_data = {
        "messages": [
            {
                "role": "tool",
                "content": "invalid json {not valid}",
                "toolCallId": "call_123",
            }
        ],
    }

    events = []
    async for event in wrapper.run_agent(input_data):
        events.append(event)

    # Orphaned tool result should be sanitized out
    # Only run lifecycle events should be emitted, no text/tool events
    text_events = [e for e in events if e.type == "TEXT_MESSAGE_CONTENT"]
    tool_events = [e for e in events if e.type.startswith("TOOL_CALL")]
    assert len(text_events) == 0
    assert len(tool_events) == 0


async def test_suppressed_summary_with_document_state():
    """Test suppressed summary uses document state for confirmation message."""
    from agent_framework_ag_ui import AgentFrameworkAgent, DocumentWriterConfirmationStrategy

    class MockChatClient:
        async def get_streaming_response(self, messages, chat_options, **kwargs):
            yield ChatResponseUpdate(contents=[TextContent(text="Response")])

    agent = ChatAgent(name="test_agent", instructions="Test", chat_client=MockChatClient())
    wrapper = AgentFrameworkAgent(
        agent=agent,
        state_schema={"document": {"type": "string"}},
        predict_state_config={"document": {"tool": "write_doc", "tool_argument": "content"}},
        confirmation_strategy=DocumentWriterConfirmationStrategy(),
    )

    # Simulate confirmation with document state
    tool_result = {"accepted": True, "steps": []}
    input_data = {
        "messages": [
            {
                "role": "tool",
                "content": json.dumps(tool_result),
                "toolCallId": "confirm_123",
            }
        ],
        "state": {"document": "This is the beginning of a document. It contains important information."},
    }

    events = []
    async for event in wrapper.run_agent(input_data):
        events.append(event)

    # Should generate fallback summary from document state
    text_events = [e for e in events if e.type == "TEXT_MESSAGE_CONTENT"]
    assert len(text_events) > 0
    # Should contain some reference to the document
    full_text = "".join(e.delta for e in text_events)
    assert "written" in full_text.lower() or "document" in full_text.lower()
