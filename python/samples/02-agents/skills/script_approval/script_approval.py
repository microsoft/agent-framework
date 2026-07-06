# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os

# Uncomment this filter to suppress the experimental Skills warning before
# using the sample's Skills APIs.
# import warnings
# warnings.filterwarnings("ignore", message=r"\[SKILLS\].*", category=FutureWarning)
from textwrap import dedent

from agent_framework import Agent, Content, InlineSkill, Message, SkillFrontmatter, SkillsProvider
from agent_framework.foundry import FoundryChatClient
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

"""
Skill Tool Approval — Require human approval before running skill tools

Every tool exposed by :class:`SkillsProvider` (``load_skill``,
``read_skill_resource``, and ``run_skill_script``) requires host approval by
default. This sample shows the manual human-in-the-loop pattern: the agent
pauses and returns approval requests, and the application approves or rejects
each one before the agent continues.

How it works:
1. A code-defined skill with a script is registered via SkillsProvider.
2. Because skill tools require approval by default, the agent pauses and returns
   approval requests in ``result.user_input_requests`` instead of executing
   tools immediately.
3. The application inspects each request and calls
   ``request.to_function_approval_response(approved=True|False)`` to approve
   or reject.
4. The approval response is sent back via ``agent.run(approval_response, session=session)``
   and the agent continues — running the tool if approved, or receiving an
   error if rejected.

To approve skill tools automatically instead of prompting, use
``ToolApprovalMiddleware`` with one of the static auto-approval rules — see
``samples/02-agents/skills/skills_auto_approval/skills_auto_approval.py``.

Prerequisites:
- FOUNDRY_PROJECT_ENDPOINT must be your Azure AI Foundry Agent Service (V2) project endpoint.
- FOUNDRY_MODEL (defaults to "gpt-4o-mini").
"""

# Load environment variables from .env file
load_dotenv()

# Define a code skill with a script that performs a sensitive operation
deployment_skill = InlineSkill(
    frontmatter=SkillFrontmatter(
        name="deployment", description="Tools for deploying application versions to production"
    ),
    instructions=dedent("""\
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

    # Create the skills provider. All skill tools require approval by default.
    skills_provider = SkillsProvider(
        source=[deployment_skill],
    )

    async with Agent(
        client=client,
        instructions="You are a deployment assistant. Use the deployment skill to deploy applications.",
        context_providers=[skills_provider],
    ) as agent:
        session = agent.create_session()

        print("Starting agent with skill tool approval (the default)...")
        print("-" * 60)

        # Step 1: Send the user request — the agent will try to call the script
        query = "Deploy the latest application version 2.5.0 to the production environment"
        print(f"User: {query}")
        result = await agent.run(query, session=session)

        # Step 2: Handle approval requests (with sessions, context is
        # maintained automatically). Collect a response for every request and
        # send them in one run so the loop always makes progress.
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

                # In a real application, prompt the user here
                approved = True  # Change to False to see rejection
                print(f"  Decision: {'Approved' if approved else 'Rejected'}")
                approval_responses.append(request.to_function_approval_response(approved=approved))

            # Send the approval responses — session preserves conversation history
            result = await agent.run(Message(role="user", contents=approval_responses), session=session)

        print(f"\nAgent: {result}")


if __name__ == "__main__":
    asyncio.run(main())

"""
Sample output:

Starting agent with skill tool approval (the default)...
------------------------------------------------------------
User: Deploy the latest application version 2.5.0 to the production environment

Approval needed:
  Function: load_skill
  Arguments: {"skill_name": "deployment"}
  Decision: Approved

Approval needed:
  Function: run_skill_script
  Arguments: {"skill_name": "deployment", "script_name": "deploy", ...}
  Decision: Approved

Agent: Successfully deployed version 2.5.0 to production.
"""
