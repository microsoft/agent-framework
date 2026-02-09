# Copyright (c) Microsoft. All rights reserved.

"""Tests for _actions_agents.py module.

These tests cover:
- JSON extraction utility function
- Message building from state
- Agent invocation handlers
"""

import json
from collections.abc import AsyncGenerator
from typing import Any

import pytest

from agent_framework_declarative._workflows._actions_agents import (
    _extract_json_from_response,
)
from agent_framework_declarative._workflows._handlers import (
    ActionContext,
    WorkflowEvent,
    get_action_handler,
)
from agent_framework_declarative._workflows._state import WorkflowState


def create_action_context(
    action: dict[str, Any],
    inputs: dict[str, Any] | None = None,
    agents: dict[str, Any] | None = None,
    bindings: dict[str, Any] | None = None,
    state: WorkflowState | None = None,
) -> ActionContext:
    """Helper to create an ActionContext for testing."""
    if state is None:
        state = WorkflowState(inputs=inputs or {})

    async def execute_actions(
        actions: list[dict[str, Any]], state: WorkflowState
    ) -> AsyncGenerator[WorkflowEvent, None]:
        """Mock execute_actions that runs handlers for nested actions."""
        for nested_action in actions:
            action_kind = nested_action.get("kind")
            handler = get_action_handler(action_kind)
            if handler:
                ctx = ActionContext(
                    state=state,
                    action=nested_action,
                    execute_actions=execute_actions,
                    agents=agents or {},
                    bindings=bindings or {},
                )
                async for event in handler(ctx):
                    yield event

    return ActionContext(
        state=state,
        action=action,
        execute_actions=execute_actions,
        agents=agents or {},
        bindings=bindings or {},
    )


