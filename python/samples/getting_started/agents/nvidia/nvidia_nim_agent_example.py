# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
from random import randint
from typing import Annotated

from nvidia_nim_chat_client import NVIDIANIMChatClient

"""
NVIDIA NIM Agent Example

This sample demonstrates using NVIDIA NIM (NVIDIA Inference Microservices) models 
deployed on Azure AI Foundry with the Agent Framework. It uses a custom chat client
that handles NVIDIA NIM's specific message format requirements.

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

## Running the Example

After setting up your NVIDIA NIM deployment and environment variables:

```bash
# Set your environment variables
export OPENAI_BASE_URL="https://your-endpoint.region.inference.ml.azure.com/v1"
export OPENAI_API_KEY="your-api-key"
export OPENAI_CHAT_MODEL_ID="nvidia/llama-3.1-8b-instruct"

# Run the example
python nvidia_nim_agent_example.py
```

The example will demonstrate:
- Chat completion with NVIDIA NIM models
- Basic conversation capabilities

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


async def first_example() -> None:
    """First example response."""
    print("=== Response ===")

    agent = NVIDIANIMChatClient(
        api_key=os.environ["OPENAI_API_KEY"],
        base_url=os.environ["OPENAI_BASE_URL"],
        model_id=os.environ["OPENAI_CHAT_MODEL_ID"],
    ).create_agent(
        name="NVIDIAAIAgent",
    )

    query = "Hello! Can you tell me about yourself and what you can help with?"
    print(f"User: {query}")
    result = await agent.run(query)
    print(f"Agent: {result}\n")


async def second_example() -> None:
    """Second example response."""
    print("=== Response ===")

    agent = NVIDIANIMChatClient(
        api_key=os.environ["OPENAI_API_KEY"],
        base_url=os.environ["OPENAI_BASE_URL"],
        model_id=os.environ["OPENAI_CHAT_MODEL_ID"],
    ).create_agent(
        name="NVIDIAAIAgent",
    )

    query = "Can you explain what artificial intelligence is and how it works?"
    print(f"User: {query}")
    result = await agent.run(query)
    print(f"Agent: {result}\n")


async def main() -> None:
    print("=== NVIDIA NIM Agent Example ===")
    print("This example demonstrates using NVIDIA NIM models deployed on Azure AI Foundry")
    print("with the Agent Framework using a custom chat client.\n")

    await first_example()
    await second_example()


if __name__ == "__main__":
    asyncio.run(main())
