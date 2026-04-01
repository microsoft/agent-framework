# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
import sys

# Uncomment this filter to suppress the experimental Skills warning before
# using the sample's Skills APIs.
# import warnings
# warnings.filterwarnings("ignore", message=r"\[SKILLS\].*", category=FutureWarning)
from pathlib import Path

from agent_framework import Agent, SkillsProvider
from agent_framework.foundry import FoundryChatClient
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

# Add the skills folder root to sys.path so the shared subprocess_script_runner can be imported
_SKILLS_ROOT = str(Path(__file__).resolve().parent.parent)
if _SKILLS_ROOT not in sys.path:
    sys.path.insert(0, _SKILLS_ROOT)

from subprocess_script_runner import subprocess_script_runner  # noqa: E402

"""
File-Based Agent Skills

This sample demonstrates how to use file-based Agent Skills with a SkillsProvider.
Agent Skills are modular packages of instructions and resources that extend an agent's
capabilities. They follow progressive disclosure:

1. Advertise — skill names and descriptions are injected into the system prompt
2. Load — full instructions are loaded on-demand via the load_skill tool
3. Read resources — supplementary files are read via the read_skill_resource tool
4. Run scripts — skill scripts are run via the run_skill_script tool

This sample includes the unit-converter skill which demonstrates all three
file-based capabilities: instructions (SKILL.md), resources (CONVERSION_TABLES.md),
and scripts (convert.py).
"""

# Load environment variables from .env file
load_dotenv()


async def main() -> None:
    """Run the file-based skills demo."""
    endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
    deployment = os.environ.get("FOUNDRY_MODEL", "gpt-4o-mini")

    # Create the chat client
    client = FoundryChatClient(
        project_endpoint=endpoint,
        model=deployment,
        credential=AzureCliCredential(),
    )

    # Create the skills provider
    # Discovers skills from the 'skills' directory and configures the
    # subprocess_script_runner to run file-based scripts.
    skills_dir = Path(__file__).parent / "skills"
    skills_provider = SkillsProvider(
        skill_paths=str(skills_dir),
        script_runner=subprocess_script_runner,
    )

    # Create the agent with skills
    async with Agent(
        client=client,
        instructions="You are a helpful assistant.",
        context_providers=[skills_provider],
    ) as agent:
        # The agent will: load the unit-converter skill, read the conversion
        # tables resource, then execute the convert.py script.
        print("Converting units")
        print("-" * 60)
        response = await agent.run(
            "How many kilometers is a marathon (26.2 miles)? And how many pounds is 75 kilograms?"
        )
        print(f"Agent: {response}\n")


if __name__ == "__main__":
    asyncio.run(main())

"""
Sample output:

Converting units
------------------------------------------------------------
Agent: Here are your conversions:

1. **26.2 miles → 42.16 km** (a marathon distance)
2. **75 kg → 165.35 lbs**

I used the conversion factors from the reference table:
miles × 1.60934 and kilograms × 2.20462.
"""
