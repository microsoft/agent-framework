# agent.py
import asyncio
from agent_framework import Agent
# from agent_framework.openai import OpenAIChatClient   # Option A
from agent_framework.foundry import FoundryChatClient    # Option B
from azure.identity import AzureCliCredential


def get_weather(location: str) -> str:
    """Get the weather for a location."""
    return f"Weather in {location}: 72°F and sunny"


agent = Agent(
    name="WeatherAgent",
    instructions="You are a friendly assistant. Keep your answers brief.",
    # client=OpenAIChatClient(),                                    # Option A
    # Option B — reads FOUNDRY_PROJECT_ENDPOINT and FOUNDRY_MODEL from the environment.
    # Set them before running, e.g.:
    #   export FOUNDRY_PROJECT_ENDPOINT="https://<account>.services.ai.azure.com/api/projects/<project>"
    #   export FOUNDRY_MODEL="<your-model-deployment-name>"
    client=FoundryChatClient(credential=AzureCliCredential()),
    tools=[get_weather],
)


async def main():
    print(await agent.run("What's the weather in Seattle?"))


if __name__ == "__main__":
    asyncio.run(main())
