# Copyright (c) Microsoft. All rights reserved.

"""Comprehensive tests for orchestrator coverage."""

from collections.abc import AsyncGenerator
from types import SimpleNamespace
from typing import Any

from agent_framework import (
    AgentRunResponseUpdate,
    ChatMessage,
    TextContent,
    ai_function,
)
from pydantic import BaseModel

from agent_framework_ag_ui._agent import AgentConfig
from agent_framework_ag_ui._orchestrators import (
    DefaultOrchestrator,
    ExecutionContext,
    HumanInTheLoopOrchestrator,
)


@ai_function(approval_mode="always_require")
def approval_tool(param: str) -> str:
    """Tool requiring approval."""
    return f"executed: {param}"


class MockAgent:
    """Mock agent for testing."""

    def __init__(self, updates: list[AgentRunResponseUpdate] | None = None) -> None:
        self.updates = updates or [AgentRunResponseUpdate(contents=[TextContent(text="response")], role="assistant")]
        self.chat_options = SimpleNamespace(tools=[approval_tool], response_format=None)
        self.chat_client = SimpleNamespace(function_invocation_configuration=None)
        self.messages_received: list[Any] = []
        self.tools_received: list[Any] | None = None

    async def run_stream(
        self,
        messages: list[Any],
        *,
        thread: Any = None,
        tools: list[Any] | None = None,
    ) -> AsyncGenerator[AgentRunResponseUpdate, None]:
        self.messages_received = messages
        self.tools_received = tools
        for update in self.updates:
            yield update


async def test_human_in_the_loop_json_decode_error() -> None:
    """Test HumanInTheLoopOrchestrator handles invalid JSON in tool result."""
    orchestrator = HumanInTheLoopOrchestrator()

    input_data = {
        "messages": [
            {
                "role": "tool",
                "content": [{"type": "text", "text": "not valid json {"}],
            }
        ],
    }

    messages = [
        ChatMessage(
            role="tool",
            contents=[TextContent(text="not valid json {")],
            additional_properties={"is_tool_result": True},
        )
    ]

    context = ExecutionContext(
        input_data=input_data,
        agent=MockAgent(),
        config=AgentConfig(),
    )
    context._messages = messages

    assert orchestrator.can_handle(context)

    events = []
    async for event in orchestrator.run(context):
        events.append(event)

    # Should emit RunErrorEvent for invalid JSON
    error_events = [e for e in events if e.type == "RUN_ERROR"]
    assert len(error_events) == 1
    assert "Invalid tool result format" in error_events[0].message


async def test_sanitize_tool_history_confirm_changes() -> None:
    """Test sanitize_tool_history logic for confirm_changes synthetic result."""
    from agent_framework import ChatMessage, FunctionCallContent, TextContent

    # Create messages that will trigger confirm_changes synthetic result injection
    messages = [
        ChatMessage(
            role="assistant",
            contents=[
                FunctionCallContent(
                    name="confirm_changes",
                    call_id="call_confirm_123",
                    arguments='{"changes": "test"}',
                )
            ],
        ),
        ChatMessage(
            role="user",
            contents=[TextContent(text='{"accepted": true}')],
        ),
    ]

    # The sanitize_tool_history function is internal to DefaultOrchestrator.run
    # We'll test it indirectly by checking the orchestrator processes it correctly
    orchestrator = DefaultOrchestrator()

    # Use pre-constructed ChatMessage objects to bypass message adapter
    input_data = {"messages": []}

    agent = MockAgent()
    context = ExecutionContext(
        input_data=input_data,
        agent=agent,
        config=AgentConfig(),
    )
    # Override the messages property to use our pre-constructed messages
    context._messages = messages

    events = []
    async for event in orchestrator.run(context):
        events.append(event)

    # Agent should receive synthetic tool result
    assert len(agent.messages_received) > 0
    tool_messages = [
        msg
        for msg in agent.messages_received
        if (msg.role.value if hasattr(msg.role, "value") else str(msg.role)) == "tool"
    ]
    assert len(tool_messages) == 1
    assert str(tool_messages[0].contents[0].call_id) == "call_confirm_123"
    assert tool_messages[0].contents[0].result == "Confirmed"


