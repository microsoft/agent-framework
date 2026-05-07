# Copyright (c) Microsoft. All rights reserved.

import asyncio
import json
import os
import sys

# Uncomment this filter to suppress the experimental Skills warning before
# using the sample's Skills APIs.
# import warnings
# warnings.filterwarnings("ignore", message=r"\[SKILLS\].*", category=FutureWarning)
from pathlib import Path
from textwrap import dedent
from typing import Any

from agent_framework import (
    Agent,
    AggregatingSkillsSource,
    ClassSkill,
    DeduplicatingSkillsSource,
    FileSkillsSource,
    InlineSkill,
    InMemorySkillsSource,
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
Mixed Skills — Code, class, and file skills in a single agent

This sample demonstrates how to combine **code-defined skills** (with
``@skill.script`` and ``@skill.resource`` decorators), **class-based skills**
(subclassing ``ClassSkill``), and **file-based skills** (discovered from
``SKILL.md`` files on disk) in a single agent using ``SkillsProvider`` and
a ``SkillScriptRunner`` callable.

Key concepts shown:
- Code skills with ``@skill.script``: executable Python functions the agent
  can invoke directly in-process.
- Code skills with ``@skill.resource``: dynamic content the agent can read
  on demand.
- Class skills: self-contained skill classes extending ``ClassSkill``.
- File skills from disk: ``SKILL.md`` files with reference documents and
  executable script files.
- ``script_runner``: routes **file-based** script execution
  through a callback, enabling custom handling (e.g. subprocess calls).
  Code-defined and class-based scripts run in-process automatically.

The sample registers three skills:
1. **volume-converter** (code skill) — converts between gallons and liters using
   ``@skill.script`` for conversion and ``@skill.resource`` for the factor table.
2. **temperature-converter** (class skill) — converts between temperature scales
   (°F↔°C↔K) using a ``ClassSkill`` subclass.
3. **unit-converter** (file skill) — converts between common units (miles↔km,
   pounds↔kg) via a subprocess-executed Python script discovered from
   ``skills/unit-converter/SKILL.md``.
"""

# Load environment variables from .env file
load_dotenv()

# ---------------------------------------------------------------------------
# 1. Define a code skill with @skill.script and @skill.resource decorators
# ---------------------------------------------------------------------------

volume_converter_skill = InlineSkill(
    name="volume-converter",
    description="Convert between gallons and liters using a conversion factor",
    instructions=dedent("""\
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
# 2. Define a class-based skill for temperature conversion
# ---------------------------------------------------------------------------

class TemperatureConverterSkill(ClassSkill):
    """A temperature-converter skill defined as a Python class.

    Converts between temperature scales (Fahrenheit, Celsius, Kelvin).
    Resources and scripts are discovered automatically via decorators.
    """

    def __init__(self) -> None:
        super().__init__(
            name="temperature-converter",
            description="Convert between temperature scales (Fahrenheit, Celsius, Kelvin).",
        )

    @property
    def instructions(self) -> str:
        return dedent("""\
            Use this skill when the user asks to convert temperatures.

            1. Read the temperature-conversion-formulas resource to find the factor and offset
               for the requested conversion.
            2. Use the convert-temperature script, passing value, factor, and offset.
            3. Present the result clearly with both temperature scales.
        """)

    @ClassSkill.resource(name="temperature-conversion-formulas")
    def formulas(self) -> str:
        """Temperature conversion formulas reference table."""
        return dedent("""\
            # Temperature Conversion Formulas

            Formula: **result = value × factor + offset**

            | From        | To          | Factor   | Offset    |
            |-------------|-------------|----------|-----------|
            | Fahrenheit  | Celsius     | 0.555556 | -17.7778  |
            | Celsius     | Fahrenheit  | 1.8      | 32        |
            | Celsius     | Kelvin      | 1        | 273.15    |
            | Kelvin      | Celsius     | 1        | -273.15   |
        """)

    @ClassSkill.script(name="convert-temperature")
    def convert_temperature(self, value: float, factor: float, offset: float = 0) -> str:
        """Convert a temperature value using factor and offset from the formulas resource.

        Args:
            value: The numeric temperature value to convert.
            factor: Conversion factor from the formulas resource.
            offset: Offset to add after multiplying (default 0).

        Returns:
            JSON string with the conversion result.
        """
        result = round(value * factor + offset, 4)
        return json.dumps({"value": value, "factor": factor, "offset": offset, "result": result})


# ---------------------------------------------------------------------------
# 3. Wire everything together and run the agent
# ---------------------------------------------------------------------------

async def main() -> None:
    """Run the combined skills demo."""
    endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
    deployment = os.environ.get("FOUNDRY_MODEL", "gpt-4o-mini")

    # Create the chat client
    client = FoundryChatClient(
        project_endpoint=endpoint,
        model=deployment,
        credential=AzureCliCredential(),
    )

    # Create the SkillsProvider with code, class, and file skills.
    # The script_runner handles file-based scripts; code-defined and
    # class-based scripts run in-process automatically.
    temperature_converter = TemperatureConverterSkill()

    skills_provider = SkillsProvider(
        DeduplicatingSkillsSource(
            AggregatingSkillsSource([
                FileSkillsSource(
                    str(Path(__file__).parent / "skills"),
                    script_runner=subprocess_script_runner,
                ),
                InMemorySkillsSource([volume_converter_skill, temperature_converter]),
            ])
        )
    )

    # Run the agent
    async with Agent(
        client=client,
        instructions="You are a helpful assistant that can convert units, volumes, and temperatures.",
        context_providers=[skills_provider],
    ) as agent:
        # Ask the agent to use all three skills
        print("Converting with mixed skills (file + code + class)")
        print("-" * 60)
        response = await agent.run(
            "I need three conversions: "
            "1) How many kilometers is a marathon (26.2 miles)? "
            "2) How many liters is a 5-gallon bucket? "
            "3) What is 98.6°F in Celsius?"
        )
        print(f"Agent: {response}\n")


if __name__ == "__main__":
    asyncio.run(main())

"""
Sample output:

Converting with mixed skills (file + code + class)
------------------------------------------------------------
Agent: Here are your conversions:

1. **26.2 miles → 42.16 km** (a marathon distance)
2. **5 gallons → 18.93 liters**
3. **98.6°F → 37.0°C**
"""
