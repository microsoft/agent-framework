# Get Started with Microsoft Agent Framework for Python Developers

## Quick Install

We recommend two common installation paths depending on your use case.

### 1. Development mode

If you are exploring or developing locally, install the entire framework with all sub-packages:

```bash
pip install agent-framework --pre
```

This installs the core and every integration package, making sure that all features are available without additional steps. The `--pre` flag is required while Agent Framework is in preview. This is the simplest way to get started.

### 2. Selective install

If you only need specific integrations, you can install at a more granular level. This keeps dependencies lighter and focuses on what you actually plan to use. Some examples:

```bash
# Core only
# includes Azure OpenAI and OpenAI support by default
# also includes workflows and orchestrations
pip install agent-framework-core --pre

# Core + Azure AI integration
pip install agent-framework-azure-ai --pre

# Core + Microsoft Copilot Studio integration
pip install agent-framework-copilotstudio --pre

# Core + both Microsoft Copilot Studio and Azure AI integration
pip install agent-framework-microsoft agent-framework-azure-ai --pre
```

This selective approach is useful when you know which integrations you need, and it is the recommended way to set up lightweight environments.

Supported Platforms:

- Python: 3.10+
- OS: Windows, macOS, Linux

## 1. Setup API Keys

Set as environment variables, or create a .env file at your project root:

```bash
OPENAI_API_KEY=sk-...
OPENAI_CHAT_MODEL_ID=...
...
AZURE_OPENAI_API_KEY=...
AZURE_OPENAI_ENDPOINT=...
AZURE_OPENAI_CHAT_DEPLOYMENT_NAME=...
...
AZURE_AI_PROJECT_ENDPOINT=...
AZURE_AI_MODEL_DEPLOYMENT_NAME=...
```

You can also override environment variables by explicitly passing configuration parameters to the chat client constructor:

```python
from agent_framework.azure import AzureOpenAIChatClient

chat_client = AzureOpenAIChatClient(
    api_key='',
    endpoint='',
    deployment_name='',
    api_version='',
)
```

See the following [setup guide](https://github.com/microsoft/agent-framework/tree/main/python/samples/getting_started) for more information.

## 2. Create a Simple Agent

Create agents and invoke them directly:

```python
import asyncio
from agent_framework import ChatAgent
from agent_framework.openai import OpenAIChatClient

async def main():
    agent = ChatAgent(
        chat_client=OpenAIChatClient(),
        instructions="""
        1) A robot may not injure a human being...
        2) A robot must obey orders given it by human beings...
        3) A robot must protect its own existence...

        Give me the TLDR in exactly 5 words.
        """
    )

    result = await agent.run("Summarize the Three Laws of Robotics")
    print(result)

asyncio.run(main())
# Output: Protect humans, obey, self-preserve, prioritized.
```

## 3. Directly Use Chat Clients (No Agent Required)

You can use the chat client classes directly for advanced workflows:

```python
import asyncio
from agent_framework import ChatMessage
from agent_framework.openai import OpenAIChatClient

async def main():
    client = OpenAIChatClient()

    messages = [
        ChatMessage(role="system", text="You are a helpful assistant."),
        ChatMessage(role="user", text="Write a haiku about Agent Framework.")
    ]

    response = await client.get_response(messages)
    print(response.messages[0].text)

    """
    Output:

    Agents work in sync,
    Framework threads through each task—
    Code sparks collaboration.
    """

asyncio.run(main())
```

## 4. Build an Agent with Tools and Functions

Enhance your agent with custom tools and function calling:

```python
import asyncio
from typing import Annotated
from random import randint
from pydantic import Field
from agent_framework import ChatAgent
from agent_framework.openai import OpenAIChatClient


def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
) -> str:
    """Get the weather for a given location."""
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    return f"The weather in {location} is {conditions[randint(0, 3)]} with a high of {randint(10, 30)}°C."


def get_menu_specials() -> str:
    """Get today's menu specials."""
    return """
    Special Soup: Clam Chowder
    Special Salad: Cobb Salad
    Special Drink: Chai Tea
    """


async def main():
    agent = ChatAgent(
        chat_client=OpenAIChatClient(),
        instructions="You are a helpful assistant that can provide weather and restaurant information.",
        tools=[get_weather, get_menu_specials]
    )

    response = await agent.run("What's the weather in Amsterdam and what are today's specials?")
    print(response)

    """
    Output:
    The weather in Amsterdam is sunny with a high of 22°C. Today's specials include
    Clam Chowder soup, Cobb Salad, and Chai Tea as the special drink.
    """

if __name__ == "__main__":
    asyncio.run(main())
```

You can explore additional agent samples [here](https://github.com/microsoft/agent-framework/tree/main/python/samples/getting_started/agents).

## 5. Multi-Agent Orchestration

Coordinate multiple agents to collaborate on complex tasks using orchestration patterns:

```python
import asyncio
from agent_framework import ChatAgent
from agent_framework.openai import OpenAIChatClient


async def main():
    # Create specialized agents
    writer = ChatAgent(
        chat_client=OpenAIChatClient(),
        name="Writer",
        instructions="You are a creative content writer. Generate and refine slogans based on feedback."
    )

    reviewer = ChatAgent(
        chat_client=OpenAIChatClient(),
        name="Reviewer",
        instructions="You are a critical reviewer. Provide detailed feedback on proposed slogans."
    )

    # Sequential workflow: Writer creates, Reviewer provides feedback
    task = "Create a slogan for a new electric SUV that is affordable and fun to drive."

    # Step 1: Writer creates initial slogan
    initial_result = await writer.run(task)
    print(f"Writer: {initial_result}")

    # Step 2: Reviewer provides feedback
    feedback_request = f"Please review this slogan: {initial_result}"
    feedback = await reviewer.run(feedback_request)
    print(f"Reviewer: {feedback}")

    # Step 3: Writer refines based on feedback
    refinement_request = f"Please refine this slogan based on the feedback: {initial_result}\nFeedback: {feedback}"
    final_result = await writer.run(refinement_request)
    print(f"Final Slogan: {final_result}")

    # Example Output:
    # Writer: "Charge Forward: Affordable Adventure Awaits!"
    # Reviewer: "Good energy, but 'Charge Forward' is overused in EV marketing..."
    # Final Slogan: "Power Up Your Adventure: Premium Feel, Smart Price!"

if __name__ == "__main__":
    asyncio.run(main())
```

**Note**: Advanced orchestration patterns like GroupChat, Sequential, and Concurrent orchestrations are coming soon.

## More Examples & Samples

- [Getting Started with Agents](https://github.com/microsoft/agent-framework/tree/main/python/samples/getting_started/agents): Basic agent creation and tool usage
- [Chat Client Examples](https://github.com/microsoft/agent-framework/tree/main/python/samples/getting_started/chat_client): Direct chat client usage patterns
- [Azure AI Integration](https://github.com/microsoft/agent-framework/tree/main/python/packages/azure-ai): Azure AI integration
- [Workflow Samples](https://github.com/microsoft/agent-framework/tree/main/python/samples/getting_started/workflows): Advanced multi-agent patterns

## Agent Framework Documentation

- [Agent Framework Repository](https://github.com/microsoft/agent-framework)
- [Python Package Documentation](https://github.com/microsoft/agent-framework/tree/main/python)
- [.NET Package Documentation](https://github.com/microsoft/agent-framework/tree/main/dotnet)
- [Design Documents](https://github.com/microsoft/agent-framework/tree/main/docs/design)
- Learn docs are coming soon.
