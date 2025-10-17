# Copyright (c) Microsoft. All rights reserved.

import asyncio
from random import randint
from typing import Annotated, cast

from agent_framework import ChatMessage, Role, SequentialBuilder, WorkflowOutputEvent
from agent_framework.azure import AzureAIAgentClient, AzureOpenAIChatClient, AzureOpenAIResponsesClient
from azure.identity import AzureCliCredential
from azure.identity.aio import AzureCliCredential as AsyncAzureCliCredential
from pydantic import Field

"""
Sample: Cross-Framework Sequential Orchestration

This sample demonstrates how to orchestrate agents from different frameworks/clients
in a single sequential workflow. It shows how to handle:

1. Different client initialization patterns
2. Mixed async credential contexts (Azure AI requires async credentials)
3. Agents with different capabilities working together

The workflow demonstrates three different agent types:
- Azure AI Foundry Agent: Uses Azure AI Agent Service (async credential required)
- Azure OpenAI Responses Client: Lightweight structured response generation
- Azure OpenAI Chat Client: Standard conversational agent

Key insights:
- All agents implement the AgentProtocol, making them compatible with SequentialBuilder
- Azure AI agents require async credentials (azure.identity.aio.AzureCliCredential)
- Other Azure OpenAI clients use sync credentials (azure.identity.AzureCliCredential)
- The workflow manages the async context automatically for all participants
- Each agent maintains its own client instance and configuration

Prerequisites:
- Azure OpenAI access configured (az login + env vars)
- Azure AI Foundry project configured (for AzureAIAgentClient)
- Environment variables:
  - AZURE_OPENAI_ENDPOINT (for Chat/Responses clients)
  - AZUREAI_PROJECT_CONNECTION_STRING (for Azure AI Agent)
"""


def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
) -> str:
    """Get the weather for a given location."""
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    return f"The weather in {location} is {conditions[randint(0, 3)]} with a high of {randint(10, 30)}°C."


async def main() -> None:
    print("===== Cross-Framework Sequential Orchestration =====\n")

    # 1) Create agents from different frameworks/clients
    #    Note: Each client uses its own credential and configuration

    # Azure AI Foundry Agent - requires async credential
    # This agent uses the Azure AI Agent Service and supports advanced features
    # like code interpreter, file search, and MCP tools
    async with AsyncAzureCliCredential() as async_credential:
        azure_ai_client = AzureAIAgentClient(async_credential=async_credential)

        # Create Azure AI agent with function tools
        # The agent will be automatically created and managed by the client
        async with azure_ai_client.create_agent(
            name="WeatherExpert",
            instructions=(
                "You are a weather expert. When asked about weather, use the get_weather function. "
                "Provide the weather information in a friendly, conversational way."
            ),
            tools=get_weather,
        ) as weather_agent:

            # Azure OpenAI Responses Client - uses sync credential
            # This is a lightweight client for structured response generation
            responses_client = AzureOpenAIResponsesClient(credential=AzureCliCredential())
            activity_recommender = responses_client.create_agent(
                instructions=(
                    "You are an activity recommender. Based on the weather information provided, "
                    "suggest 2-3 appropriate outdoor or indoor activities. Keep it brief and practical."
                ),
                name="ActivityRecommender",
            )

            # Azure OpenAI Chat Client - uses sync credential
            # Standard chat client for conversational agents
            chat_client = AzureOpenAIChatClient(credential=AzureCliCredential())
            summarizer = chat_client.create_agent(
                instructions=(
                    "You are a helpful summarizer. Review the entire conversation and provide "
                    "a brief, friendly summary highlighting the key points."
                ),
                name="Summarizer",
            )

            # 2) Build sequential workflow with mixed framework agents
            #    The agents are executed in order: weather_agent -> activity_recommender -> summarizer
            #    Each agent receives the full conversation history and appends its response
            workflow = SequentialBuilder().participants([weather_agent, activity_recommender, summarizer]).build()

            # 3) Run the workflow with an initial prompt
            print("Starting workflow with prompt: 'What's the weather like in Seattle?'\n")

            outputs: list[list[ChatMessage]] = []
            async for event in workflow.run_stream("What's the weather like in Seattle?"):
                if isinstance(event, WorkflowOutputEvent):
                    outputs.append(cast(list[ChatMessage], event.data))

            # 4) Display the final conversation showing contributions from all agents
            if outputs:
                print("===== Final Conversation =====")
                for i, msg in enumerate(outputs[-1], start=1):
                    name = msg.author_name or ("assistant" if msg.role == Role.ASSISTANT else "user")
                    print(f"{'-' * 60}\n{i:02d} [{name}]\n{msg.text}")
                print()

    """
    Sample Output:

    ===== Cross-Framework Sequential Orchestration =====

    Starting workflow with prompt: 'What's the weather like in Seattle?'

    ===== Final Conversation =====
    ------------------------------------------------------------
    01 [user]
    What's the weather like in Seattle?
    ------------------------------------------------------------
    02 [WeatherExpert]
    The weather in Seattle is cloudy with a high of 18°C. It's a typical Pacific
    Northwest day with overcast skies and mild temperatures.
    ------------------------------------------------------------
    03 [ActivityRecommender]
    Based on the cloudy weather:
    1. Visit the Seattle Art Museum or MoPOP for indoor cultural exploration
    2. Take a scenic walk at Discovery Park - perfect for cloudy days
    3. Enjoy coffee tasting at Pike Place Market
    ------------------------------------------------------------
    04 [Summarizer]
    Seattle's weather today is cloudy with temperatures around 18°C. Great activities
    include indoor museum visits or a pleasant walk at Discovery Park. The mild
    conditions make it a nice day for both indoor and outdoor exploration!

    Key Takeaways:
    - Different frameworks/clients can be easily mixed in a single workflow
    - Azure AI agents work seamlessly with Azure OpenAI agents
    - Each agent maintains its own configuration and capabilities
    - The workflow handles async context management automatically
    - All agents share the conversation history via list[ChatMessage]
    """


if __name__ == "__main__":
    asyncio.run(main())