class TestExtractJsonFromResponse:
    """Tests for _extract_json_from_response utility function."""

    def test_pure_json_object(self):
        """Test parsing pure JSON object."""
        text = '{"key": "value", "number": 42}'
        result = _extract_json_from_response(text)
        assert result == {"key": "value", "number": 42}

    def test_pure_json_array(self):
        """Test parsing pure JSON array."""
        text = '[1, 2, 3, "four"]'
        result = _extract_json_from_response(text)
        assert result == [1, 2, 3, "four"]

    def test_json_in_markdown_code_block(self):
        """Test extracting JSON from markdown code block with json tag."""
        text = """Here's the response:
```json
{"status": "success", "data": [1, 2, 3]}
```
That's all!"""
        result = _extract_json_from_response(text)
        assert result == {"status": "success", "data": [1, 2, 3]}

    def test_json_in_plain_code_block(self):
        """Test extracting JSON from plain markdown code block."""
        text = """Result:
```
{"name": "test"}
```"""
        result = _extract_json_from_response(text)
        assert result == {"name": "test"}

    def test_json_with_leading_text(self):
        """Test extracting JSON with leading explanatory text."""
        text = 'Here is the result: {"answer": 42}'
        result = _extract_json_from_response(text)
        assert result == {"answer": 42}

    def test_json_with_trailing_text(self):
        """Test extracting JSON with trailing text."""
        text = '{"answer": 42} - that is the answer'
        result = _extract_json_from_response(text)
        assert result == {"answer": 42}

    def test_multiple_json_objects_returns_last(self):
        """Test that multiple JSON objects returns the last valid one."""
        text = '{"partial": true} {"complete": true, "final": "result"}'
        result = _extract_json_from_response(text)
        assert result == {"complete": True, "final": "result"}

    def test_nested_json_object(self):
        """Test parsing nested JSON objects."""
        text = '{"outer": {"inner": {"deep": "value"}}}'
        result = _extract_json_from_response(text)
        assert result == {"outer": {"inner": {"deep": "value"}}}

    def test_json_with_escaped_quotes(self):
        """Test JSON with escaped quotes in strings."""
        text = '{"message": "He said \\"hello\\""}'
        result = _extract_json_from_response(text)
        assert result == {"message": 'He said "hello"'}

    def test_json_with_newlines_in_strings(self):
        """Test JSON with newlines in string values."""
        text = '{"text": "line1\\nline2"}'
        result = _extract_json_from_response(text)
        assert result == {"text": "line1\nline2"}

    def test_empty_string_returns_none(self):
        """Test that empty string returns None."""
        result = _extract_json_from_response("")
        assert result is None

    def test_whitespace_only_returns_none(self):
        """Test that whitespace-only string returns None."""
        result = _extract_json_from_response("   \n\t  ")
        assert result is None

    def test_none_input_returns_none(self):
        """Test that None-like empty input returns None."""
        result = _extract_json_from_response("")
        assert result is None

    def test_no_json_raises_error(self):
        """Test that text with no JSON raises JSONDecodeError."""
        text = "This is just plain text with no JSON"
        with pytest.raises(json.JSONDecodeError):
            _extract_json_from_response(text)

    def test_malformed_json_raises_error(self):
        """Test that malformed JSON raises JSONDecodeError."""
        text = '{"key": "value", missing_quote: bad}'
        with pytest.raises(json.JSONDecodeError):
            _extract_json_from_response(text)

    def test_json_array_in_text(self):
        """Test extracting JSON array from surrounding text."""
        text = "The numbers are: [1, 2, 3, 4, 5] in order"
        result = _extract_json_from_response(text)
        assert result == [1, 2, 3, 4, 5]

    def test_complex_nested_structure(self):
        """Test complex nested JSON structure."""
        text = """
        ```json
        {
            "users": [
                {"id": 1, "name": "Alice"},
                {"id": 2, "name": "Bob"}
            ],
            "metadata": {
                "count": 2,
                "page": 1
            }
        }
        ```
        """
        result = _extract_json_from_response(text)
        assert result == {
            "users": [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}],
            "metadata": {"count": 2, "page": 1},
        }

    def test_json_with_boolean_and_null(self):
        """Test JSON with boolean and null values."""
        text = '{"active": true, "deleted": false, "data": null}'
        result = _extract_json_from_response(text)
        assert result == {"active": True, "deleted": False, "data": None}

    def test_multiple_code_blocks_returns_last(self):
        """Test that multiple code blocks returns last valid JSON."""
        text = """
First attempt:
```json
{"attempt": 1}
```

Final result:
```json
{"attempt": 2, "final": true}
```
"""
        result = _extract_json_from_response(text)
        assert result == {"attempt": 2, "final": True}

    def test_json_with_unicode(self):
        """Test JSON with unicode characters."""
        text = '{"greeting": "Hello, 世界!", "emoji": "👋"}'
        result = _extract_json_from_response(text)
        assert result == {"greeting": "Hello, 世界!", "emoji": "👋"}

    def test_json_with_numbers(self):
        """Test JSON with various number formats."""
        text = '{"int": 42, "float": 3.14, "negative": -10, "scientific": 1.5e10}'
        result = _extract_json_from_response(text)
        assert result == {"int": 42, "float": 3.14, "negative": -10, "scientific": 1.5e10}

    def test_empty_json_object(self):
        """Test empty JSON object."""
        text = "{}"
        result = _extract_json_from_response(text)
        assert result == {}

    def test_empty_json_array(self):
        """Test empty JSON array."""
        text = "[]"
        result = _extract_json_from_response(text)
        assert result == []

    def test_json_with_backslashes(self):
        """Test JSON with backslash escapes."""
        text = '{"path": "C:\\\\Users\\\\test"}'
        result = _extract_json_from_response(text)
        assert result == {"path": "C:\\Users\\test"}