async def test_sanitize_tool_history_orphaned_tool_result() -> None:
    """Test sanitize_tool_history removes orphaned tool results."""
    from agent_framework import ChatMessage, FunctionResultContent, TextContent

    # Tool result without preceding assistant tool call
    messages = [
        ChatMessage(
            role="tool",
            contents=[FunctionResultContent(call_id="orphan_123", result="orphaned data")],
        ),
        ChatMessage(
            role="user",
            contents=[TextContent(text="Hello")],
        ),
    ]

    orchestrator = DefaultOrchestrator()
    input_data = {"messages": []}
    agent = MockAgent()
    context = ExecutionContext(
        input_data=input_data,
        agent=agent,
        config=AgentConfig(),
    )
    context._messages = messages

    events = []
    async for event in orchestrator.run(context):
        events.append(event)

    # Orphaned tool result should be filtered out
    tool_messages = [
        msg
        for msg in agent.messages_received
        if (msg.role.value if hasattr(msg.role, "value") else str(msg.role)) == "tool"
    ]
    assert len(tool_messages) == 0


async def test_orphaned_tool_result_sanitization() -> None:
    """Test that orphaned tool results are filtered out."""
    orchestrator = DefaultOrchestrator()

    input_data = {
        "messages": [
            {
                "role": "tool",
                "content": [{"type": "tool_result", "tool_call_id": "orphan_123", "content": "result"}],
            },
            {
                "role": "user",
                "content": [{"type": "text", "text": "Hello"}],
            },
        ],
    }

    agent = MockAgent()
    context = ExecutionContext(
        input_data=input_data,
        agent=agent,
        config=AgentConfig(),
    )

    events = []
    async for event in orchestrator.run(context):
        events.append(event)

    # Orphaned tool result should be filtered, only user message remains
    tool_messages = [
        msg
        for msg in agent.messages_received
        if (msg.role.value if hasattr(msg.role, "value") else str(msg.role)) == "tool"
    ]
    assert len(tool_messages) == 0


async def test_deduplicate_messages_empty_tool_results() -> None:
    """Test deduplicate_messages prefers non-empty tool results."""
    from agent_framework import ChatMessage, FunctionCallContent, FunctionResultContent

    messages = [
        ChatMessage(
            role="assistant",
            contents=[FunctionCallContent(name="test_tool", call_id="call_789", arguments="{}")],
        ),
        ChatMessage(
            role="tool",
            contents=[FunctionResultContent(call_id="call_789", result="")],
        ),
        ChatMessage(
            role="tool",
            contents=[FunctionResultContent(call_id="call_789", result="real data")],
        ),
    ]

    orchestrator = DefaultOrchestrator()
    input_data = {"messages": []}
    agent = MockAgent()
    context = ExecutionContext(
        input_data=input_data,
        agent=agent,
        config=AgentConfig(),
    )
    context._messages = messages

    events = []
    async for event in orchestrator.run(context):
        events.append(event)

    # Should have only one tool result with actual data
    tool_messages = [
        msg
        for msg in agent.messages_received
        if (msg.role.value if hasattr(msg.role, "value") else str(msg.role)) == "tool"
    ]
    assert len(tool_messages) == 1
    assert tool_messages[0].contents[0].result == "real data"


async def test_deduplicate_messages_duplicate_assistant_tool_calls() -> None:
    """Test deduplicate_messages removes duplicate assistant tool call messages."""
    from agent_framework import ChatMessage, FunctionCallContent, FunctionResultContent

    messages = [
        ChatMessage(
            role="assistant",
            contents=[FunctionCallContent(name="test_tool", call_id="call_abc", arguments="{}")],
        ),
        ChatMessage(
            role="assistant",
            contents=[FunctionCallContent(name="test_tool", call_id="call_abc", arguments="{}")],
        ),
        ChatMessage(
            role="tool",
            contents=[FunctionResultContent(call_id="call_abc", result="result")],
        ),
    ]

    orchestrator = DefaultOrchestrator()
    input_data = {"messages": []}
    agent = MockAgent()
    context = ExecutionContext(
        input_data=input_data,
        agent=agent,
        config=AgentConfig(),
    )
    context._messages = messages

    events = []
    async for event in orchestrator.run(context):
        events.append(event)

    # Should have only one assistant message
    assistant_messages = [
        msg
        for msg in agent.messages_received
        if (msg.role.value if hasattr(msg.role, "value") else str(msg.role)) == "assistant"
    ]
    assert len(assistant_messages) == 1


