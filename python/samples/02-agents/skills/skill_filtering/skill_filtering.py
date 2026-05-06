# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
import sys
from pathlib import Path

from agent_framework import (
    Agent,
    DeduplicatingSkillsSource,
    FileSkillsSource,
    FilteringSkillsSource,
    SkillsProvider,
)
from agent_framework.foundry import FoundryChatClient
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

# Add the skills folder root to sys.path so the shared subprocess_script_runner can be imported
_SKILLS_ROOT = str(Path(__file__).resolve().parent.parent)
if _SKILLS_ROOT not in sys.path:
    sys.path.insert(0, _SKILLS_ROOT)

from subprocess_script_runner import subprocess_script_runner  # noqa: E402

"""
Skill Filtering — Using FilteringSkillsSource with file-based skills

This sample demonstrates how to use **FilteringSkillsSource** to control
which skills an agent sees.  Although this example uses file-based skills,
``FilteringSkillsSource`` works equally well with in-memory skills,
custom sources, or any combination of them.

A single ``skills/`` directory contains two file-based skills discovered via
``FileSkillsSource``:

- **volume-converter** — converts between gallons and liters
- **length-converter** — converts between miles ↔ km, feet ↔ meters

A ``FilteringSkillsSource`` wraps the file source and excludes the
``length-converter`` skill, so the agent only sees the volume-converter skill.

Note: if you only need a single skill, you could point ``FileSkillsSource``
directly at that skill's directory and skip filtering entirely.  This sample
intentionally points at the parent directory to demonstrate filtering.

Key concepts shown:

1. **FileSkillsSource** — discovers skills from ``SKILL.md`` files on disk.
2. **FilteringSkillsSource** — applies a predicate to include or exclude
   specific skills by name (or any custom logic).
3. **DeduplicatingSkillsSource** — ensures no duplicate skill names survive.
"""

# Load environment variables from .env file
load_dotenv()


async def main() -> None:
    """Run the skill filtering demo."""
    endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
    deployment = os.environ.get("FOUNDRY_MODEL", "gpt-4o-mini")

    # 1. Create the chat client
    client = FoundryChatClient(
        project_endpoint=endpoint,
        model=deployment,
        credential=AzureCliCredential(),
    )

    # 2. Compose the source pipeline:
    #    file discovery → filter out length-converter → deduplicate
    skills_dir = Path(__file__).parent / "skills"
    source = DeduplicatingSkillsSource(
        FilteringSkillsSource(
            FileSkillsSource(str(skills_dir), script_runner=subprocess_script_runner),
            # Only keep the volume-converter skill
            predicate=lambda s: s.name != "length-converter",
        )
    )

    skills_provider = SkillsProvider(source)

    # 3. Run the agent — it can only see the volume-converter skill
    async with Agent(
        client=client,
        instructions="You are a helpful assistant that can convert units.",
        context_providers=[skills_provider],
    ) as agent:
        print("Skill filtering demo")
        print("-" * 60)
        response = await agent.run("How many liters is a 5-gallon bucket?")
        print(f"Agent: {response}\n")


if __name__ == "__main__":
    asyncio.run(main())

"""
Sample output:

Skill filtering demo
------------------------------------------------------------
Agent: A 5-gallon bucket is equal to **18.9271 liters**.

I used the conversion factor: 5 × 3.78541 = 18.9271
"""
