# Copyright (c) Microsoft. All rights reserved.
import asyncio
from pathlib import Path

from agent_framework.declarative import AgentFactory
from azure.identity import AzureCliCredential


async def main():
    """Create an agent from a declarative yaml specification and run it."""
    # get the path
    current_path = Path(__file__).parent
    yaml_path = current_path.parent.parent.parent.parent / "agent-samples" / "azure" / "AzureOpenAIResponses.yaml"

    # load the yaml from the path
    with yaml_path.open("r") as f:
        yaml_str = f.read()

    # create the agent from the yaml
    agent = AgentFactory(client_kwargs={"credential": AzureCliCredential()}).create_agent_from_yaml(yaml_str)
    # use the agent
    response = await agent.run("Why is the sky blue, answer in Dutch?")
    # Use try_parse_value() for safe parsing - returns None if no response_format or parsing fails
    if parsed := response.try_parse_value():
        print("Agent response:", parsed.model_dump_json(indent=2))
    else:
        print("Agent response:", response.text)


if __name__ == "__main__":
    asyncio.run(main())
