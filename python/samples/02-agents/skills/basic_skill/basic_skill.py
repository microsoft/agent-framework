# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
from pathlib import Path

from agent_framework import Agent, FileAgentSkillsProvider
from agent_framework.azure import AzureOpenAIResponsesClient
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

"""
Agent Skills Sample

This sample demonstrates how to use file-based Agent Skills with a FileAgentSkillsProvider.
Agent Skills are modular packages of instructions and resources that extend an agent's
capabilities. They follow the progressive disclosure pattern:

1. Advertise — skill names and descriptions are injected into the system prompt
2. Load — full instructions are loaded on-demand via the load_skill tool
3. Read resources — supplementary files are read via the read_skill_resource tool

This sample includes the expense-report skill:
  - Policy-based expense filing with references and assets
"""


async def main() -> None:
    """Run the Agent Skills demo."""
    # --- Configuration ---
    endpoint = os.environ["AZURE_AI_PROJECT_ENDPOINT"]
    deployment = os.environ.get("AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME", "gpt-4o-mini")

    # --- 1. Create the chat client ---
    client = AzureOpenAIResponsesClient(
        project_endpoint=endpoint,
        deployment_name=deployment,
        credential=AzureCliCredential(),
    )

    # --- 2. Create the skills provider ---
    # Discovers skills from the 'skills' directory and makes them available to the agent
    skills_dir = Path(__file__).parent / "skills"
    skills_provider = FileAgentSkillsProvider(skill_paths=str(skills_dir))

    # --- 3. Create the agent with skills ---
    async with Agent(
        client=client,
        instructions="You are a helpful assistant.",
        context_providers=[skills_provider],
    ) as agent:
        # --- Example 1: Expense policy question (loads FAQ resource) ---
        print("Example 1: Checking expense policy FAQ")
        print("---------------------------------------")
        response1 = await agent.run(
            "Are tips reimbursable? I left a 25% tip on a taxi ride and want to know if that's covered."
        )
        print(f"Agent: {response1}\n")

        # --- Example 2: Filing an expense report (uses template asset) ---
        print("Example 2: Filing an expense report")
        print("---------------------------------------")
        session = agent.create_session()
        response2 = await agent.run(
            "I had 3 client dinners and a $1,200 flight last week. "
            "Return a draft expense report and ask about any missing details.",
            session=session,
        )
        print(f"Agent: {response2}\n")


if __name__ == "__main__":
    asyncio.run(main())

"""
Sample output:
Example 1: Checking expense policy FAQ
---------------------------------------
Agent: Tips up to 20% are reimbursable for meals, taxi/ride-share, and hotel housekeeping.
Since you left a 25% tip, the portion above 20% would require written justification...

Example 2: Filing an expense report
---------------------------------------
Agent: Here's a draft expense report based on what you've told me. I'll need a few more details...
"""
