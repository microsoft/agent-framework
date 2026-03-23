# Copyright (c) Microsoft. All rights reserved.

from agent_framework.azure import AzureOpenAIResponsesClient
from azure.ai.agentserver.agentframework import from_agent_framework  # pyright: ignore[reportUnknownVariableType]
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


def main():
    client = AzureOpenAIResponsesClient(credential=DefaultAzureCredential())

    # Create MCP tool configuration using the Responses Client helper
    mcp_tool = client.get_mcp_tool(
        name="Microsoft Learn MCP",
        url="https://learn.microsoft.com/api/mcp",
    )

    # Create an Agent using the Azure OpenAI Responses Client with a MCP Tool that connects to Microsoft Learn MCP
    agent = client.as_agent(
        name="DocsAgent",
        instructions="You are a helpful assistant that can help with microsoft documentation questions.",
        tools=[mcp_tool],
    )

    # Run the agent as a hosted agent
    from_agent_framework(agent).run()


if __name__ == "__main__":
    main()
