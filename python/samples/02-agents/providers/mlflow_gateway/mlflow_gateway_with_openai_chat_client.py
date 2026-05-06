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
MLflow AI Gateway's OpenAI passthrough endpoint, which forwards calls
to the provider's Responses API.

MLflow AI Gateway (MLflow >= 3.0) is a database-backed LLM proxy that
provides a unified API across multiple providers (OpenAI, Anthropic,
Gemini, Mistral, Bedrock, Ollama, and more) with built-in secrets
management, fallback/retry, traffic splitting, and budget tracking.
Provider API keys are stored encrypted on the server.

This sample uses ``OpenAIChatClient`` (Responses API) and the OpenAI
passthrough at ``/gateway/openai/v1``. The Responses API is OpenAI-
specific; use this sample only with OpenAI-backed gateway endpoints. For
provider-agnostic routing, see the companion
``mlflow_gateway_with_openai_chat_completion_client.py`` sample.

Setup:
    pip install 'mlflow[genai]'
    mlflow server --host 127.0.0.1 --port 5000

Then create an OpenAI-backed gateway endpoint in the MLflow UI at
http://localhost:5000 under AI Gateway -> Create Endpoint.

Environment Variables:
- MLFLOW_GATEWAY_ENDPOINT: Base URL for the gateway's OpenAI passthrough
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


async def main() -> None:
    print("=== MLflow AI Gateway with OpenAI Chat Client Agent Example ===")

    client = OpenAIChatClient(
        api_key="unused",  # Provider keys are managed by the MLflow server
        base_url=os.environ["MLFLOW_GATEWAY_ENDPOINT"],
        model=os.environ["MLFLOW_GATEWAY_MODEL"],
    )
    agent = Agent(
        client=client,
        name="WeatherAgent",
        instructions="You are a helpful weather agent.",
        tools=[get_weather],
    )

    query = "What's the weather like in Seattle?"
    print(f"User: {query}")
    print("Agent: ", end="", flush=True)
    async for chunk in agent.run(query, stream=True):
        if chunk.text:
            print(chunk.text, end="", flush=True)
    print()


if __name__ == "__main__":
    asyncio.run(main())
