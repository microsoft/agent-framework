# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
import sys
from pathlib import Path

from agent_framework import Agent, CallbackSkillScriptExecutor, SkillsProvider
from agent_framework.azure import AzureOpenAIResponsesClient
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
4. Execute scripts — skill scripts are executed via the execute_skill_script tool

This sample includes the password-generator skill which demonstrates all three
file-based capabilities: instructions (SKILL.md), resources (PASSWORD_GUIDELINES.md),
and scripts (generate.py).
"""

# Load environment variables from .env file
load_dotenv()


async def main() -> None:
    """Run the file-based skills demo."""
    endpoint = os.environ["AZURE_AI_PROJECT_ENDPOINT"]
    deployment = os.environ.get("AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME", "gpt-4o-mini")

    # Create the chat client
    client = AzureOpenAIResponsesClient(
        project_endpoint=endpoint,
        deployment_name=deployment,
        credential=AzureCliCredential(),
    )

    # Create the script executor
    # Wraps the subprocess_script_runner callback so the SkillsProvider can
    # register an execute_skill_script tool for the LLM.
    executor = CallbackSkillScriptExecutor(callback=subprocess_script_runner)

    # Create the skills provider
    # Discovers skills from the 'skills' directory and makes them available to the agent
    skills_dir = Path(__file__).parent / "skills"
    skills_provider = SkillsProvider(
        skill_paths=str(skills_dir),
        script_executor=executor,
    )

    # Create the agent with skills
    async with Agent(
        client=client,
        instructions="You are a helpful assistant.",
        context_providers=[skills_provider],
    ) as agent:
        # The agent will: load the password-generator skill, read the guidelines
        # resource, then execute the generate.py script with the right length.
        print("Generating a secure password")
        print("-" * 60)
        response = await agent.run(
            "I need a secure password for a new PostgreSQL database. "
            "Please generate one following best practices."
        )
        print(f"Agent: {response}\n")


if __name__ == "__main__":
    asyncio.run(main())

"""
Sample output:

Generating a secure password
------------------------------------------------------------
Agent: Based on the password guidelines, database credentials should use at least 24
characters with upper + lower case letters, digits, and symbols. I ran the password
generator script with --length 24 and here's your result:

{"password": "aR3$vK8!mN2@pQ7&xL5#wY9b", "length": 24}

This password was generated using a cryptographically secure random generator.
Remember to store it securely and never reuse it across services.
"""