class TestNormalizeVariablePath:
    """Tests for _normalize_variable_path utility function."""

    def test_local_prefix_unchanged(self):
        """Test that Local. prefix is preserved."""
        from agent_framework_declarative._workflows._actions_agents import _normalize_variable_path

        result = _normalize_variable_path("Local.myVar")
        assert result == "Local.myVar"

    def test_system_prefix_unchanged(self):
        """Test that System. prefix is preserved."""
        from agent_framework_declarative._workflows._actions_agents import _normalize_variable_path

        result = _normalize_variable_path("System.ConversationId")
        assert result == "System.ConversationId"

    def test_workflow_prefix_unchanged(self):
        """Test that Workflow. prefix is preserved."""
        from agent_framework_declarative._workflows._actions_agents import _normalize_variable_path

        result = _normalize_variable_path("Workflow.step")
        assert result == "Workflow.step"

    def test_agent_prefix_unchanged(self):
        """Test that Agent. prefix is preserved."""
        from agent_framework_declarative._workflows._actions_agents import _normalize_variable_path

        result = _normalize_variable_path("Agent.result")
        assert result == "Agent.result"

    def test_conversation_prefix_unchanged(self):
        """Test that Conversation. prefix is preserved."""
        from agent_framework_declarative._workflows._actions_agents import _normalize_variable_path

        result = _normalize_variable_path("Conversation.messages")
        assert result == "Conversation.messages"

    def test_custom_namespace_preserved(self):
        """Test that custom namespaces with dots are preserved."""
        from agent_framework_declarative._workflows._actions_agents import _normalize_variable_path

        result = _normalize_variable_path("Custom.myVar")
        assert result == "Custom.myVar"

    def test_no_prefix_defaults_to_local(self):
        """Test that variables without prefix default to Local."""
        from agent_framework_declarative._workflows._actions_agents import _normalize_variable_path

        result = _normalize_variable_path("myVariable")
        assert result == "Local.myVariable"

    def test_nested_path_preserved(self):
        """Test that nested paths are preserved."""
        from agent_framework_declarative._workflows._actions_agents import _normalize_variable_path

        result = _normalize_variable_path("Local.data.nested.value")
        assert result == "Local.data.nested.value"


class TestBuildMessagesFromState:
    """Tests for _build_messages_from_state function."""

    def test_empty_conversation_returns_empty_list(self):
        """Test that empty conversation returns empty message list."""
        from agent_framework_declarative._workflows._actions_agents import _build_messages_from_state

        ctx = create_action_context(action={"kind": "InvokeAzureAgent"})
        messages = _build_messages_from_state(ctx)
        assert messages == []

    def test_conversation_messages_included(self):
        """Test that conversation messages are included in result."""
        from agent_framework._types import ChatMessage

        from agent_framework_declarative._workflows._actions_agents import _build_messages_from_state

        state = WorkflowState()
        msg1 = ChatMessage(role="user", text="Hello")
        msg2 = ChatMessage(role="assistant", text="Hi there!")
        state.set("conversation.messages", [msg1, msg2])

        ctx = create_action_context(action={"kind": "InvokeAzureAgent"}, state=state)
        messages = _build_messages_from_state(ctx)
        assert len(messages) == 2
        assert messages[0].text == "Hello"
        assert messages[1].text == "Hi there!"

    def test_none_conversation_returns_empty(self):
        """Test that None conversation returns empty list."""
        from agent_framework_declarative._workflows._actions_agents import _build_messages_from_state

        state = WorkflowState()
        state.set("conversation.messages", None)

        ctx = create_action_context(action={"kind": "InvokeAzureAgent"}, state=state)
        messages = _build_messages_from_state(ctx)
        assert messages == []


