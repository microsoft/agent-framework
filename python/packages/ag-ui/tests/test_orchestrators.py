"""Tests for AG-UI orchestrators."""

from collections.abc import AsyncGenerator
from types import SimpleNamespace
from typing import Any

from agent_framework import AgentRunResponseUpdate, TextContent, ai_function
from agent_framework._tools import FunctionInvocationConfiguration

from agent_framework_ag_ui._agent import AgentConfig
from agent_framework_ag_ui._orchestrators import DefaultOrchestrator, ExecutionContext


@ai_function
def server_tool() -> str:
    """Server-executable tool."""
    return "server"


class DummyAgent:
    """Minimal agent stub to capture run_stream parameters."""

    def __init__(self) -> None:
        self.chat_options = SimpleNamespace(tools=[server_tool], response_format=None)
        self.tools = [server_tool]
        self.chat_client = SimpleNamespace(
            function_invocation_configuration=FunctionInvocationConfiguration(),
        )
        self.seen_tools: list[Any] | None = None

    async def run_stream(
        self,
        messages: list[Any],
        *,
        thread: Any,
        tools: list[Any] | None = None,
    ) -> AsyncGenerator[AgentRunResponseUpdate, None]:
        self.seen_tools = tools
        yield AgentRunResponseUpdate(contents=[TextContent(text="ok")], role="assistant")


async def test_default_orchestrator_merges_client_tools() -> None:
    """Client tool declarations are merged with server tools before running agent."""

    agent = DummyAgent()
    orchestrator = DefaultOrchestrator()

    input_data = {
        "messages": [
            {
                "role": "user",
                "content": [{"type": "input_text", "text": "Hello"}],
            }
        ],
        "tools": [
            {
                "name": "get_weather",
                "description": "Client weather lookup.",
                "parameters": {
                    "type": "object",
                    "properties": {"location": {"type": "string"}},
                    "required": ["location"],
                },
            }
        ],
    }

    context = ExecutionContext(
        input_data=input_data,
        agent=agent,
        config=AgentConfig(),
    )

    events = []
    async for event in orchestrator.run(context):
        events.append(event)

    assert agent.seen_tools is not None
    tool_names = [getattr(tool, "name", "?") for tool in agent.seen_tools]
    assert "server_tool" in tool_names
    assert "get_weather" in tool_names
    assert agent.chat_client.function_invocation_configuration.additional_tools
