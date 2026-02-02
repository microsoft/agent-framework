# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
from random import randint
from typing import Annotated

from agent_framework.azure import AzureAIProjectAgentProvider
from azure.ai.projects.aio import AIProjectClient
from azure.ai.projects.models import AgentReference, PromptAgentDefinition
from azure.identity.aio import AzureCliCredential
from pydantic import Field
from agent_framework import tool

"""
Azure AI Project Agent Provider Methods Example

This sample demonstrates the three main methods of AzureAIProjectAgentProvider:
1. create_agent() - Create a new agent on the Azure AI service
2. get_agent() - Retrieve an existing agent from the service
3. as_agent() - Wrap an SDK agent version object without making HTTP calls

It also shows how to use a single provider instance to spawn multiple agents
with different configurations, which is efficient for multi-agent scenarios.

Each method returns a ChatAgent that can be used for conversations.
"""

# NOTE: approval_mode="never_require" is for sample brevity. Use "always_require" in production; see samples/getting_started/tools/function_tool_with_approval.py and samples/getting_started/tools/function_tool_with_approval_and_threads.py.
@tool(approval_mode="never_require")
def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
) -> str:
    """Get the weather for a given location."""
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    return f"The weather in {location} is {conditions[randint(0, 3)]} with a high of {randint(10, 30)}C."


async def create_agent_example() -> None:
    """Example of using provider.create_agent() to create a new agent.

    This method creates a new agent version on the Azure AI service and returns
    a ChatAgent. Use this when you want to create a fresh agent with
    specific configuration.
    """
    print("=== provider.create_agent() Example ===")

    async with (
        AzureCliCredential() as credential,
        AzureAIProjectAgentProvider(credential=credential) as provider,
    ):
        # Create a new agent with custom configuration
        agent = await provider.create_agent(
            name="WeatherAssistant",
            instructions="You are a helpful weather assistant. Always be concise.",
            description="An agent that provides weather information.",
            tools=get_weather,
        )

        print(f"Created agent: {agent.name}")
        print(f"Agent ID: {agent.id}")

        query = "What's the weather in Paris?"
        print(f"User: {query}")
        result = await agent.run(query)
        print(f"Agent: {result}\n")


