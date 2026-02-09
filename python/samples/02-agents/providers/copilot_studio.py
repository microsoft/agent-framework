# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework.microsoft import CopilotStudioAgent

"""
Copilot Studio Provider

Demonstrates setting up CopilotStudioAgent and running a simple query.
Configuration is read from environment variables automatically.

Environment variables:
- COPILOTSTUDIOAGENT__ENVIRONMENTID: Environment ID
- COPILOTSTUDIOAGENT__SCHEMANAME: Agent schema name
- COPILOTSTUDIOAGENT__AGENTAPPID: Client ID for authentication
- COPILOTSTUDIOAGENT__TENANTID: Tenant ID for authentication

For more Copilot Studio examples:
- Explicit settings: getting_started/agents/copilotstudio/copilotstudio_with_explicit_settings.py
- Docs: https://learn.microsoft.com/agent-framework/providers/copilot-studio
"""


async def main() -> None:
    print("=== Copilot Studio Provider ===\n")

    # <create_agent>
    agent = CopilotStudioAgent()
    # </create_agent>

    # <run_query>
    query = "What is the capital of France?"
    print(f"User: {query}")
    result = await agent.run(query)
    print(f"Agent: {result}")
    # </run_query>


if __name__ == "__main__":
    asyncio.run(main())
