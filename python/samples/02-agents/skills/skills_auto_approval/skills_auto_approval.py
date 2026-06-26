# Copyright (c) Microsoft. All rights reserved.

import asyncio
import json
import os

# Uncomment this filter to suppress the experimental Skills warning before
# using the sample's Skills APIs.
# import warnings  # isort: skip
# warnings.filterwarnings("ignore", message=r"\[SKILLS\].*", category=FutureWarning)
from textwrap import dedent
from typing import Any

from agent_framework import (
    Agent,
    Content,
    InlineSkill,
    InlineSkillResource,
    Message,
    SkillFrontmatter,
    SkillsProvider,
    ToolApprovalMiddleware,
)
from agent_framework.foundry import FoundryChatClient
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

"""
Skills Auto-Approval — Configure auto-approval rules for skill tools

Every tool exposed by :class:`SkillsProvider` (``load_skill``,
``read_skill_resource``, and ``run_skill_script``) requires host approval by
default. Rather than prompting for every call, this sample uses
:class:`ToolApprovalMiddleware` with a static auto-approval rule so that the
read-only tools are approved automatically while script execution still
requires explicit user approval.

How it works:
1. A code-defined unit-converter skill (with a resource and a script) is
   registered via SkillsProvider.
2. The agent installs ``ToolApprovalMiddleware`` with
   ``SkillsProvider.read_only_tools_auto_approval_rule``. This auto-approves
   ``load_skill`` and ``read_skill_resource`` while still prompting for
   ``run_skill_script``.
3. The application handles the remaining ``run_skill_script`` approval requests
   via the standard ``result.user_input_requests`` loop.

Available auto-approval rules:
- ``SkillsProvider.read_only_tools_auto_approval_rule`` — approves only the
  read-only tools (``load_skill``, ``read_skill_resource``).
- ``SkillsProvider.all_tools_auto_approval_rule`` — approves every skill tool,
  including ``run_skill_script`` (no manual approval loop needed).

To use auto-approval rules, the agent must have ``ToolApprovalMiddleware`` in
its middleware stack.

Prerequisites:
- FOUNDRY_PROJECT_ENDPOINT must be your Azure AI Foundry Agent Service (V2) project endpoint.
- FOUNDRY_MODEL (defaults to "gpt-4o-mini").
"""

# Load environment variables from .env file
load_dotenv()

# A code-defined unit-converter skill with a resource (read-only) and a script.
unit_converter_skill = InlineSkill(
    frontmatter=SkillFrontmatter(
        name="unit-converter", description="Convert between common units using a conversion factor"
    ),
    instructions=dedent("""\
        Use this skill when the user asks to convert between units.

        1. Review the conversion-tables resource to find the factor for the
           requested conversion.
        2. Use the convert script, passing the value and factor from the table.
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


@unit_converter_skill.script(name="convert", description="Convert a value: result = value × factor")
def convert_units(value: float, factor: float, **kwargs: Any) -> str:
    """Convert a value using a multiplication factor: result = value × factor.

    Args:
        value: The numeric value to convert.
        factor: Conversion factor from the conversion table.
        **kwargs: Runtime keyword arguments from ``agent.run()``.

    Returns:
        JSON string with the inputs and converted result.
    """
    result = round(value * factor, 2)
    return json.dumps({"value": value, "factor": factor, "result": result})


async def main() -> None:
    """Run the skills auto-approval demo."""
    endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
    deployment = os.environ.get("FOUNDRY_MODEL", "gpt-4o-mini")

    client = FoundryChatClient(
        project_endpoint=endpoint,
        model=deployment,
        credential=AzureCliCredential(),
    )

    skills_provider = SkillsProvider(unit_converter_skill)

    # Install ToolApprovalMiddleware with the read-only auto-approval rule.
    # load_skill and read_skill_resource are approved automatically; the agent
    # only pauses for run_skill_script.
    #
    # To approve every skill tool without prompting, swap the rule for
    # SkillsProvider.all_tools_auto_approval_rule (the manual approval loop
    # below then becomes a no-op).
    approval_middleware = ToolApprovalMiddleware(
        auto_approval_rules=[SkillsProvider.read_only_tools_auto_approval_rule]
    )

    async with Agent(
        client=client,
        instructions="You are a helpful assistant that can convert units.",
        context_providers=[skills_provider],
        middleware=[approval_middleware],
    ) as agent:
        session = agent.create_session()

        print("Converting units with skill tools and read-only auto-approval")
        print("-" * 60)

        query = "How many kilometers is a marathon (26.2 miles)? And how many pounds is 75 kilograms?"
        print(f"User: {query}")
        result = await agent.run(query, session=session)

        # Read-only tools (load_skill, read_skill_resource) were auto-approved.
        # Only run_skill_script reaches this loop and needs explicit approval.
        # Collect a response for every request and send them in one run so the
        # loop always makes progress.
        while result.user_input_requests:
            approval_responses: list[Content] = []
            for request in result.user_input_requests:
                if request.function_call is None:
                    # Not a function-approval request; reject it so the run can proceed.
                    approval_responses.append(request.to_function_approval_response(approved=False))
                    continue
                print("\nApproval needed:")
                print(f"  Function: {request.function_call.name}")
                print(f"  Arguments: {request.function_call.arguments}")

                # In a real application, prompt the user here.
                approved = True
                print(f"  Decision: {'Approved' if approved else 'Rejected'}")
                approval_responses.append(request.to_function_approval_response(approved=approved))

            result = await agent.run(Message(role="user", contents=approval_responses), session=session)

        print(f"\nAgent: {result}")


if __name__ == "__main__":
    asyncio.run(main())

"""
Sample output:

Converting units with skill tools and read-only auto-approval
------------------------------------------------------------
User: How many kilometers is a marathon (26.2 miles)? And how many pounds is 75 kilograms?

Approval needed:
  Function: run_skill_script
  Arguments: {"skill_name": "unit-converter", "script_name": "convert", ...}
  Decision: Approved

Agent: Here are your conversions:

1. 26.2 miles -> 42.16 km (a marathon distance)
2. 75 kg -> 165.35 lbs
"""
