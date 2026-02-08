# Copyright (c) Microsoft. All rights reserved.

import asyncio
import logging

from agent_framework import ChatAgent, tool

from agent_framework_bedrock import BedrockChatClient


@tool(approval_mode="never_require")
def get_weather(city: str) -> dict[str, str]:
    """Return a mock forecast for the requested city."""
    normalized = city.strip() or "New York"
    return {"city": normalized, "forecast": "72F and sunny"}


async def main() -> None:
    """Run the Bedrock sample agent, invoke the weather tool, and log the response."""
    agent = ChatAgent(
        chat_client=BedrockChatClient(),
        instructions="You are a concise travel assistant.",
        name="BedrockWeatherAgent",
        tool_choice="auto",
        tools=[get_weather],
    )

    response = await agent.run("Use the weather tool to check the forecast for new york.")
    logging.info("\nAssistant reply:", response.text or "<no text returned>")
    logging.info("\nConversation transcript:")
    for message in response.messages:
        for idx, content in enumerate(message.contents, start=1):
            match content.type:
                case "text":
                    logging.info(f"  {idx}. text -> {content.text}")
                case "function_call":
                    logging.info(f"  {idx}. function_call ({content.name}) -> {content.arguments}")
                case "function_result":
                    logging.info(f"  {idx}. function_result ({content.call_id}) -> {content.result}")
                case _:
                    logging.info(f"  {idx}. {content.type}")


if __name__ == "__main__":
    asyncio.run(main())
