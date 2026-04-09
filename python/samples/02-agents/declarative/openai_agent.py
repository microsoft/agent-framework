# Copyright (c) Microsoft. All rights reserved.
import asyncio
from pathlib import Path

from agent_framework.declarative import AgentFactory
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


async def main():
    """Create an agent from a declarative yaml specification and run it."""
    # get the path
    current_path = Path(__file__).parent
    yaml_path = (
        current_path.parent.parent.parent.parent
        / "declarative-agents"
        / "agent-samples"
        / "openai"
        / "OpenAIResponses.yaml"
    )
    # create the agent from the yaml
    agent = AgentFactory(safe_mode=False).create_agent_from_yaml_path(yaml_path)
    # use the agent
    response = await agent.run("Why is the sky blue, answer in Dutch?")
    # Use response.value with try/except for safe parsing
    try:
        parsed = response.value
        print("Agent response:", parsed)
    except Exception:
        print("Agent response:", response.text)


if __name__ == "__main__":
    asyncio.run(main())