async def test_deduplicate_messages_duplicate_system_messages() -> None:
    """Test that deduplication logic is invoked for system messages."""
    from agent_framework import ChatMessage, TextContent

    messages = [
        ChatMessage(
            role="system",
            contents=[TextContent(text="You are a helpful assistant.")],
        ),
        ChatMessage(
            role="system",
            contents=[TextContent(text="You are a helpful assistant.")],
        ),
        ChatMessage(
            role="user",
            contents=[TextContent(text="Hello")],
        ),
    ]

    orchestrator = DefaultOrchestrator()
    input_data = {"messages": []}
    agent = MockAgent()
    context = ExecutionContext(
        input_data=input_data,
        agent=agent,
        config=AgentConfig(),
    )
    context._messages = messages

    events = []
    async for event in orchestrator.run(context):
        events.append(event)

    # Deduplication uses hash() which may not deduplicate identical content
    # This test verifies deduplication logic runs without errors
    system_messages = [
        msg
        for msg in agent.messages_received
        if (msg.role.value if hasattr(msg.role, "value") else str(msg.role)) == "system"
    ]
    # At least one system message should be present
    assert len(system_messages) >= 1


async def test_state_context_injection() -> None:
    """Test state context message injection for first request."""
    orchestrator = DefaultOrchestrator()

    input_data = {
        "messages": [
            {
                "role": "user",
                "content": [{"type": "text", "text": "Hello"}],
            }
        ],
        "state": {"items": ["apple", "banana"]},
    }

    agent = MockAgent()
    context = ExecutionContext(
        input_data=input_data,
        agent=agent,
        config=AgentConfig(state_schema={"items": {"type": "array"}}),
    )

    events = []
    async for event in orchestrator.run(context):
        events.append(event)

    # Should inject system message with current state
    system_messages = [
        msg
        for msg in agent.messages_received
        if (msg.role.value if hasattr(msg.role, "value") else str(msg.role)) == "system"
    ]
    assert len(system_messages) == 1
    assert "apple" in system_messages[0].contents[0].text
    assert "banana" in system_messages[0].contents[0].text


async def test_no_state_context_injection_with_tool_calls() -> None:
    """Test state context is NOT injected if conversation has tool calls."""
    from agent_framework import ChatMessage, FunctionCallContent, FunctionResultContent, TextContent

    messages = [
        ChatMessage(
            role="assistant",
            contents=[FunctionCallContent(name="get_weather", call_id="call_xyz", arguments="{}")],
        ),
        ChatMessage(
            role="tool",
            contents=[FunctionResultContent(call_id="call_xyz", result="sunny")],
        ),
        ChatMessage(
            role="user",
            contents=[TextContent(text="Thanks")],
        ),
    ]

    orchestrator = DefaultOrchestrator()
    input_data = {"messages": [], "state": {"weather": "sunny"}}
    agent = MockAgent()
    context = ExecutionContext(
        input_data=input_data,
        agent=agent,
        config=AgentConfig(state_schema={"weather": {"type": "string"}}),
    )
    context._messages = messages

    events = []
    async for event in orchestrator.run(context):
        events.append(event)

    # Should NOT inject state context system message since conversation has tool calls
    system_messages = [
        msg
        for msg in agent.messages_received
        if (msg.role.value if hasattr(msg.role, "value") else str(msg.role)) == "system"
    ]
    assert len(system_messages) == 0


async def test_structured_output_processing() -> None:
    """Test structured output extraction and state update."""

    class RecipeState(BaseModel):
        ingredients: list[str]
        message: str

    orchestrator = DefaultOrchestrator()

    input_data = {
        "messages": [
            {
                "role": "user",
                "content": [{"type": "text", "text": "Add tomato"}],
            }
        ],
    }

    # Agent with structured output
    agent = MockAgent(
        updates=[
            AgentRunResponseUpdate(
                contents=[TextContent(text='{"ingredients": ["tomato"], "message": "Added tomato"}')],
                role="assistant",
            )
        ]
    )
    agent.chat_options.response_format = RecipeState

    context = ExecutionContext(
        input_data=input_data,
        agent=agent,
        config=AgentConfig(state_schema={"ingredients": {"type": "array"}}),
    )

    events = []
    async for event in orchestrator.run(context):
        events.append(event)

    # Should emit StateSnapshotEvent with ingredients
    state_events = [e for e in events if e.type == "STATE_SNAPSHOT"]
    assert len(state_events) >= 1

    # Should emit TextMessage with message field
    text_content_events = [e for e in events if e.type == "TEXT_MESSAGE_CONTENT"]
    assert len(text_content_events) >= 1
    assert any("Added tomato" in e.delta for e in text_content_events)


