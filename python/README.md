# Azure AI Multi-Agent Framework

This Python package provides a framework for building and running multi-agent systems using various AI services including Azure OpenAI and OpenAI.

## Installation

```bash
pip install azure-ai-multi-agent
```

## Features

- Abstract agent framework for building AI agent systems
- Support for chat completion-based agents
- Memory-backed agent threads
- Simple agent implementation for demonstration purposes
- Support for both synchronous and streaming agent responses
- Support for OpenAI and Azure OpenAI chat completions

## Quick Start

```python
import asyncio
import os
from azure.ai.agent.chat_completion_agent import ChatClientAgent, OpenAIChatClient, ChatClientAgentOptions
from azure.ai.agent.common import ChatMessage, ChatRole

async def main():
    # Create an OpenAI chat client
    api_key = os.environ["OPENAI_API_KEY"]
    chat_client = OpenAIChatClient(api_key, model="gpt-3.5-turbo")
    
    # Create a chat client agent
    agent_options = ChatClientAgentOptions(
        name="Assistant",
        instructions="You are a helpful assistant."
    )
    agent = ChatClientAgent(chat_client, agent_options)
    
    # Create a new thread
    thread = agent.get_new_thread()
    
    # Create a message
    message = ChatMessage(ChatRole.USER, "Hello, what can you do for me?")
    
    # Run the agent
    response = await agent.run_async_with_messages([message], thread)
    
    # Print the response
    print(f"Agent: {response.messages[0].content}")

if __name__ == "__main__":
    asyncio.run(main())
```

## Alternative: Simple Agent

For a simpler demonstration without external API calls:

```python
import asyncio
from azure.ai.agent.simple_agent import SimpleAgent
from azure.ai.agent.common import ChatMessage, ChatRole

async def main():
    # Create a simple agent
    agent = SimpleAgent(
        response_text="I'm a simple agent that responds with this message.",
        name="SimpleAgent"
    )
    
    # Create a thread
    thread = agent.get_new_thread()
    
    # Create a message
    message = ChatMessage(ChatRole.USER, "Hello!")
    
    # Run the agent
    response = await agent.run_async_with_messages([message], thread)
    
    # Print the response
    print(f"Agent: {response.messages[0].content}")

if __name__ == "__main__":
    asyncio.run(main())
```

## Sample Code

The package includes several sample applications:

- `samples/chat_completion_agent_sample.py` - Shows how to use the ChatClientAgent with OpenAI
- `samples/simple_agent_sample.py` - Shows how to use the SimpleAgent with canned responses
- `samples/multi_agent_sample.py` - Shows how to orchestrate multiple agents with a shared memory thread

## Checks

Run all checks using pre-commit:

```bash
uv run pre-commit run -a
```
