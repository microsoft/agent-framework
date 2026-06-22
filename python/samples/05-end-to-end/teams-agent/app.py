# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "microsoft-teams-apps",
#   "agent-framework-core",
#   "agent-framework-openai",
# ]
# ///
# Copyright (c) Microsoft. All rights reserved.
# Run with any PEP 723 compatible runner, e.g.:
#   uv run samples/05-end-to-end/teams-agent/app.py

import asyncio
import logging
import os
from random import randint
from typing import Annotated

from agent_framework import Agent, AgentSession, tool
from agent_framework.openai import OpenAIChatClient
from dotenv import load_dotenv
from microsoft_teams.api import CardAction, CardActionType, MessageActivity, MessageActivityInput, SuggestedActions
from microsoft_teams.apps import ActivityContext, App
from pydantic import Field

# Load environment variables from .env file
load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

"""
Demo application using the Microsoft Teams SDK (teams.py).

This sample demonstrates how to build an AI agent using the Agent Framework,
hosted as a Microsoft Teams bot through the Teams SDK.

Key features:
- Loads OpenAI credentials and Teams bot configuration from environment variables.
- Demonstrates agent creation and tool registration.
- Streams the agent response token-by-token into the Teams chat.
- Maintains per-conversation AgentSession for multi-turn memory.

To run, set the Teams bot credentials and OpenAI credentials (check .env.example),
then point your bot's messaging endpoint at this app (e.g. via a dev tunnel).
"""


# NOTE: approval_mode="never_require" is for sample brevity. Use "always_require" in
# production; see samples/02-agents/tools/function_tool_with_approval.py.
@tool(approval_mode="never_require")
def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
) -> str:
    """Generate a mock weather report for the provided location."""
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    return f"The weather in {location} is {conditions[randint(0, 3)]} with a high of {randint(10, 30)}°C."


def build_agent() -> Agent:
    """Create and return the agent instance with the weather tool registered."""
    # Reads AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY, and AZURE_OPENAI_CHAT_COMPLETION_MODEL from the environment.
    client = OpenAIChatClient()
    return Agent(
        client=client,
        name="WeatherAgent",
        instructions="You are a helpful weather agent. Keep your answers brief.",
        tools=get_weather,
    )


# Reads CLIENT_ID, CLIENT_SECRET, TENANT_ID, and PORT from the environment.
app = App()
agent = build_agent()

# Per-conversation sessions preserve message history across turns.
_sessions: dict[str, AgentSession] = {}


@app.on_message
async def handle_message(ctx: ActivityContext[MessageActivity]) -> None:
    """Run the agent for each incoming Teams message and stream the reply back."""
    try:
        conversation_id = ctx.activity.conversation.id
        session = _sessions.setdefault(conversation_id, agent.create_session())

        text = ctx.activity.text or ""
        if not text.strip():
            return

        async for chunk in agent.run(text, session=session, stream=True):
            if chunk.text:
                ctx.stream.emit(chunk.text)

        # Add suggested follow-up questions and AI generated label after streaming completes
        suggested_actions = SuggestedActions(
            to=[ctx.activity.from_.id],
            actions=[
                CardAction(type=CardActionType.IM_BACK, title="New York weather", value="What's the weather in New York?"),
                CardAction(type=CardActionType.IM_BACK, title="San Francisco weather", value="What's the weather in San Francisco?"),
            ],
        )
        reply = MessageActivityInput().add_ai_generated().add_feedback()
        reply.with_suggested_actions(suggested_actions)
        ctx.stream.emit(reply)
    except Exception as e:
        logger.exception("Error handling message: %s", e)
        await ctx.send(f"Sorry, an error occurred: {e}")


def main() -> None:
    """Entry point: start the Teams bot HTTP listener."""
    asyncio.run(app.start())


if __name__ == "__main__":
    main()
