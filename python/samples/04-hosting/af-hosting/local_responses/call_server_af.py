# Copyright (c) Microsoft. All rights reserved.

"""Agent Framework agent client for the local_responses sample.

Creates a local :class:`agent_framework.Agent` backed by
:class:`agent_framework.openai.OpenAIChatClient` and points that client at the
hosted ``/responses`` endpoint for both turns:

1. ``What is the weather in Tokyo?``
2. ``And what about Amsterdam?``

Both turns use the same :class:`agent_framework.AgentSession`; the first
turn binds the hosted response id to the session, and the second turn
continues through that session.

Start the server first (in another shell)::

    uv run python app.py

Then::

    uv run python call_server_af.py
"""

from __future__ import annotations

import asyncio

from agent_framework import Agent
from agent_framework.openai import OpenAIChatClient

BASE_URL = "http://127.0.0.1:8000"
PROMPTS = [
    "What is the weather in Tokyo?",
    "And what about Amsterdam?",
]


async def main() -> None:
    agent = Agent(
        client=OpenAIChatClient(base_url=BASE_URL, api_key="not-needed"),
        name="HostedWeatherClient",
    )
    session = agent.create_session()

    for prompt in PROMPTS:
        print(f"User: {prompt}")
        response = await agent.run(prompt, session=session)
        print(f"Agent: {response.text}\n")
        print(f"Response ID: {response.response_id}\n")


if __name__ == "__main__":
    asyncio.run(main())
