# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
import re

import httpx
from a2a.client import A2ACardResolver
from agent_framework.a2a import A2AAgent
from agent_framework.foundry import FoundryChatClient
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

"""
A2A Agent Skills as Function Tools

This sample demonstrates how to represent an A2A agent's skills as individual
function tools and register them with a host agent. Each skill advertised in the
remote agent's AgentCard becomes a separate tool that the host agent can invoke.

Key concepts demonstrated:
- Resolving an AgentCard from a remote A2A endpoint
- Converting each skill into a FunctionTool via as_tool()
- Registering those tools with a host agent
- Having the host agent autonomously select and invoke A2A skills

Prerequisites:
- Set A2A_AGENT_HOST to the URL of a running A2A server
- Set FOUNDRY_PROJECT_ENDPOINT to your Azure AI Foundry project endpoint
- Set FOUNDRY_MODEL to the model deployment name (e.g. gpt-4o)

To run this sample:
    cd python/samples/04-hosting/a2a
    uv run python a2a_agent_as_function_tools.py
"""


async def main() -> None:
    """Discover A2A agent skills and register them as tools on a host agent."""
    # 1. Read environment configuration.
    a2a_agent_host = os.getenv("A2A_AGENT_HOST")
    if not a2a_agent_host:
        raise ValueError("A2A_AGENT_HOST environment variable is not set")

    project_endpoint = os.getenv("FOUNDRY_PROJECT_ENDPOINT")
    model = os.getenv("FOUNDRY_MODEL")
    if not project_endpoint or not model:
        raise ValueError(
            "FOUNDRY_PROJECT_ENDPOINT and FOUNDRY_MODEL must be set"
        )

    print(f"Connecting to A2A agent at: {a2a_agent_host}")

    # 2. Resolve the remote agent card to discover its skills.
    async with httpx.AsyncClient(timeout=60.0) as http_client:
        resolver = A2ACardResolver(httpx_client=http_client, base_url=a2a_agent_host)
        agent_card = await resolver.get_agent_card()

    print(f"Found agent: {agent_card.name} ({len(agent_card.skills)} skill(s))")
    for skill in agent_card.skills:
        print(f"  - {skill.name}: {skill.description}")

    # 3. Create the A2AAgent that wraps the remote endpoint.
    async with A2AAgent(
        name=agent_card.name,
        description=agent_card.description,
        agent_card=agent_card,
        url=a2a_agent_host,
    ) as a2a_agent:
        # 4. Convert each A2A skill into a FunctionTool.
        #    Skill names may contain spaces or special characters, so we
        #    sanitize them into valid tool identifiers before passing to as_tool().
        skill_tools = [
            a2a_agent.as_tool(
                name=re.sub(r"[^0-9A-Za-z]+", "_", skill.name),
                description=skill.description or "",
            )
            for skill in agent_card.skills
        ]

        # 5. Create the host agent with the skill tools.
        credential = AzureCliCredential()
        client = FoundryChatClient(
            project_endpoint=project_endpoint,
            model=model,
            credential=credential,
        )
        host_agent = client.as_agent(
            name="assistant",
            instructions="You are a helpful assistant. Use your tools to answer questions.",
            tools=skill_tools,
        )

        # 6. Run the host agent — it will select and invoke the appropriate A2A skill tools.
        query = "Show me all invoices for Contoso"
        print(f"\nUser: {query}\n")
        response = await host_agent.run(query)
        print(f"Agent: {response}")


if __name__ == "__main__":
    asyncio.run(main())


"""
Sample output:

Connecting to A2A agent at: http://localhost:5000/
Found agent: InvoiceAgent (1 skill(s))
  - InvoiceQuery: Handles requests relating to invoices.

User: Show me all invoices for Contoso

Agent: Here are the invoices for Contoso:

1. **Invoice ID:** INV789
   - **Date:** 2026-02-15
   - **Products:**
     - T-Shirts: 150 units @ $10.00 = $1,500.00
     - Hats: 200 units @ $15.00 = $3,000.00
     - Glasses: 300 units @ $5.00 = $1,500.00
   - **Total:** $6,000.00

2. **Invoice ID:** INV333
   - **Date:** 2026-03-14
   - **Products:**
     - T-Shirts: 400 units @ $11.00 = $4,400.00
     - Hats: 600 units @ $15.00 = $9,000.00
     - Glasses: 700 units @ $5.00 = $3,500.00
   - **Total:** $16,900.00

3. **Invoice ID:** INV666
   - **Date:** 2026-02-06
   - **Products:**
     - T-Shirts: 2,500 units @ $8.00 = $20,000.00
     - Hats: 1,200 units @ $10.00 = $12,000.00
     - Glasses: 1,000 units @ $6.00 = $6,000.00
   - **Total:** $38,000.00

4. **Invoice ID:** INV999
   - **Date:** 2026-03-19
   - **Products:**
     - T-Shirts: 1,400 units @ $10.50 = $14,700.00
     - Hats: 1,100 units @ $9.00 = $9,900.00
     - Glasses: 950 units @ $12.00 = $11,400.00
   - **Total:** $36,000.00

If you need more details or a specific invoice, please let me know!
"""
