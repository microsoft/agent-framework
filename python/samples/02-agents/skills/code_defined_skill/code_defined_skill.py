# Copyright (c) Microsoft. All rights reserved.

import asyncio
import json
import os
from textwrap import dedent
from typing import Any

from agent_framework import (
    Agent,
    InlineSkill,
    InlineSkillResource,
    SkillFrontmatter,
    SkillsProvider,
    ToolApprovalMiddleware,
)
from agent_framework.foundry import FoundryChatClient
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

Resources and scripts that accept ``**kwargs`` also receive host-supplied
runtime context from ``agent.run(..., function_invocation_kwargs={...})``.
This sample passes ``precision`` that way. Scripts additionally receive the
model-supplied nested ``args`` dictionary: declared parameters bind by name,
and extra entries can enter the callback's ``**kwargs``. Unlike resource
callbacks, script callbacks therefore do not have a runtime-only ``**kwargs``
mapping.

Code-defined skills can be combined with file-based skills in a single
SkillsProvider — see the mixed_skills sample.
"""

# Load environment variables from .env file
load_dotenv()

# ---------------------------------------------------------------------------
# 1. Static Resources — inline content passed at construction time
# ---------------------------------------------------------------------------
unit_converter_skill = InlineSkill(
    frontmatter=SkillFrontmatter(
        name="unit-converter", description="Convert between common units using a conversion factor"
    ),
    instructions=dedent("""\
        Use this skill when the user asks to convert between units.

        1. Review the conversion-tables resource to find the factor for the
           requested conversion.
        2. Check the conversion-policy resource for rounding and formatting rules.
        3. Use the convert script, passing the value and factor from the table.
    """),
    resources=[
        InlineSkillResource(
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
@unit_converter_skill.resource(
    name="conversion-policy", description="Current conversion formatting and rounding policy"
)
def conversion_policy(**kwargs: Any) -> Any:
    """Return the current conversion policy.

    Dynamic resources are evaluated at runtime, so they can include
    live data such as dates, configuration values, or database lookups.

    When the resource function accepts ``**kwargs``, runtime keyword
    arguments passed to ``agent.run()`` are forwarded automatically.

    These runtime values are *host-controlled request context*: they come only
    from the application calling ``agent.run()``, never from the model. That
    distinction matters for values that select authority — a tenant ID, a user
    ID, or an auth token — so this resource treats a missing ``precision`` as a
    bug rather than silently falling back to a default and masking it.

    Args:
        **kwargs: Runtime keyword arguments from ``agent.run()``.
            For example, ``agent.run(..., function_invocation_kwargs={"precision": 2})``
            makes ``kwargs["precision"]`` available here.
    """
    if "precision" not in kwargs:
        raise RuntimeError(
            "Expected host-supplied 'precision' in runtime kwargs. Runtime context must reach "
            "resources via agent.run(function_invocation_kwargs=...)."
        )
    precision = kwargs["precision"]
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

    The model supplies ``value`` and ``factor`` through the script's nested
    ``args`` dictionary, while ``main()`` supplies ``precision`` through
    ``function_invocation_kwargs``. Both dictionaries are expanded into this
    callback, so additional nested ``args`` entries can also enter ``**kwargs``.
    Checking for ``precision`` below verifies its presence, not its source.

    Args:
        value: The numeric value to convert.
        factor: Conversion factor from the conversion table.
        **kwargs: Runtime keyword arguments from ``agent.run()`` and any extra
            entries in the script's nested ``args`` dictionary. The ``precision``
            kwarg controls how many decimal places the result is rounded to.

    Returns:
        JSON string with the inputs and converted result.
    """
    if "precision" not in kwargs:
        raise RuntimeError(
            "This sample requires 'precision'. main() supplies it through agent.run(function_invocation_kwargs=...)."
        )
    precision = kwargs["precision"]
    result = round(value * factor, precision)
    return json.dumps({"value": value, "factor": factor, "result": result})


async def main() -> None:
    """Run the code-defined skills demo."""
    endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
    deployment = os.environ.get("FOUNDRY_MODEL", "gpt-4o-mini")

    client = FoundryChatClient(
        project_endpoint=endpoint,
        model=deployment,
        credential=AzureCliCredential(),
    )

    # Create the skills provider with the code-defined skill and pass it to the agent
    # All skill tools require approval by default; auto-approve them so the
    # sample runs unattended. See the script_approval / skills_auto_approval
    # samples for interactive and selective approval handling.
    async with Agent(
        client=client,
        instructions="You are a helpful assistant that can convert units.",
        context_providers=[SkillsProvider(unit_converter_skill)],
        middleware=[ToolApprovalMiddleware(auto_approval_rules=[SkillsProvider.all_tools_auto_approval_rule])],
    ) as agent:
        print("Converting units")
        print("-" * 60)
        session = agent.create_session()
        response = await agent.run(
            "How many kilometers is a marathon (26.2 miles)? And how many pounds is 75 kilograms?",
            function_invocation_kwargs={"precision": 2},
            session=session,
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
