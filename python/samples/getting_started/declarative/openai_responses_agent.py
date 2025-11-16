# Copyright (c) Microsoft. All rights reserved.
import asyncio
from pathlib import Path

from agent_framework.declarative import AgentFactory


async def main():
    """Create an agent from a declarative yaml specification and run it."""
    # get the path
    current_path = Path(__file__).parent
    yaml_path = current_path.parent.parent.parent.parent / "agent-samples" / "openai" / "OpenAIResponses.yaml"

    # load the yaml from the path
    with yaml_path.open("r") as f:
        yaml_str = f.read()

    # create the agent from the yaml
    agent = AgentFactory().create_agent_from_yaml(yaml_str)
    # use the agent
    response = await agent.run("Why is the sky blue, answer in Dutch?")
    print("Agent response:", response.value)


if __name__ == "__main__":
    asyncio.run(main())
