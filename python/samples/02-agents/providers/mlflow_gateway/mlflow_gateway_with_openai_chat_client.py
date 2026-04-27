# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
from random import randint
from typing import Annotated

from agent_framework import Agent, tool
from agent_framework.openai import OpenAIChatClient
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

"""
MLflow AI Gateway with OpenAI Chat Client Example

This sample demonstrates routing Agent Framework requests through the
MLflow AI Gateway using the OpenAI-compatible passthrough endpoint.

MLflow AI Gateway (MLflow >= 3.0) is a database-backed LLM proxy that
provides a unified API across multiple providers (OpenAI, Anthropic,
Gemini, Mistral, Bedrock, Ollama, and more) with built-in secrets
management, fallback/retry, traffic splitting, and budget tracking.
Provider API keys are stored encrypted on the server.

Setup:
    pip install mlflow[genai]
    mlflow server --host 127.0.0.1 --port 5000

Then create a gateway endpoint in the MLflow UI at http://localhost:5000
under AI Gateway -> Create Endpoint, select a provider and model, and
enter your provider API key.

Environment Variables:
- MLFLOW_GATEWAY_ENDPOINT: Base URL for the gateway's OpenAI-compatible
  endpoint (e.g., "http://localhost:5000/gateway/openai/v1/")
- MLFLOW_GATEWAY_MODEL: The gateway endpoint name you created in the
  MLflow UI (e.g., "my-chat-endpoint")

See: https://mlflow.org/docs/latest/genai/governance/ai-gateway/
"""


# NOTE: approval_mode="never_require" is for sample brevity. Use "always_require" in production;
# see samples/02-agents/tools/function_tool_with_approval.py
# and samples/02-agents/tools/function_tool_with_approval_and_sessions.py.
@tool(approval_mode="never_require")
def get_weather(
    location: Annotated[str, "The location to get the weather for."],
) -> str:
    """Get the weather for a given location."""
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    return f"The weather in {location} is {conditions[randint(0, 3)]} with a high of {randint(10, 30)}°C."


async def non_streaming_example() -> None:
    """Example of non-streaming response (get the complete result at once)."""
    print("=== Non-streaming Response Example ===")

    _client = OpenAIChatClient(
        api_key="unused",  # Provider keys are managed by the MLflow server
        base_url=os.getenv("MLFLOW_GATEWAY_ENDPOINT"),
        model=os.getenv("MLFLOW_GATEWAY_MODEL"),
    )
    agent = Agent(
        client=_client,
        name="WeatherAgent",
        instructions="You are a helpful weather agent.",
        tools=[get_weather],
    )

    query = "What's the weather like in Seattle?"
    print(f"User: {query}")
    result = await agent.run(query)
    print(f"Agent: {result}\n")


async def streaming_example() -> None:
    """Example of streaming response (get results as they are generated)."""
    print("=== Streaming Response Example ===")

    _client = OpenAIChatClient(
        api_key="unused",  # Provider keys are managed by the MLflow server
        base_url=os.getenv("MLFLOW_GATEWAY_ENDPOINT"),
        model=os.getenv("MLFLOW_GATEWAY_MODEL"),
    )
    agent = Agent(
        client=_client,
        name="WeatherAgent",
        instructions="You are a helpful weather agent.",
        tools=[get_weather],
    )

    query = "What's the weather like in Portland?"
    print(f"User: {query}")
    print("Agent: ", end="", flush=True)
    async for chunk in agent.run(query, stream=True):
        if chunk.text:
            print(chunk.text, end="", flush=True)
    print("\n")


async def main() -> None:
    print("=== MLflow AI Gateway with OpenAI Chat Client Agent Example ===")

    await non_streaming_example()
    await streaming_example()


if __name__ == "__main__":
    asyncio.run(main())
