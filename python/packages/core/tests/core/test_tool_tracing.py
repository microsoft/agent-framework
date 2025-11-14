import asyncio
import os
from random import randint
from typing import Annotated
from pydantic import Field

from agent_framework.azure import AzureOpenAIChatClient
from azure.identity import AzureCliCredential
from agent_framework.observability import setup_observability

# Setup observability
setup_observability(
    applicationinsights_connection_string=os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING"),
    enable_sensitive_data=True,  # Important to see error details
)

def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
) -> str:
    """Get the weather for a given location."""
    raise ValueError("An example exception for testing purposes.")

async def main():
    agent = AzureOpenAIChatClient(credential=AzureCliCredential()).create_agent(
        instructions="You are a helpful weather agent.",
        tools=get_weather,
    )
    
    query = "What's the weather like in Seattle?"
    print(f"User: {query}")
    
    try:
        result = await agent.run(query)
        print(f"Result: {result}")
    except Exception as e:
        print(f"Expected error occurred: {e}")

if __name__ == "__main__":
    asyncio.run(main())