async def get_agent_by_name_example() -> None:
    """Example of using provider.get_agent(name=...) to retrieve an agent by name.

    This method fetches the latest version of an existing agent from the service.
    Use this when you know the agent name and want to use the most recent version.
    """
    print("=== provider.get_agent(name=...) Example ===")

    async with (
        AzureCliCredential() as credential,
        AIProjectClient(endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"], credential=credential) as project_client,
    ):
        # First, create an agent using the SDK directly
        created_agent = await project_client.agents.create_version(
            agent_name="TestAgentByName",
            description="Test agent for get_agent by name example.",
            definition=PromptAgentDefinition(
                model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
                instructions="You are a helpful assistant. End each response with '- Your Assistant'.",
            ),
        )

        try:
            # Get the agent using the provider by name (fetches latest version)
            provider = AzureAIProjectAgentProvider(project_client=project_client)
            agent = await provider.get_agent(name=created_agent.name)

            print(f"Retrieved agent: {agent.name}")

            query = "Hello!"
            print(f"User: {query}")
            result = await agent.run(query)
            print(f"Agent: {result}\n")
        finally:
            # Clean up the agent
            await project_client.agents.delete_version(
                agent_name=created_agent.name, agent_version=created_agent.version
            )


async def get_agent_by_reference_example() -> None:
    """Example of using provider.get_agent(reference=...) to retrieve a specific agent version.

    This method fetches a specific version of an agent using an AgentReference.
    Use this when you need to use a particular version of an agent.
    """
    print("=== provider.get_agent(reference=...) Example ===")

    async with (
        AzureCliCredential() as credential,
        AIProjectClient(endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"], credential=credential) as project_client,
    ):
        # First, create an agent using the SDK directly
        created_agent = await project_client.agents.create_version(
            agent_name="TestAgentByReference",
            description="Test agent for get_agent by reference example.",
            definition=PromptAgentDefinition(
                model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
                instructions="You are a helpful assistant. Always respond in uppercase.",
            ),
        )

        try:
            # Get the agent using an AgentReference with specific version
            provider = AzureAIProjectAgentProvider(project_client=project_client)
            reference = AgentReference(name=created_agent.name, version=created_agent.version)
            agent = await provider.get_agent(reference=reference)

            print(f"Retrieved agent: {agent.name} (version via reference)")

            query = "Say hello"
            print(f"User: {query}")
            result = await agent.run(query)
            print(f"Agent: {result}\n")
        finally:
            # Clean up the agent
            await project_client.agents.delete_version(
                agent_name=created_agent.name, agent_version=created_agent.version
            )


async def multiple_agents_example() -> None:
    """Example of using a single provider to spawn multiple agents.

    A single provider instance can create multiple agents with different
    configurations.
    """
    print("=== Multiple Agents from Single Provider Example ===")

    async with (
        AzureCliCredential() as credential,
        AzureAIProjectAgentProvider(credential=credential) as provider,
    ):
        # Create multiple specialized agents from the same provider
        weather_agent = await provider.create_agent(
            name="WeatherExpert",
            instructions="You are a weather expert. Provide brief weather information.",
            tools=get_weather,
        )

        translator_agent = await provider.create_agent(
            name="Translator",
            instructions="You are a translator. Translate any text to French. Only output the translation.",
        )

        poet_agent = await provider.create_agent(
            name="Poet",
            instructions="You are a poet. Respond to everything with a short haiku.",
        )

        print(f"Created agents: {weather_agent.name}, {translator_agent.name}, {poet_agent.name}\n")

        # Use each agent for its specialty
        weather_query = "What's the weather in London?"
        print(f"User to WeatherExpert: {weather_query}")
        weather_result = await weather_agent.run(weather_query)
        print(f"WeatherExpert: {weather_result}\n")

        translate_query = "Hello, how are you today?"
        print(f"User to Translator: {translate_query}")
        translate_result = await translator_agent.run(translate_query)
        print(f"Translator: {translate_result}\n")

        poet_query = "Tell me about the morning sun"
        print(f"User to Poet: {poet_query}")
        poet_result = await poet_agent.run(poet_query)
        print(f"Poet: {poet_result}\n")


async def as_agent_example() -> None:
    """Example of using provider.as_agent() to wrap an SDK object without HTTP calls.

    This method wraps an existing AgentVersionDetails into a ChatAgent without
    making additional HTTP calls. Use this when you already have the full
    AgentVersionDetails from a previous SDK operation.
    """
    print("=== provider.as_agent() Example ===")

    async with (
        AzureCliCredential() as credential,
        AIProjectClient(endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"], credential=credential) as project_client,
    ):
        # Create an agent using the SDK directly - this returns AgentVersionDetails
        agent_version_details = await project_client.agents.create_version(
            agent_name="TestAgentAsAgent",
            description="Test agent for as_agent example.",
            definition=PromptAgentDefinition(
                model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
                instructions="You are a helpful assistant. Keep responses under 20 words.",
            ),
        )

        try:
            # Wrap the SDK object directly without any HTTP calls
            provider = AzureAIProjectAgentProvider(project_client=project_client)
            agent = provider.as_agent(agent_version_details)

            print(f"Wrapped agent: {agent.name} (no HTTP call needed)")
            print(f"Agent version: {agent_version_details.version}")

            query = "What can you do?"
            print(f"User: {query}")
            result = await agent.run(query)
            print(f"Agent: {result}\n")
        finally:
            # Clean up the agent
            await project_client.agents.delete_version(
                agent_name=agent_version_details.name, agent_version=agent_version_details.version
            )


async def main() -> None:
    print("=== Azure AI Project Agent Provider Methods Example ===\n")

    await create_agent_example()
    await get_agent_by_name_example()
    await get_agent_by_reference_example()
    await as_agent_example()
    await multiple_agents_example()


if __name__ == "__main__":
    asyncio.run(main())
