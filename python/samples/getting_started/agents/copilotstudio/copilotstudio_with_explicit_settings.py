# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os

from agent_framework.microsoft import CopilotStudioAgent, acquire_token
from microsoft_agents.copilotstudio.client import AgentType, ConnectionSettings, CopilotClient, PowerPlatformCloud

"""
Copilot Studio Agent with Explicit Settings Example

This sample demonstrates explicit configuration of CopilotStudioAgent with manual
token management and custom ConnectionSettings for production environments.
"""

# Environment variables needed:
# COPILOTSTUDIOAGENT__ENVIRONMENTID - Environment ID where your copilot is deployed
# COPILOTSTUDIOAGENT__SCHEMANAME - Agent identifier/schema name of your copilot
# COPILOTSTUDIOAGENT__AGENTAPPID - Client ID for authentication
# COPILOTSTUDIOAGENT__TENANTID - Tenant ID for authentication


async def example_with_connection_settings() -> None:
    """Example using explicit ConnectionSettings and CopilotClient."""
    print("=== Copilot Studio Agent with Connection Settings ===")

    # Configuration from environment variables
    environment_id = os.environ["COPILOTSTUDIOAGENT__ENVIRONMENTID"]
    agent_identifier = os.environ["COPILOTSTUDIOAGENT__SCHEMANAME"]
    client_id = os.environ["COPILOTSTUDIOAGENT__AGENTAPPID"]
    tenant_id = os.environ["COPILOTSTUDIOAGENT__TENANTID"]

    # Acquire token using the acquire_token function
    token = acquire_token(
        client_id=client_id,
        tenant_id=tenant_id,
    )

    # Create connection settings
    settings = ConnectionSettings(
        environment_id=environment_id,
        agent_identifier=agent_identifier,
        cloud=PowerPlatformCloud.PROD,  # Or PowerPlatformCloud.GOV, PowerPlatformCloud.HIGH, etc.
        copilot_agent_type=AgentType.PUBLISHED,  # Or AgentType.PREBUILT
        custom_power_platform_cloud=None,  # Optional: for custom cloud endpoints
    )

    # Create CopilotClient with explicit settings
    client = CopilotClient(settings=settings, token=token)

    # Create agent with explicit client
    agent = CopilotStudioAgent(client=client)

    # Run a simple query
    query = "What is the capital of Italy?"
    print(f"User: {query}")
    result = await agent.run(query)
    print(f"Agent: {result}")


async def example_with_explicit_parameters() -> None:
    """Example using CopilotStudioAgent with all parameters explicitly provided."""
    print("\n=== Copilot Studio Agent with All Explicit Parameters ===")

    # Configuration from environment variables
    environment_id = os.environ["COPILOTSTUDIOAGENT__ENVIRONMENTID"]
    agent_identifier = os.environ["COPILOTSTUDIOAGENT__SCHEMANAME"]
    client_id = os.environ["COPILOTSTUDIOAGENT__AGENTAPPID"]
    tenant_id = os.environ["COPILOTSTUDIOAGENT__TENANTID"]

    # Create agent with all parameters explicitly
    agent = CopilotStudioAgent(
        environment_id=environment_id,
        agent_identifier=agent_identifier,
        client_id=client_id,
        tenant_id=tenant_id,
        cloud=PowerPlatformCloud.PROD,
        agent_type=AgentType.PUBLISHED,
    )

    # Run a simple query
    query = "What is the capital of Japan?"
    print(f"User: {query}")
    result = await agent.run(query)
    print(f"Agent: {result}")


async def main() -> None:
    await example_with_connection_settings()
    await example_with_explicit_parameters()


if __name__ == "__main__":
    asyncio.run(main())
