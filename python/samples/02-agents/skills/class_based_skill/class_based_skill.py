# Copyright (c) Microsoft. All rights reserved.

import asyncio
import json
import os

# Uncomment this filter to suppress the experimental Skills warning before
# using the sample's Skills APIs.
# import warnings  # isort: skip
# warnings.filterwarnings("ignore", message=r"\[SKILLS\].*", category=FutureWarning)
from textwrap import dedent

from agent_framework import Agent, ClassSkill, SkillsProvider
from agent_framework.foundry import FoundryChatClient
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

"""
Class-Based Agent Skills — Define skills as Python classes

This sample demonstrates how to define Agent Skills as reusable Python classes
by subclassing ``ClassSkill``. Class-based skills bundle all components (name,
description, instructions, resources, scripts) into a single class, making
them easy to package and distribute via shared libraries or PyPI.

Key concepts shown:
- Subclassing ``ClassSkill`` to create a self-contained skill
- Using ``@property`` + ``@ClassSkill.resource`` (bare) — name defaults to method name
- Using ``@ClassSkill.script(name=..., description=...)`` — explicit name and description
- Lazy-loading and caching of resources and scripts
"""

# Load environment variables from .env file
load_dotenv()


# ---------------------------------------------------------------------------
# Class-Based Skill: UnitConverterSkill
# ---------------------------------------------------------------------------


class UnitConverterSkill(ClassSkill):
    """A unit-converter skill defined as a Python class.

    Converts between common units (miles↔km, pounds↔kg) using a
    conversion factor. Resources and scripts are discovered automatically
    via decorators.
    """

    def __init__(self) -> None:
        super().__init__(
            name="unit-converter",
            description=(
                "Convert between common units using a multiplication factor. "
                "Use when asked to convert miles, kilometers, pounds, or kilograms."
            ),
        )

    @property
    def instructions(self) -> str:
        return dedent("""\
            Use this skill when the user asks to convert between units.

            1. Review the conversion-table resource to find the factor for the requested conversion.
            2. Use the convert script, passing the value and factor from the table.
            3. Present the result clearly with both units.
        """)

    # 1. Property with bare decorator — name defaults to the method name
    #    ("conversion_table" → "conversion-table"), no description.
    #    Place @property first, then @ClassSkill.resource.
    @property
    @ClassSkill.resource
    def conversion_table(self) -> str:
        """Lookup table of multiplication factors for common unit conversions."""
        return dedent("""\
            # Conversion Tables

            Formula: **result = value × factor**

            | From        | To          | Factor   |
            |-------------|-------------|----------|
            | miles       | kilometers  | 1.60934  |
            | kilometers  | miles       | 0.621371 |
            | pounds      | kilograms   | 0.453592 |
            | kilograms   | pounds      | 2.20462  |
        """)

    # 2. Explicit name — overrides the method name
    # 3. Explicit description — provides a description for the script
    @ClassSkill.script(name="convert", description="Multiplies a value by a conversion factor.")
    def convert_units(self, value: float, factor: float) -> str:
        """Convert a value using a multiplication factor: result = value × factor.

        Args:
            value: The numeric value to convert.
            factor: Conversion factor from the conversion table.

        Returns:
            JSON string with the inputs and converted result.
        """
        result = round(value * factor, 4)
        return json.dumps({"value": value, "factor": factor, "result": result})


async def main() -> None:
    """Run the class-based skills demo."""
    endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
    deployment = os.environ.get("FOUNDRY_MODEL", "gpt-4o-mini")

    client = FoundryChatClient(
        project_endpoint=endpoint,
        model=deployment,
        credential=AzureCliCredential(),
    )

    # Instantiate the class-based skill and pass it to the provider
    unit_converter = UnitConverterSkill()

    async with Agent(
        client=client,
        instructions="You are a helpful assistant that can convert units.",
        context_providers=[SkillsProvider(unit_converter)],
    ) as agent:
        print("Converting units with class-based skills")
        print("-" * 60)
        response = await agent.run(
            "How many kilometers is a marathon (26.2 miles)? And how many pounds is 75 kilograms?"
        )
        print(f"Agent: {response}\n")


if __name__ == "__main__":
    asyncio.run(main())

"""
Sample output:

Converting units with class-based skills
------------------------------------------------------------
Agent: Here are your conversions:

1. **26.2 miles → 42.16 km** (a marathon distance)
2. **75 kg → 165.35 lbs**
"""
