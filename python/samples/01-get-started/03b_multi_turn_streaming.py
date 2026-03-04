# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os

from agent_framework.azure import AzureOpenAIResponsesClient
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

"""
Multi-Turn Streaming — Combine streaming output with session history

This sample shows how to stream responses while maintaining conversation
history across turns. The key is calling get_final_response() after
iterating the stream, which persists messages to the session.

Without get_final_response(), the session history is not updated and
the agent will not remember previous turns.

Environment variables:
  AZURE_AI_PROJECT_ENDPOINT        — Your Azure AI Foundry project endpoint
  AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME — Model deployment name (e.g. gpt-4o)
"""


async def main() -> None:
    # 1. Create the client and agent.
    credential = AzureCliCredential()
    client = AzureOpenAIResponsesClient(
        project_endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
        deployment_name=os.environ["AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME"],
        credential=credential,
    )

    agent = client.as_agent(
        name="ConversationAgent",
        instructions="You are a friendly assistant. Keep your answers brief.",
    )

    # 2. Create a session to maintain conversation history.
    session = agent.create_session()

    # 3. First turn — stream the response, then finalize to save history.
    print("Agent: ", end="")
    stream = agent.run("My name is Alice and I love hiking.", session=session, stream=True)
    async for chunk in stream:
        if chunk.text:
            print(chunk.text, end="", flush=True)
    await stream.get_final_response()  # Persists messages to the session
    print("\n")

    # 4. Second turn — the agent remembers context from the first turn.
    print("Agent: ", end="")
    stream = agent.run("What do you remember about me?", session=session, stream=True)
    async for chunk in stream:
        if chunk.text:
            print(chunk.text, end="", flush=True)
    await stream.get_final_response()
    print()


if __name__ == "__main__":
    asyncio.run(main())

"""
Sample output:

Agent: Hi Alice! That's awesome — hiking is such a great way to stay active
and enjoy nature. Do you have a favorite trail or spot you like to hike?

Agent: You're Alice, and you love hiking!
"""
