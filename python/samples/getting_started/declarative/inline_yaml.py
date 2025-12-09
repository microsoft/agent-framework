# Copyright (c) Microsoft. All rights reserved.
import asyncio

from agent_framework.declarative import AgentFactory
from azure.identity.aio import AzureCliCredential

"""
This sample shows how to create an agent using an inline YAML string rather than a file.

It uses a Azure AI Client so it needs the credential to be passed into the AgentFactory.

Prerequisites:
- `pip install agent-framework-azure-ai agent-framework-declarative --pre`
- Set the following environment variables in a .env file or your environment:
    - AZURE_AI_PROJECT_ENDPOINT
    - AZURE_OPENAI_MODEL
"""


async def main():
    """Create an agent from a declarative YAML specification and run it."""
    yaml_definition = """kind: Prompt
name: DiagnosticAgent
displayName: Diagnostic Assistant
instructions: Specialized diagnostic and issue detection agent for systems with critical error protocol and automatic handoff capabilities
description: A agent that performs diagnostics on systems and can escalate issues when critical errors are detected.

model:
  id: =Env.AZURE_OPENAI_MODEL
  connection:
    kind: remote
    endpoint: =Env.AZURE_AI_PROJECT_ENDPOINT
"""
    # create the agent from the yaml
    async with (
        AzureCliCredential() as credential,
        AgentFactory(client_kwargs={"credential": credential}).create_agent_from_yaml(yaml_definition) as agent,
    ):
        response = await agent.run("What can you do for me?")
        print("Agent response:", response.text)


if __name__ == "__main__":
    asyncio.run(main())
