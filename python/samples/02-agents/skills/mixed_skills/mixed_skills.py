# Copyright (c) Microsoft. All rights reserved.

import asyncio
import json
import os
import sys
from pathlib import Path
from textwrap import dedent
from typing import Any

from agent_framework import (
    Agent,
    Skill,
    SkillsProvider,
)
from agent_framework.azure import AzureOpenAIResponsesClient
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

# Add the skills folder root to sys.path so the shared subprocess_script_runner can be imported
_SKILLS_ROOT = str(Path(__file__).resolve().parent.parent)
if _SKILLS_ROOT not in sys.path:
    sys.path.insert(0, _SKILLS_ROOT)

from subprocess_script_runner import subprocess_script_runner  # noqa: E402

"""
Mixed Skills — Code skills and file skills in a single agent

This sample demonstrates how to combine **code-defined skills** (with
``@skill.script`` and ``@skill.resource`` decorators) and **file-based skills**
(discovered from ``SKILL.md`` files on disk) in a single agent using
``SkillsProvider`` and a ``SkillScriptRunner`` callable.

Key concepts shown:
- Code skills with ``@skill.script``: executable Python functions the agent
  can invoke directly in-process.
- Code skills with ``@skill.resource``: dynamic content the agent can read
  on demand.
- File skills from disk: ``SKILL.md`` files with reference documents and
  executable script files.
- ``script_runner``: routes **file-based** script execution
  through a callback, enabling custom handling (e.g. subprocess calls).
  Code-defined scripts (``@skill.script``) run in-process automatically.

The sample registers two skills:
1. **volume-converter** (code skill) — converts between gallons and liters using
   ``@skill.script`` for conversion and ``@skill.resource`` for the factor table.
2. **unit-converter** (file skill) — converts between common units (miles↔km,
   pounds↔kg) via a subprocess-executed Python script discovered from
   ``skills/unit-converter/SKILL.md``.
"""

# Load environment variables from .env file
load_dotenv()

# ---------------------------------------------------------------------------
# 1. Define a code skill with @skill.script and @skill.resource decorators
# ---------------------------------------------------------------------------

volume_converter_skill = Skill(
    name="volume-converter",
    description="Convert between gallons and liters using a conversion factor",
    content=dedent("""\
        Use this skill when the user asks to convert between gallons and liters.

        1. Review the conversion-table resource to find the correct factor.
        2. Use the convert script, passing the value and factor.
    """),
)


@volume_converter_skill.resource(name="conversion-table", description="Volume conversion factors")
def volume_table() -> Any:
    """Return the volume conversion factor table."""
    return dedent("""\
        # Volume Conversion Table

        Formula: **result = value × factor**

        | From    | To     | Factor  |
        |---------|--------|---------|
        | gallons | liters | 3.78541 |
        | liters  | gallons| 0.264172|
    """)


@volume_converter_skill.script(name="convert", description="Convert a value: result = value × factor")
def convert_volume(value: float, factor: float) -> str:
    """Convert a value using a multiplication factor.

    Args:
        value: The numeric value to convert.
        factor: Conversion factor from the table.

    Returns:
        JSON string with the conversion result.
    """
    result = round(value * factor, 4)
    return json.dumps({"value": value, "factor": factor, "result": result})


# ---------------------------------------------------------------------------
# 2. Wire everything together and run the agent
# ---------------------------------------------------------------------------


async def main() -> None:
    """Run the combined skills demo."""
    endpoint = os.environ["AZURE_AI_PROJECT_ENDPOINT"]
    deployment = os.environ.get("AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME", "gpt-4o-mini")

    # Create the chat client
    client = AzureOpenAIResponsesClient(
        project_endpoint=endpoint,
        deployment_name=deployment,
        credential=AzureCliCredential(),
    )

    # Create the SkillsProvider with both code and file skills.
    # The script_runner handles file-based scripts; code-defined scripts
    # (@skill.script) run in-process automatically.
    skills_dir = Path(__file__).parent / "skills"
    skills_provider = SkillsProvider(
        skill_paths=str(skills_dir),
        skills=[volume_converter_skill],
        script_runner=subprocess_script_runner,
    )

    # Run the agent
    async with Agent(
        client=client,
        instructions="You are a helpful assistant that can convert units.",
        context_providers=[skills_provider],
    ) as agent:
        # Ask the agent to use both skills
        print("Converting units")
        print("-" * 60)
        response = await agent.run(
            "How many kilometers is a marathon (26.2 miles)? And how many liters is a 5-gallon bucket?"
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
2. **5 gallons → 18.93 liters**

I used the conversion factors from each skill's reference table.
"""