class TestInvokeAzureAgentHandler:
    """Tests for handle_invoke_azure_agent action handler."""

    @pytest.mark.asyncio
    async def test_missing_agent_name_logs_warning(self):
        """Test that missing agent name logs warning and returns."""
        from agent_framework_declarative._workflows._actions_agents import handle_invoke_azure_agent

        ctx = create_action_context(action={"kind": "InvokeAzureAgent"})
        events = [event async for event in handle_invoke_azure_agent(ctx)]
        assert events == []

    @pytest.mark.asyncio
    async def test_agent_name_from_string(self):
        """Test that agent name can be provided as string."""
        from agent_framework_declarative._workflows._actions_agents import handle_invoke_azure_agent

        ctx = create_action_context(
            action={"kind": "InvokeAzureAgent", "agent": "myAgent"},
            agents={},  # Agent not found, so will return early
        )
        events = [event async for event in handle_invoke_azure_agent(ctx)]
        assert events == []

    @pytest.mark.asyncio
    async def test_agent_name_from_dict(self):
        """Test that agent name can be provided as dict with name key."""
        from agent_framework_declarative._workflows._actions_agents import handle_invoke_azure_agent

        ctx = create_action_context(
            action={"kind": "InvokeAzureAgent", "agent": {"name": "myAgent"}},
        )
        events = [event async for event in handle_invoke_azure_agent(ctx)]
        assert events == []

    @pytest.mark.asyncio
    async def test_agent_name_from_expression(self):
        """Test that agent name can be evaluated from expression."""
        from agent_framework_declarative._workflows._actions_agents import handle_invoke_azure_agent

        state = WorkflowState()
        state.set("Local.agentName", "dynamicAgent")
        ctx = create_action_context(
            action={"kind": "InvokeAzureAgent", "agent": {"name": "=Local.agentName"}},
            state=state,
        )
        events = [event async for event in handle_invoke_azure_agent(ctx)]
        assert events == []

    @pytest.mark.asyncio
    async def test_agent_not_found_logs_error(self):
        """Test that agent not found logs error and returns."""
        from agent_framework_declarative._workflows._actions_agents import handle_invoke_azure_agent

        ctx = create_action_context(
            action={"kind": "InvokeAzureAgent", "agent": "nonExistentAgent"},
        )
        events = [event async for event in handle_invoke_azure_agent(ctx)]
        assert events == []

    @pytest.mark.asyncio
    async def test_streaming_agent_with_run_stream(self):
        """Test invocation of streaming agent with run(stream=True) method."""
        from typing import Any
        from unittest.mock import MagicMock

        from agent_framework._types import ChatMessage

        from agent_framework_declarative._workflows._actions_agents import handle_invoke_azure_agent
        from agent_framework_declarative._workflows._handlers import (
            AgentResponseEvent,
            AgentStreamingChunkEvent,
        )

        # Create a mock streaming agent
        mock_agent = MagicMock()
        mock_chunk1 = MagicMock()
        mock_chunk1.text = "Hello"
        mock_chunk1.tool_calls = []
        mock_chunk2 = MagicMock()
        mock_chunk2.text = " World"
        mock_chunk2.tool_calls = []

        async def mock_run(messages: list[Any], stream: bool = False):
            yield mock_chunk1
            yield mock_chunk2

        mock_agent.run = mock_run

        state = WorkflowState()
        state.set("conversation.messages", [ChatMessage(role="user", text="Test")])

        ctx = create_action_context(
            action={"kind": "InvokeAzureAgent", "agent": "testAgent", "outputPath": "Local.result"},
            state=state,
            agents={"testAgent": mock_agent},
        )

        events = [event async for event in handle_invoke_azure_agent(ctx)]

        # Should have streaming chunks and final response
        streaming_chunks = [e for e in events if isinstance(e, AgentStreamingChunkEvent)]
        response_events = [e for e in events if isinstance(e, AgentResponseEvent)]

        assert len(streaming_chunks) == 2
        assert streaming_chunks[0].chunk == "Hello"
        assert streaming_chunks[1].chunk == " World"
        assert len(response_events) == 1

    @pytest.mark.asyncio
    async def test_non_streaming_agent_with_run(self):
        """Test invocation of non-streaming agent with run method."""
        from unittest.mock import AsyncMock, MagicMock

        from agent_framework._types import ChatMessage

        from agent_framework_declarative._workflows._actions_agents import handle_invoke_azure_agent
        from agent_framework_declarative._workflows._handlers import AgentResponseEvent

        # Create a mock non-streaming agent (with spec to exclude run_stream)
        mock_agent = MagicMock(spec=["run"])
        mock_response = MagicMock()
        mock_response.text = "Response text"
        mock_response.messages = [ChatMessage(role="assistant", text="Response text")]
        mock_response.tool_calls = None
        mock_agent.run = AsyncMock(return_value=mock_response)

        state = WorkflowState()
        state.set("conversation.messages", [ChatMessage(role="user", text="Test")])

        ctx = create_action_context(
            action={"kind": "InvokeAzureAgent", "agent": "testAgent", "outputPath": "Local.result"},
            state=state,
            agents={"testAgent": mock_agent},
        )

        events = [event async for event in handle_invoke_azure_agent(ctx)]

        assert len(events) == 1
        assert isinstance(events[0], AgentResponseEvent)
        assert events[0].text == "Response text"
        assert state.get("Local.result") == "Response text"

    @pytest.mark.asyncio
    async def test_input_messages_from_string(self):
        """Test that input messages from string are handled."""
        from unittest.mock import AsyncMock, MagicMock

        from agent_framework_declarative._workflows._actions_agents import handle_invoke_azure_agent

        mock_agent = MagicMock(spec=["run"])
        mock_response = MagicMock()
        mock_response.text = "Response"
        mock_response.messages = []
        mock_response.tool_calls = None
        mock_agent.run = AsyncMock(return_value=mock_response)

        ctx = create_action_context(
            action={
                "kind": "InvokeAzureAgent",
                "agent": "testAgent",
                "input": {"messages": "User input string"},
            },
            agents={"testAgent": mock_agent},
        )

        events = [event async for event in handle_invoke_azure_agent(ctx)]
        assert len(events) == 1

        # Verify the agent was called with messages including the input
        call_args = mock_agent.run.call_args[0][0]
        assert any(msg.text == "User input string" for msg in call_args)

    @pytest.mark.asyncio
    async def test_input_messages_from_list(self):
        """Test that input messages from list are handled."""
        from unittest.mock import AsyncMock, MagicMock

        from agent_framework_declarative._workflows._actions_agents import handle_invoke_azure_agent

        mock_agent = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "Response"
        mock_response.messages = []
        mock_response.tool_calls = None
        mock_agent.run = AsyncMock(return_value=mock_response)

        ctx = create_action_context(
            action={
                "kind": "InvokeAzureAgent",
                "agent": "testAgent",
                "input": {
                    "messages": [
                        "String message",
                        {"role": "user", "content": "Dict message"},
                        {"role": "assistant", "content": "Assistant message"},
                        {"role": "system", "content": "System message"},
                    ]
                },
            },
            agents={"testAgent": mock_agent},
        )

        events = [event async for event in handle_invoke_azure_agent(ctx)]
        assert len(events) == 1

    @pytest.mark.asyncio
    async def test_output_response_object_json_parsing(self):
        """Test that responseObject output parses JSON from response."""
        from unittest.mock import AsyncMock, MagicMock

        from agent_framework_declarative._workflows._actions_agents import handle_invoke_azure_agent

        mock_agent = MagicMock(spec=["run"])
        mock_response = MagicMock()
        mock_response.text = '{"result": "parsed", "count": 42}'
        mock_response.messages = []
        mock_response.tool_calls = None
        mock_agent.run = AsyncMock(return_value=mock_response)

        state = WorkflowState()
        ctx = create_action_context(
            action={
                "kind": "InvokeAzureAgent",
                "agent": "testAgent",
                "output": {"responseObject": "Local.parsed"},
            },
            state=state,
            agents={"testAgent": mock_agent},
        )

        events = [event async for event in handle_invoke_azure_agent(ctx)]
        assert len(events) == 1

        # Verify the parsed JSON was stored
        parsed = state.get("Local.parsed")
        assert parsed == {"result": "parsed", "count": 42}

    @pytest.mark.asyncio
    async def test_output_messages_storage(self):
        """Test that output messages are stored in specified variable."""
        from unittest.mock import AsyncMock, MagicMock

        from agent_framework._types import ChatMessage

        from agent_framework_declarative._workflows._actions_agents import handle_invoke_azure_agent

        mock_agent = MagicMock(spec=["run"])
        mock_response = MagicMock()
        mock_response.text = "Response"
        mock_response.messages = [ChatMessage(role="assistant", text="Response")]
        mock_response.tool_calls = None
        mock_agent.run = AsyncMock(return_value=mock_response)

        state = WorkflowState()
        ctx = create_action_context(
            action={
                "kind": "InvokeAzureAgent",
                "agent": "testAgent",
                "output": {"messages": "Local.outputMessages"},
            },
            state=state,
            agents={"testAgent": mock_agent},
        )

        events = [event async for event in handle_invoke_azure_agent(ctx)]
        assert len(events) == 1

        # Verify messages were stored
        stored = state.get("Local.outputMessages")
        assert len(stored) == 1

    @pytest.mark.asyncio
    async def test_agent_without_run_methods(self):
        """Test agent without run or run_stream methods logs error."""
        from unittest.mock import MagicMock

        from agent_framework_declarative._workflows._actions_agents import handle_invoke_azure_agent

        mock_agent = MagicMock(spec=[])  # No run or run_stream methods

        ctx = create_action_context(
            action={"kind": "InvokeAzureAgent", "agent": "testAgent"},
            agents={"testAgent": mock_agent},
        )

        events = [event async for event in handle_invoke_azure_agent(ctx)]
        assert events == []

    @pytest.mark.asyncio
    async def test_agent_error_raises_exception(self):
        """Test that agent errors are propagated."""
        from unittest.mock import AsyncMock, MagicMock

        from agent_framework_declarative._workflows._actions_agents import handle_invoke_azure_agent

        mock_agent = MagicMock(spec=["run"])
        mock_agent.run = AsyncMock(side_effect=RuntimeError("Agent failed"))

        ctx = create_action_context(
            action={"kind": "InvokeAzureAgent", "agent": "testAgent"},
            agents={"testAgent": mock_agent},
        )

        with pytest.raises(RuntimeError, match="Agent failed"):
            [event async for event in handle_invoke_azure_agent(ctx)]


