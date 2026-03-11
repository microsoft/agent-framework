# Copyright (c) Microsoft. All rights reserved.

import asyncio
import json
import os
from textwrap import dedent
from typing import Any

from agent_framework import Agent, Skill, SkillResource, SkillsProvider
from agent_framework.azure import AzureOpenAIResponsesClient
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

"""
Code-Defined Agent Skills — Define skills in Python code

This sample demonstrates how to create Agent Skills in code,
without needing SKILL.md files on disk. Three approaches are shown
using a unit-converter skill:

1. Static Resources
   Pass inline content directly via the ``resources`` parameter when
   constructing the Skill.

2. Dynamic Resources
   Attach a callable resource via the @skill.resource decorator. The
   function is invoked on demand, so it can return data computed at
   runtime.

3. Dynamic Scripts
   Attach a callable script via the @skill.script decorator. Scripts are
   executable functions the agent can invoke directly in-process.

Code-defined skills can be combined with file-based skills in a single
SkillsProvider — see the mixed_skills sample.
"""

# Load environment variables from .env file
load_dotenv()

# ---------------------------------------------------------------------------
# 1. Static Resources — inline content passed at construction time
# ---------------------------------------------------------------------------
unit_converter_skill = Skill(
    name="unit-converter",
    description="Convert between common units using a conversion factor",
    content=dedent("""\
        Use this skill when the user asks to convert between units.

        1. Review the conversion-tables resource to find the factor for the
           requested conversion.
        2. Check the conversion-policy resource for rounding and formatting rules.
        3. Use the convert script, passing the value and factor from the table.
    """),
    resources=[
        SkillResource(
            name="conversion-tables",
            content=dedent("""\
                # Conversion Tables

                Formula: **result = value × factor**

                | From        | To          | Factor   |
                |-------------|-------------|----------|
                | miles       | kilometers  | 1.60934  |
                | kilometers  | miles       | 0.621371 |
                | pounds      | kilograms   | 0.453592 |
                | kilograms   | pounds      | 2.20462  |
            """),
        ),
    ],
)


# ---------------------------------------------------------------------------
# 2. Dynamic Resources — callable function via @skill.resource
# ---------------------------------------------------------------------------
@unit_converter_skill.resource(name="conversion-policy", description="Current conversion formatting and rounding policy")
def conversion_policy(**kwargs: Any) -> Any:
    """Return the current conversion policy.

    Dynamic resources are evaluated at runtime, so they can include
    live data such as dates, configuration values, or database lookups.

    When the resource function accepts ``**kwargs``, runtime keyword
    arguments passed to ``agent.run()`` are forwarded automatically.

    Args:
        **kwargs: Runtime keyword arguments from ``agent.run()``.
            For example, ``agent.run(..., precision=2)``
            makes ``kwargs["precision"]`` available here.
    """
    precision = kwargs.get("precision", 4)
    return dedent(f"""\
        # Conversion Policy

        **Decimal places:** {precision}
        **Format:** Always show both the original and converted values with units
    """)


# ---------------------------------------------------------------------------
# 3. Dynamic Scripts — in-process callable function
# ---------------------------------------------------------------------------
@unit_converter_skill.script(name="convert", description="Convert a value: result = value × factor")
def convert_units(value: float, factor: float, **kwargs: Any) -> str:
    """Convert a value using a multiplication factor: result = value × factor.

    The caller looks up the correct factor from the conversion-tables
    resource and passes it here.

    Args:
        value: The numeric value to convert.
        factor: Conversion factor from the conversion table.
        **kwargs: Runtime keyword arguments from ``agent.run()``.
            The ``precision`` kwarg controls how many decimal places
            the result is rounded to (default 4).

    Returns:
        JSON string with the inputs and converted result.
    """
    precision = kwargs.get("precision", 4)
    result = round(value * factor, precision)
    return json.dumps({"value": value, "factor": factor, "result": result})


async def main() -> None:
    """Run the code-defined skills demo."""
    endpoint = os.environ["AZURE_AI_PROJECT_ENDPOINT"]
    deployment = os.environ.get("AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME", "gpt-4o-mini")

    client = AzureOpenAIResponsesClient(
        project_endpoint=endpoint,
        deployment_name=deployment,
        credential=AzureCliCredential(),
    )

    # Create the skills provider with the code-defined skill
    skills_provider = SkillsProvider(
        skills=[unit_converter_skill],
    )

    async with Agent(
        client=client,
        instructions="You are a helpful assistant that can convert units.",
        context_providers=[skills_provider],
    ) as agent:
        print("Converting units")
        print("-" * 60)
        response = await agent.run(
            "How many kilometers is a marathon (26.2 miles)? "
            "And how many pounds is 75 kilograms?",
            precision=2,
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
