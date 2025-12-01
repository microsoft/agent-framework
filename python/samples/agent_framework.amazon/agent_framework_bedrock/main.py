from __future__ import annotations

import asyncio

from typing import Sequence

from agent_framework import (
    AgentRunResponse,
    ChatAgent,
    FunctionCallContent,
    FunctionResultContent,
    Role,
    TextContent,
    ToolMode,
    ai_function,
)
from agent_framework_bedrock import BedrockChatClient


@ai_function
def get_weather(city: str) -> dict[str, str]:
    """Return a mock forecast for the requested city."""

    normalized = city.strip() or "New york"
    return {"city": normalized, "forecast": "72F and sunny"}


async def main() -> None:
    agent = ChatAgent(
        chat_client=BedrockChatClient(),
        instructions="You are a concise travel assistant.",
        name="BedrockWeatherAgent",
        tool_choice=ToolMode.AUTO,
        tools=[get_weather],
    )

    response = await agent.run("Use the weather tool to check the forecast for new york.")
    print("\nAssistant reply:", response.text or "<no text returned>")
    _log_response(response)


def _log_response(response: AgentRunResponse) -> None:
    print("\nConversation transcript:")
    for idx, message in enumerate(response.messages, start=1):
        tag = f"{idx}. {message.role.value if isinstance(message.role, Role) else message.role}"
        _log_contents(tag, message.contents)


def _log_contents(tag: str, contents: Sequence[object]) -> None:
    print(f"[{tag}] {len(contents)} content blocks")
    for idx, content in enumerate(contents, start=1):
        if isinstance(content, TextContent):
            print(f"  {idx}. text -> {content.text}")
        elif isinstance(content, FunctionCallContent):
            print(f"  {idx}. tool_call ({content.name}) -> {content.arguments}")
        elif isinstance(content, FunctionResultContent):
            print(f"  {idx}. tool_result ({content.call_id}) -> {content.result}")
        else:  # pragma: no cover - defensive
            print(f"  {idx}. {content.type}")


if __name__ == "__main__":
    asyncio.run(main())
