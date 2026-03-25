# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
from textwrap import dedent

from agent_framework import Agent, Skill, SkillsProvider
from agent_framework.foundry import FoundryChatClient
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

"""
Skill Script Approval — Require human approval before executing skill scripts

This sample demonstrates how to use ``require_script_approval=True`` on
:class:`SkillsProvider` so that every call to ``run_skill_script`` is
gated by a human-in-the-loop approval step.

How it works:
1. A code-defined skill with a script is registered via SkillsProvider.
2. ``require_script_approval=True`` causes the agent to pause and return
   approval requests in ``result.user_input_requests`` instead of executing
   scripts immediately.
3. The application inspects each request and calls
   ``request.to_function_approval_response(approved=True|False)`` to approve
   or reject.
4. The approval response is sent back via ``agent.run(approval_response, session=session)``
   and the agent continues — executing the script if approved, or receiving
   an error if rejected.

Prerequisites:
- FOUNDRY_PROJECT_ENDPOINT must be your Azure AI Foundry Agent Service (V2) project endpoint.
- FOUNDRY_MODEL (defaults to "gpt-4o-mini").
"""

# Load environment variables from .env file
load_dotenv()

# Define a code skill with a script that performs a sensitive operation
deployment_skill = Skill(
    name="deployment",
    description="Tools for deploying application versions to production",
    content=dedent("""\
        Use this skill when the user asks to deploy an application.

        1. Run the deploy script with the version and environment parameters.
    """),
)


@deployment_skill.script
def deploy(version: str, environment: str = "staging") -> str:
    """Deploy the application to the specified environment."""
    return f"Deployed version {version} to {environment}"


async def main() -> None:
    """Run the skill script approval demo."""
    endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
    deployment = os.environ.get("FOUNDRY_MODEL", "gpt-4o-mini")

    client = FoundryChatClient(
        project_endpoint=endpoint,
        model=deployment,
        credential=AzureCliCredential(),
    )

    # Create the skills provider with script approval enabled
    skills_provider = SkillsProvider(
        skills=[deployment_skill],
        require_script_approval=True,
    )

    async with Agent(
        client=client,
        instructions="You are a deployment assistant. Use the deployment skill to deploy applications.",
        context_providers=[skills_provider],
    ) as agent:
        session = agent.create_session()

        print("Starting agent with skill script approval enabled...")
        print("-" * 60)

        # Step 1: Send the user request — the agent will try to call the script
        query = "Deploy the latest application version 2.5.0 to the production environment"
        print(f"User: {query}")
        result = await agent.run(query, session=session)

        # Step 2: Handle approval requests (with sessions, context is
        # maintained automatically — just send the approval response)
        while result.user_input_requests:
            for request in result.user_input_requests:
                print("\nApproval needed:")
                print(f"  Function: {request.function_call.name}")  # type: ignore[union-attr]
                print(f"  Arguments: {request.function_call.arguments}")  # type: ignore[union-attr]

                # In a real application, prompt the user here
                approved = True  # Change to False to see rejection
                print(f"  Decision: {'Approved' if approved else 'Rejected'}")

                # Send the approval response — session preserves conversation history
                approval_response = request.to_function_approval_response(approved=approved)
                result = await agent.run(approval_response, session=session)

        print(f"\nAgent: {result}")


if __name__ == "__main__":
    asyncio.run(main())

"""
Sample output:

Starting agent with skill script approval enabled...
------------------------------------------------------------
User: Deploy version 2.5.0 to production

Approval needed:
  Function: run_skill_script
  Arguments: {"skill_name": "deployment", "script_name": "deploy", ...}
  Decision: Approved

Agent: Successfully deployed version 2.5.0 to production.
"""