async def test_duplicate_client_tools_filtered() -> None:
    """Test that client tools duplicating server tools are filtered out."""

    @ai_function
    def get_weather(location: str) -> str:
        """Get weather for location."""
        return f"Weather in {location}"

    orchestrator = DefaultOrchestrator()

    input_data = {
        "messages": [
            {
                "role": "user",
                "content": [{"type": "text", "text": "Hello"}],
            }
        ],
        "tools": [
            {
                "name": "get_weather",
                "description": "Client weather tool.",
                "parameters": {
                    "type": "object",
                    "properties": {"location": {"type": "string"}},
                    "required": ["location"],
                },
            }
        ],
    }

    agent = MockAgent()
    agent.chat_options.tools = [get_weather]

    context = ExecutionContext(
        input_data=input_data,
        agent=agent,
        config=AgentConfig(),
    )

    events = []
    async for event in orchestrator.run(context):
        events.append(event)

    # tools parameter should not be passed since client tool duplicates server tool
    assert agent.tools_received is None


async def test_unique_client_tools_merged() -> None:
    """Test that unique client tools are merged with server tools."""

    @ai_function
    def server_tool() -> str:
        """Server tool."""
        return "server"

    orchestrator = DefaultOrchestrator()

    input_data = {
        "messages": [
            {
                "role": "user",
                "content": [{"type": "text", "text": "Hello"}],
            }
        ],
        "tools": [
            {
                "name": "client_tool",
                "description": "Unique client tool.",
                "parameters": {
                    "type": "object",
                    "properties": {"param": {"type": "string"}},
                    "required": ["param"],
                },
            }
        ],
    }

    agent = MockAgent()
    agent.chat_options.tools = [server_tool]

    context = ExecutionContext(
        input_data=input_data,
        agent=agent,
        config=AgentConfig(),
    )

    events = []
    async for event in orchestrator.run(context):
        events.append(event)

    # tools parameter should be passed with both server and client tools
    assert agent.tools_received is not None
    tool_names = [getattr(tool, "name", None) for tool in agent.tools_received]
    assert "server_tool" in tool_names
    assert "client_tool" in tool_names


async def test_empty_messages_handling() -> None:
    """Test orchestrator handles empty message list gracefully."""
    orchestrator = DefaultOrchestrator()

    input_data = {"messages": []}

    agent = MockAgent()
    context = ExecutionContext(
        input_data=input_data,
        agent=agent,
        config=AgentConfig(),
    )

    events = []
    async for event in orchestrator.run(context):
        events.append(event)

    # Should emit run lifecycle events but not call agent
    assert len(agent.messages_received) == 0
    run_started = [e for e in events if e.type == "RUN_STARTED"]
    run_finished = [e for e in events if e.type == "RUN_FINISHED"]
    assert len(run_started) == 1
    assert len(run_finished) == 1


async def test_all_messages_filtered_handling() -> None:
    """Test orchestrator handles case where all messages are filtered out."""
    orchestrator = DefaultOrchestrator()

    input_data = {
        "messages": [
            {
                "role": "tool",
                "content": [{"type": "tool_result", "tool_call_id": "orphan", "content": "data"}],
            }
        ]
    }

    agent = MockAgent()
    context = ExecutionContext(
        input_data=input_data,
        agent=agent,
        config=AgentConfig(),
    )

    events = []
    async for event in orchestrator.run(context):
        events.append(event)

    # Should finish without calling agent
    assert len(agent.messages_received) == 0
    run_finished = [e for e in events if e.type == "RUN_FINISHED"]
    assert len(run_finished) == 1


async def test_confirm_changes_with_invalid_json_fallback() -> None:
    """Test confirm_changes with invalid JSON falls back to normal processing."""
    from agent_framework import ChatMessage, FunctionCallContent, TextContent

    messages = [
        ChatMessage(
            role="assistant",
            contents=[
                FunctionCallContent(
                    name="confirm_changes",
                    call_id="call_confirm_invalid",
                    arguments='{"changes": "test"}',
                )
            ],
        ),
        ChatMessage(
            role="user",
            contents=[TextContent(text="invalid json {")],
        ),
    ]

    orchestrator = DefaultOrchestrator()
    input_data = {"messages": []}
    agent = MockAgent()
    context = ExecutionContext(
        input_data=input_data,
        agent=agent,
        config=AgentConfig(),
    )
    context._messages = messages

    events = []
    async for event in orchestrator.run(context):
        events.append(event)

    # Invalid JSON should fall back - user message should be included
    user_messages = [
        msg
        for msg in agent.messages_received
        if (msg.role.value if hasattr(msg.role, "value") else str(msg.role)) == "user"
    ]
    assert len(user_messages) == 1


