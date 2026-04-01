# Copyright (c) Microsoft. All rights reserved.

from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from azure.ai.agentserver.agentframework import from_agent_framework  # pyright: ignore[reportUnknownVariableType]
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


def main():
    client = FoundryChatClient(credential=AzureCliCredential())

    # Create MCP tool configuration as dict
    mcp_tool = client.get_mcp_tool(
        name="Microsoft_Learn_MCP",
        url="https://learn.microsoft.com/api/mcp",
    )

    # Create an Agent using the Azure OpenAI Chat Client with a MCP Tool that connects to Microsoft Learn MCP
    agent = Agent(
        client=client,
        name="DocsAgent",
        instructions="You are a helpful assistant that can help with microsoft documentation questions.",
        tools=[mcp_tool],
    )
    # Run the agent as a hosted agent
    from_agent_framework(agent).run()


if __name__ == "__main__":
    main()
