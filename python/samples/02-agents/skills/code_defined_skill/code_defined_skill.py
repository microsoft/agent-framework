# Copyright (c) Microsoft. All rights reserved.

import asyncio
import json
import os
import random
import string
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
using a password-generator skill:

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
password_skill = Skill(
    name="password-generator",
    description="Generate secure passwords for accounts and services",
    content=dedent("""\
        Use this skill when the user asks to generate a password.

        1. Review the password-guidelines resource for recommended settings.
        2. Check the password-policy resource for the current policy.
        3. Use the generate-password script to create a password of the appropriate length.
    """),
    resources=[
        SkillResource(
            name="password-guidelines",
            content=dedent("""\
                # Password Generation Guidelines

                ## Recommended Settings by Use Case
                | Use Case              | Min Length | Character Set                     |
                |-----------------------|-----------|-----------------------------------|
                | Web account           | 16        | Upper + lower + digits + symbols  |
                | Database credential   | 24        | Upper + lower + digits + symbols  |
                | Wi-Fi / network key   | 20        | Upper + lower + digits + symbols  |
                | API key / token       | 32        | Upper + lower + digits (no symbols)|

                ## General Rules
                - Never reuse passwords across services.
                - Always use cryptographically secure randomness.
                - Avoid dictionary words, keyboard patterns, and personal information.
            """),
        ),
    ],
)


# ---------------------------------------------------------------------------
# 2. Dynamic Resources — callable function via @skill.resource
# ---------------------------------------------------------------------------
@password_skill.resource(name="password-policy", description="Current password policy with today's rotation schedule")
def password_policy(**kwargs: Any) -> str:
    """Return the current password policy.

    Dynamic resources are evaluated at runtime, so they can include
    live data such as dates, configuration values, or database lookups.

    When the resource function accepts ``**kwargs``, runtime keyword
    arguments passed to ``agent.run()`` are forwarded automatically.

    Args:
        **kwargs: Runtime keyword arguments from ``agent.run()``.
            For example, ``agent.run(..., environment="production")``
            makes ``kwargs["environment"]`` available here.
    """
    from datetime import datetime, timezone

    environment = kwargs.get("environment", "development")
    today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    return dedent(f"""\
        # Current Password Policy

        **Policy date:** {today}
        **Environment:** {environment}

        - Must include uppercase, lowercase, digits, and symbols
        - Passwords expire every 90 days
        - Cannot reuse the last 5 passwords
    """)


# ---------------------------------------------------------------------------
# 3. Dynamic Scripts — in-process callable function
# ---------------------------------------------------------------------------
@password_skill.script(name="generate-password", description="Generate a secure random password")
def generate_password(length: int = 16, **kwargs: Any) -> str:
    """Generate a cryptographically secure password.

    Args:
        length: Password length (minimum 4, default 16).
        **kwargs: Runtime keyword arguments from ``agent.run()``.

    Returns:
        JSON string with the generated password and its length.
    """
    if length < 4:
        return json.dumps({"error": "Password length must be >= 4"})

    pool = string.ascii_lowercase + string.ascii_uppercase + string.digits + string.punctuation
    rng = random.SystemRandom()
    password = "".join(rng.choice(pool) for _ in range(length))

    return json.dumps({
        "password": password,
        "length": length,
        "environment": kwargs.get("environment", "development"),
    })


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
        skills=[password_skill],
    )

    async with Agent(
        client=client,
        instructions="You are a helpful assistant that can generate passwords.",
        context_providers=[skills_provider],
    ) as agent:
        print("Generating a secure password")
        print("-" * 60)
        response = await agent.run(
            "I need a secure password for a new PostgreSQL database. "
            "Please generate one following best practices.",
            environment="production",
        )
        print(f"Agent: {response}\n")


if __name__ == "__main__":
    asyncio.run(main())

"""
Sample output:

Generating a secure password
------------------------------------------------------------
Agent: Based on the password guidelines, database credentials should use
at least 24 characters with upper + lower case letters, digits, and symbols.

I generated a password for you:

{"password": "aR3$vK8!mN2@pQ7&xL5#wY9b", "length": 24}

This password was generated using a cryptographically secure random
generator. Remember to store it securely and never reuse it across services.
"""