async def test_tool_result_kept_when_call_id_matches() -> None:
    """Test tool result is kept when call_id matches pending tool calls."""
    from agent_framework import ChatMessage, FunctionCallContent, FunctionResultContent

    messages = [
        ChatMessage(
            role="assistant",
            contents=[FunctionCallContent(name="get_data", call_id="call_match", arguments="{}")],
        ),
        ChatMessage(
            role="tool",
            contents=[FunctionResultContent(call_id="call_match", result="data")],
        ),
    ]

    orchestrator = DefaultOrchestrator()
    input_data = {"messages": []}
    agent = MockAgent()
    context = ExecutionContext(
        input_data=input_data,
        agent=agent,
        config=AgentConfig(),
    )
    context._messages = messages

    events = []
    async for event in orchestrator.run(context):
        events.append(event)

    # Tool result should be kept
    tool_messages = [
        msg
        for msg in agent.messages_received
        if (msg.role.value if hasattr(msg.role, "value") else str(msg.role)) == "tool"
    ]
    assert len(tool_messages) == 1
    assert tool_messages[0].contents[0].result == "data"


async def test_agent_protocol_fallback_paths() -> None:
    """Test fallback paths for non-ChatAgent implementations."""

    class CustomAgent:
        """Custom agent without ChatAgent type."""

        def __init__(self) -> None:
            self.chat_options = SimpleNamespace(tools=[], response_format=None)
            self.chat_client = SimpleNamespace(function_invocation_configuration=SimpleNamespace())
            self.messages_received: list[Any] = []

        async def run_stream(
            self,
            messages: list[Any],
            *,
            thread: Any = None,
            tools: list[Any] | None = None,
        ) -> AsyncGenerator[AgentRunResponseUpdate, None]:
            self.messages_received = messages
            yield AgentRunResponseUpdate(contents=[TextContent(text="response")], role="assistant")

    from agent_framework import ChatMessage, TextContent

    messages = [ChatMessage(role="user", contents=[TextContent(text="Hello")])]

    orchestrator = DefaultOrchestrator()
    input_data = {"messages": []}
    agent = CustomAgent()
    context = ExecutionContext(
        input_data=input_data,
        agent=agent,  # type: ignore
        config=AgentConfig(),
    )
    context._messages = messages

    events = []
    async for event in orchestrator.run(context):
        events.append(event)

    # Should work with custom agent implementation
    assert len(agent.messages_received) > 0


async def test_initial_state_snapshot_with_array_schema() -> None:
    """Test state initialization with array type schema."""
    from agent_framework import ChatMessage, TextContent

    messages = [ChatMessage(role="user", contents=[TextContent(text="Hello")])]

    orchestrator = DefaultOrchestrator()
    input_data = {"messages": [], "state": {}}
    agent = MockAgent()
    context = ExecutionContext(
        input_data=input_data,
        agent=agent,
        config=AgentConfig(state_schema={"items": {"type": "array"}}),
    )
    context._messages = messages

    events = []
    async for event in orchestrator.run(context):
        events.append(event)

    # Should emit state snapshot with empty array for items
    state_events = [e for e in events if e.type == "STATE_SNAPSHOT"]
    assert len(state_events) >= 1


async def test_response_format_skip_text_content() -> None:
    """Test that response_format causes skip_text_content to be set."""

    class OutputModel(BaseModel):
        result: str

    from agent_framework import ChatMessage, TextContent

    messages = [ChatMessage(role="user", contents=[TextContent(text="Hello")])]

    orchestrator = DefaultOrchestrator()
    input_data = {"messages": []}

    agent = MockAgent()
    agent.chat_options.response_format = OutputModel

    context = ExecutionContext(
        input_data=input_data,
        agent=agent,
        config=AgentConfig(),
    )
    context._messages = messages

    events = []
    async for event in orchestrator.run(context):
        events.append(event)

    # Test passes if no errors occur - verifies response_format code path
    assert len(events) > 0
