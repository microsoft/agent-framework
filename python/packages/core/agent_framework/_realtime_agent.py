# Copyright (c) Microsoft. All rights reserved.

"""RealtimeAgent for real-time voice conversations."""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any, ClassVar

from agent_framework._realtime_types import RealtimeEvent, RealtimeSessionConfig
from agent_framework._threads import AgentThread
from agent_framework._tools import FunctionTool
from agent_framework._types import Message

from ._agents import BaseAgent
from ._logging import get_logger

if TYPE_CHECKING:
    from agent_framework._realtime_client import RealtimeClientProtocol

logger = get_logger("agent_framework")

__all__ = ["RealtimeAgent", "execute_tool", "tool_to_schema"]


def tool_to_schema(tool: FunctionTool) -> dict[str, Any]:
    """Convert a tool to a schema dict for realtime providers.

    Args:
        tool: The tool to convert.

    Returns:
        A dict with type, name, description, and optional parameters.
    """
    schema: dict[str, Any] = {
        "type": "function",
        "name": tool.name,
        "description": tool.description,
    }
    if isinstance(tool, FunctionTool) and tool.input_model is not None:
        json_schema = tool.input_model.model_json_schema()
        schema["parameters"] = {
            "type": "object",
            "properties": json_schema.get("properties", {}),
            "required": json_schema.get("required", []),
        }
    return schema


async def execute_tool(
    tool_registry: dict[str, FunctionTool],
    tool_call: dict[str, Any],
) -> str:
    """Execute a realtime tool call and return the string result.

    Args:
        tool_registry: Mapping of tool name to tool instance.
        tool_call: The tool call event data containing 'name' and 'arguments'.

    Returns:
        The string result of the tool invocation, or an error message.
    """
    tool_name = tool_call.get("name", "")
    tool = tool_registry.get(tool_name)
    if not tool:
        return f"Unknown tool: {tool_name}"

    arguments_str = tool_call.get("arguments", "{}")
    try:
        arguments = json.loads(arguments_str) if isinstance(arguments_str, str) else arguments_str
    except json.JSONDecodeError:
        return f"Invalid arguments for {tool_name}: {arguments_str}"

    try:
        if isinstance(tool, FunctionTool):
            result = await tool.invoke(**arguments)
        else:
            return f"Tool '{tool_name}' is not a FunctionTool and cannot be executed in realtime sessions."
        return str(result)
    except Exception as e:
        return f"Error executing {tool_name}: {e}"


class RealtimeAgent(BaseAgent):
    """Agent for real-time voice conversations."""

    AGENT_PROVIDER_NAME: ClassVar[str] = "microsoft.agent_framework"

    def __init__(
        self,
        realtime_client: RealtimeClientProtocol,
        instructions: str | None = None,
        *,
        id: str | None = None,
        name: str | None = None,
        description: str | None = None,
        tools: list[FunctionTool] | None = None,
        voice: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize a RealtimeAgent instance.

        Args:
            realtime_client: The realtime client to use for audio streaming.
            instructions: System instructions for the agent.

        Keyword Args:
            id: Unique identifier. Auto-generated if not provided.
            name: Name of the agent.
            description: Description of the agent's purpose.
            tools: Tools available for function calling.
            voice: Voice ID for audio responses (e.g., "nova", "alloy").
            **kwargs: Additional properties passed to BaseAgent.
        """
        super().__init__(id=id, name=name, description=description, **kwargs)
        self._client = realtime_client
        self.instructions = instructions
        self._tools = tools or []
        self.voice = voice
        self._tool_registry: dict[str, FunctionTool] = {t.name: t for t in self._tools}

    async def run(
        self,
        audio_input: AsyncIterator[bytes],
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[RealtimeEvent]:

        if not thread:
            thread = self.get_new_thread()

        config = RealtimeSessionConfig(
            instructions=self.instructions,
            voice=self.voice,
            tools=[tool_to_schema(t) for t in self._tools] if self._tools else None,
        )

        await self._client.connect(config)

        all_messages: list[Message] = []

        try:
            send_task = asyncio.create_task(self._send_audio_loop(audio_input))

            try:
                async for event in self._process_events():
                    if event.type == "input_transcript":
                        text = event.data.get("text", "")
                        if text:
                            all_messages.append(Message(role="user", text=text))
                    elif event.type == "response_transcript":
                        text = event.data.get("text", "")
                        if text:
                            all_messages.append(Message(role="assistant", text=text))
                    yield event
            finally:
                send_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await send_task
        finally:
            await self._client.disconnect()
            input_messages = [m for m in all_messages if m.role == "user"]
            response_messages = [m for m in all_messages if m.role == "assistant"]
            if all_messages:
                await thread.on_new_messages(all_messages)
            if thread.context_provider:
                await thread.context_provider.invoked(input_messages, response_messages)

    async def _send_audio_loop(self, audio_input: AsyncIterator[bytes]) -> None:
        try:
            async for chunk in audio_input:
                await self._client.send_audio(chunk)
        except asyncio.CancelledError:
            logger.debug("Audio send loop cancelled — agent stopped receiving events.")

    async def _process_events(self) -> AsyncIterator[RealtimeEvent]:
        async for event in self._client.events():
            if event.type == "tool_call":
                call_id = event.data.get("id")
                if not call_id:
                    logger.error("Tool call event missing 'id', skipping: %s", event.data)
                    yield RealtimeEvent(
                        type="error",
                        data={"message": "Tool call event missing 'id'"},
                    )
                    continue
                result = await self._execute_tool(event.data)
                await self._client.send_tool_result(call_id, result)
                yield event
                yield RealtimeEvent(
                    type="tool_result",
                    data={"name": event.data.get("name", ""), "result": result},
                )
                continue
            yield event

    async def _execute_tool(self, tool_call: dict[str, Any]) -> str:
        """Execute a tool and return the result."""
        return await execute_tool(self._tool_registry, tool_call)

    def as_tool(self, **kwargs: Any) -> Any:
        """Not supported for RealtimeAgent.

        RealtimeAgent operates on audio streams, not text messages,
        so it cannot be wrapped as a text-based tool for multi-agent workflows.

        Raises:
            NotImplementedError: Always raised.
        """
        raise NotImplementedError(
            "RealtimeAgent cannot be used as a tool because it operates on audio streams. "
            "Use ChatAgent for text-based multi-agent workflows."
        )

    def _tool_to_schema(self, tool: FunctionTool) -> dict[str, Any]:
        """Convert a tool to a schema dict for the provider."""
        return tool_to_schema(tool)
