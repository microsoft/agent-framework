# Copyright (c) Microsoft. All rights reserved.
import asyncio

from agent_framework.declarative import AgentFactory
from azure.identity.aio import AzureCliCredential


async def main():
    """Create an agent from a declarative yaml specification and run it."""
    yaml_definition = """kind: Prompt
name: DiagnosticAgent
displayName: Diagnostic Assistant
instructions: Specialized diagnostic and issue detection agent for systems with critical error protocol and automatic handoff capabilities

model:
  id: =Env.AZURE_OPENAI_MODEL
  connection:
    kind: remote
    endpoint: =Env.AZURE_AI_PROJECT_ENDPOINT
"""
    # create the agent from the yaml
    async with (
        AzureCliCredential() as credential,
        AgentFactory(client_kwargs={"async_credential": credential}).create_agent_from_yaml(yaml_definition) as agent,
    ):
        response = await agent.run("What can you do for me?")
        print("Agent response:", response.text)


if __name__ == "__main__":
    asyncio.run(main())
