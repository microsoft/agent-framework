# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
from random import randint
from typing import Annotated

from nvidia_nim_chat_client import NVIDIANIMChatClient

"""
NVIDIA NIM with OpenAI Chat Client Example

This sample demonstrates using NVIDIA NIM (NVIDIA Inference Microservices) models 
deployed on Azure AI Foundry through OpenAI Chat Client by configuring the base URL 
to point to the Azure AI Foundry endpoint for OpenAI-compatible API access.

## Prerequisites - Deploy NVIDIA NIM on Azure AI Foundry

Before running this example, you must first deploy a NVIDIA NIM model on Azure AI Foundry.
Follow the detailed instructions at:
https://developer.nvidia.com/blog/accelerated-ai-inference-with-nvidia-nim-on-azure-ai-foundry/#deploy_a_nim_on_azure_ai_foundry

### Quick Setup Steps:

1. **Access Azure AI Foundry Portal**
   - Navigate to https://ai.azure.com
   - Ensure you have a Hub and Project available

2. **Deploy NVIDIA NIM Model**
   - Select "Model Catalog" from the left sidebar
   - In the "Collections" filter, select "NVIDIA"
   - Choose a NIM microservice (e.g., Llama 3.1 8B Instruct NIM)
   - Click "Deploy"
   - Choose deployment name and VM type
   - Review pricing and terms of use
   - Click "Deploy" to launch the deployment

3. **Get API Credentials**
   - Once deployed, note your endpoint URL and API key
   - The endpoint URL should include '/v1' (e.g., 'https://<endpoint>.<region>.inference.ml.azure.com/v1')

## Environment Variables

Set the following environment variables before running this example:

- OPENAI_BASE_URL: Your Azure AI Foundry endpoint URL (e.g., 'https://<endpoint>.<region>.inference.ml.azure.com/v1')
- OPENAI_API_KEY: Your Azure AI Foundry API key
- OPENAI_CHAT_MODEL_ID: The NVIDIA NIM model to use (e.g., 'nvidia/llama-3.1-8b-instruct')

## API Compatibility

NVIDIA NIM models deployed on Azure AI Foundry expose an OpenAI-compatible API, making them 
easy to integrate with existing OpenAI-based applications and frameworks. The models support:

- Standard OpenAI Chat Completion API
- Streaming and non-streaming responses
- Tool calling capabilities
- System and user messages

For more information, see:
https://developer.nvidia.com/blog/accelerated-ai-inference-with-nvidia-nim-on-azure-ai-foundry/#openai_sdk_with_nim_on_azure_ai_foundry
"""


def get_weather(
    location: Annotated[str, "The location to get the weather for."],
) -> str:
    """Get the weather for a given location."""
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    return f"The weather in {location} is {conditions[randint(0, 3)]} with a high of {randint(10, 30)}°C."


def get_ai_insights(
    topic: Annotated[str, "The AI topic to get insights about."],
) -> str:
    """Get AI insights about a specific topic."""
    insights = [
        f"AI is revolutionizing {topic} through advanced machine learning techniques.",
        f"The future of {topic} lies in AI-powered automation and intelligent systems.",
        f"Recent breakthroughs in AI have significantly impacted {topic} development.",
        f"AI applications in {topic} are becoming more sophisticated and widespread."
    ]
    return insights[randint(0, len(insights) - 1)]


async def non_streaming_example() -> None:
    """Example of non-streaming response (get the complete result at once)."""
    print("=== Non-streaming Response Example ===")

    agent = NVIDIANIMChatClient(
        api_key=os.environ["OPENAI_API_KEY"],
        base_url=os.environ["OPENAI_BASE_URL"],
        model_id=os.environ["OPENAI_CHAT_MODEL_ID"],
    ).create_agent(
        name="NVIDIAAIAgent",
        instructions="You are a helpful AI assistant powered by NVIDIA NIM models. You can provide weather information and AI insights.",
        tools=[get_weather, get_ai_insights],
    )

    query = "What's the weather like in Seattle and tell me about AI in healthcare?"
    print(f"User: {query}")
    result = await agent.run(query)
    print(f"Result: {result}\n")


async def streaming_example() -> None:
    """Example of streaming response (get results as they are generated)."""
    print("=== Streaming Response Example ===")

    agent = NVIDIANIMChatClient(
        api_key=os.environ["OPENAI_API_KEY"],
        base_url=os.environ["OPENAI_BASE_URL"],
        model_id=os.environ["OPENAI_CHAT_MODEL_ID"],
    ).create_agent(
        name="NVIDIAAIAgent",
        instructions="You are a helpful AI assistant powered by NVIDIA NIM models. You can provide weather information and AI insights.",
        tools=[get_weather, get_ai_insights],
    )

    query = "What's the weather like in Portland and give me insights about AI in autonomous vehicles?"
    print(f"User: {query}")
    print("Agent: ", end="", flush=True)
    async for chunk in agent.run_stream(query):
        if chunk.text:
            print(chunk.text, end="", flush=True)
    print("\n")


async def main() -> None:
    print("=== NVIDIA NIM with OpenAI Chat Client Agent Example ===")
    print("This example demonstrates using NVIDIA NIM models deployed on Azure AI Foundry")
    print("through OpenAI-compatible API endpoints.\n")

    await non_streaming_example()
    await streaming_example()


if __name__ == "__main__":
    asyncio.run(main())