class TestInvokePromptAgentHandler:
    """Tests for handle_invoke_prompt_agent action handler."""

    @pytest.mark.asyncio
    async def test_missing_agent_property_logs_warning(self):
        """Test that missing agent property logs warning."""
        from agent_framework_declarative._workflows._actions_agents import handle_invoke_prompt_agent

        ctx = create_action_context(action={"kind": "InvokePromptAgent"})
        events = [event async for event in handle_invoke_prompt_agent(ctx)]
        assert events == []

    @pytest.mark.asyncio
    async def test_non_string_agent_property_logs_warning(self):
        """Test that non-string agent property logs warning."""
        from agent_framework_declarative._workflows._actions_agents import handle_invoke_prompt_agent

        ctx = create_action_context(
            action={"kind": "InvokePromptAgent", "agent": {"name": "notAString"}},
        )
        events = [event async for event in handle_invoke_prompt_agent(ctx)]
        assert events == []

    @pytest.mark.asyncio
    async def test_agent_not_found_logs_error(self):
        """Test that agent not found logs error."""
        from agent_framework_declarative._workflows._actions_agents import handle_invoke_prompt_agent

        ctx = create_action_context(
            action={"kind": "InvokePromptAgent", "agent": "missingAgent"},
        )
        events = [event async for event in handle_invoke_prompt_agent(ctx)]
        assert events == []

    @pytest.mark.asyncio
    async def test_streaming_agent(self):
        """Test invocation of streaming prompt agent."""
        from typing import Any
        from unittest.mock import MagicMock

        from agent_framework_declarative._workflows._actions_agents import handle_invoke_prompt_agent
        from agent_framework_declarative._workflows._handlers import (
            AgentResponseEvent,
            AgentStreamingChunkEvent,
        )

        mock_agent = MagicMock()
        mock_chunk = MagicMock()
        mock_chunk.text = "Chunk"

        async def mock_run(messages: list[Any], stream: bool = False):
            yield mock_chunk

        mock_agent.run = mock_run

        ctx = create_action_context(
            action={"kind": "InvokePromptAgent", "agent": "testAgent", "outputPath": "Local.result"},
            agents={"testAgent": mock_agent},
        )

        events = [event async for event in handle_invoke_prompt_agent(ctx)]

        streaming_chunks = [e for e in events if isinstance(e, AgentStreamingChunkEvent)]
        response_events = [e for e in events if isinstance(e, AgentResponseEvent)]

        assert len(streaming_chunks) == 1
        assert len(response_events) == 1

    @pytest.mark.asyncio
    async def test_non_streaming_agent(self):
        """Test invocation of non-streaming prompt agent."""
        from unittest.mock import AsyncMock, MagicMock

        from agent_framework._types import ChatMessage

        from agent_framework_declarative._workflows._actions_agents import handle_invoke_prompt_agent
        from agent_framework_declarative._workflows._handlers import AgentResponseEvent

        mock_agent = MagicMock(spec=["run"])
        mock_response = MagicMock()
        mock_response.text = "Response text"
        mock_response.messages = [ChatMessage(role="assistant", text="Response text")]
        mock_agent.run = AsyncMock(return_value=mock_response)

        state = WorkflowState()
        ctx = create_action_context(
            action={
                "kind": "InvokePromptAgent",
                "agent": "testAgent",
                "outputPath": "Local.result",
            },
            state=state,
            agents={"testAgent": mock_agent},
        )

        events = [event async for event in handle_invoke_prompt_agent(ctx)]

        assert len(events) == 1
        assert isinstance(events[0], AgentResponseEvent)
        assert events[0].text == "Response text"
        assert state.get("Local.result") == "Response text"

    @pytest.mark.asyncio
    async def test_input_as_string(self):
        """Test input provided as string is added as user message."""
        from unittest.mock import AsyncMock, MagicMock

        from agent_framework_declarative._workflows._actions_agents import handle_invoke_prompt_agent

        mock_agent = MagicMock(spec=["run"])
        mock_response = MagicMock()
        mock_response.text = "Response"
        mock_response.messages = []
        mock_agent.run = AsyncMock(return_value=mock_response)

        ctx = create_action_context(
            action={
                "kind": "InvokePromptAgent",
                "agent": "testAgent",
                "input": "User input",
            },
            agents={"testAgent": mock_agent},
        )

        events = [event async for event in handle_invoke_prompt_agent(ctx)]
        assert len(events) == 1

        # Verify input was passed
        call_args = mock_agent.run.call_args[0][0]
        assert any(msg.text == "User input" for msg in call_args)

    @pytest.mark.asyncio
    async def test_input_as_chat_message(self):
        """Test input provided as ChatMessage is added directly."""
        from unittest.mock import AsyncMock, MagicMock

        from agent_framework._types import ChatMessage

        from agent_framework_declarative._workflows._actions_agents import handle_invoke_prompt_agent

        mock_agent = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "Response"
        mock_response.messages = []
        mock_agent.run = AsyncMock(return_value=mock_response)

        state = WorkflowState()
        input_msg = ChatMessage(role="user", text="Chat message input")
        state.set("Local.inputMsg", input_msg)

        ctx = create_action_context(
            action={
                "kind": "InvokePromptAgent",
                "agent": "testAgent",
                "input": "=Local.inputMsg",
            },
            state=state,
            agents={"testAgent": mock_agent},
        )

        events = [event async for event in handle_invoke_prompt_agent(ctx)]
        assert len(events) == 1

    @pytest.mark.asyncio
    async def test_agent_without_run_methods(self):
        """Test agent without run or run_stream methods logs error."""
        from unittest.mock import MagicMock

        from agent_framework_declarative._workflows._actions_agents import handle_invoke_prompt_agent

        mock_agent = MagicMock(spec=[])  # No run or run_stream

        ctx = create_action_context(
            action={"kind": "InvokePromptAgent", "agent": "testAgent"},
            agents={"testAgent": mock_agent},
        )

        events = [event async for event in handle_invoke_prompt_agent(ctx)]
        assert events == []

    @pytest.mark.asyncio
    async def test_agent_error_raises_exception(self):
        """Test that agent errors are propagated."""
        from unittest.mock import AsyncMock, MagicMock

        from agent_framework_declarative._workflows._actions_agents import handle_invoke_prompt_agent

        mock_agent = MagicMock(spec=["run"])
        mock_agent.run = AsyncMock(side_effect=ValueError("Agent error"))

        ctx = create_action_context(
            action={"kind": "InvokePromptAgent", "agent": "testAgent"},
            agents={"testAgent": mock_agent},
        )

        with pytest.raises(ValueError, match="Agent error"):
            [event async for event in handle_invoke_prompt_agent(ctx)]

    @pytest.mark.asyncio
    async def test_conversation_history_included(self):
        """Test that conversation history is included in messages."""
        from unittest.mock import AsyncMock, MagicMock

        from agent_framework._types import ChatMessage

        from agent_framework_declarative._workflows._actions_agents import handle_invoke_prompt_agent

        mock_agent = MagicMock(spec=["run"])
        mock_response = MagicMock()
        mock_response.text = "Response"
        mock_response.messages = []
        mock_agent.run = AsyncMock(return_value=mock_response)

        state = WorkflowState()
        state.set(
            "conversation.messages",
            [
                ChatMessage(role="user", text="Previous message"),
                ChatMessage(role="assistant", text="Previous response"),
            ],
        )

        ctx = create_action_context(
            action={"kind": "InvokePromptAgent", "agent": "testAgent"},
            state=state,
            agents={"testAgent": mock_agent},
        )

        events = [event async for event in handle_invoke_prompt_agent(ctx)]
        assert len(events) == 1

        # Verify history was passed
        call_args = mock_agent.run.call_args[0][0]
        assert len(call_args) >= 2
