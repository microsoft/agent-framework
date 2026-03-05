# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
import sys
from textwrap import dedent
from typing import Any

from agent_framework import Agent, Skill, SkillResource, SkillsProvider
from agent_framework.azure import AzureOpenAIResponsesClient
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

"""
Code-Defined Agent Skills — Define skills in Python code

This sample demonstrates how to create Agent Skills in code,
without needing SKILL.md files on disk. Three patterns are shown:

Pattern 1: Basic Code Skill
  Create a Skill instance directly with static resources (inline content).

Pattern 2: Dynamic Resources
  Create a Skill and attach callable resources via the @skill.resource
  decorator. Resources can be sync or async functions that generate content at
  invocation time.

Pattern 3: Dynamic Resources with kwargs
  Attach a callable resource that accepts **kwargs to receive runtime
  arguments passed via agent.run(). This is useful for injecting
  request-scoped context (user tokens, session data) into skill resources.

Both patterns can be combined with file-based skills in a single SkillsProvider.
"""

# Load environment variables from .env file
load_dotenv()

# Pattern 1: Basic Code Skill — direct construction with static resources
code_style_skill = Skill(
    name="code-style",
    description="Coding style guidelines and conventions for the team",
    content=dedent("""\
        Use this skill when answering questions about coding style, conventions,
        or best practices for the team.
    """),
    resources=[
        SkillResource(
            name="style-guide",
            content=dedent("""\
                # Team Coding Style Guide

                ## General Rules
                - Use 4-space indentation (no tabs)
                - Maximum line length: 120 characters
                - Use type annotations on all public functions
                - Use Google-style docstrings

                ## Naming Conventions
                - Classes: PascalCase (e.g., UserAccount)
                - Functions/methods: snake_case (e.g., get_user_name)
                - Constants: UPPER_SNAKE_CASE (e.g., MAX_RETRIES)
                - Private members: prefix with underscore (e.g., _internal_state)
            """),
        ),
    ],
)

# Pattern 2: Dynamic Resources — @skill.resource decorator
project_info_skill = Skill(
    name="project-info",
    description="Project status and configuration information",
    content=dedent("""\
        Use this skill for questions about the current project status,
        environment configuration, or team structure.
    """),
)


@project_info_skill.resource
def environment(**kwargs: Any) -> str:
    """Get current environment configuration."""
    # Access runtime kwargs passed via agent.run(app_version="...")
    app_version = kwargs.get("app_version", "unknown")
    env = os.environ.get("APP_ENV", "development")
    region = os.environ.get("APP_REGION", "us-east-1")
    return f"""\
      # Environment Configuration
      - App Version: {app_version}
      - Environment: {env}
      - Region: {region}
      - Python: {sys.version}
    """


@project_info_skill.resource(name="team-roster", description="Current team members and roles")
def get_team_roster() -> str:
    """Return the team roster."""
    return """\
      # Team Roster
      | Name         | Role              |
      |--------------|-------------------|
      | Alice Chen   | Tech Lead         |
      | Bob Smith    | Backend Engineer  |
      | Carol Davis  | Frontend Engineer |
    """


async def main() -> None:
    """Run the code-defined skills demo."""
    endpoint = os.environ["AZURE_AI_PROJECT_ENDPOINT"]
    deployment = os.environ.get("AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME", "gpt-4o-mini")

    client = AzureOpenAIResponsesClient(
        project_endpoint=endpoint,
        deployment_name=deployment,
        credential=AzureCliCredential(),
    )

    # Create the skills provider with both code-defined skills
    skills_provider = SkillsProvider(
        skills=[code_style_skill, project_info_skill],
    )

    async with Agent(
        client=client,
        instructions="You are a helpful assistant for our development team.",
        context_providers=[skills_provider],
    ) as agent:
        # Example 1: Code style question (Pattern 1 — static resources)
        print("Example 1: Code style question")
        print("-------------------------------")
        response = await agent.run("What naming convention should I use for class attributes?")
        print(f"Agent: {response}\n")

        # Example 2: Project info question (Pattern 2 & 3 — dynamic resources with kwargs)
        print("Example 2: Project info question")
        print("---------------------------------")
        # Pass app_version as a runtime kwarg; it flows to the environment() resource via **kwargs
        response = await agent.run("What environment are we running in and who is on the team?", app_version="2.4.1")
        print(f"Agent: {response}\n")

    """
    Expected output:

    Example 1: Code style question
    -------------------------------
    Agent: Based on our team's coding style guide, class attributes should follow
    snake_case naming. Private attributes use an underscore prefix (_internal_state).
    Constants use UPPER_SNAKE_CASE (MAX_RETRIES).

    Example 2: Project info question
    ---------------------------------
    Agent: We're running app version 2.4.1 in the development environment
    in us-east-1. The team consists of Alice Chen (Tech Lead), Bob Smith
    (Backend Engineer), and Carol Davis (Frontend Engineer).
    """


if __name__ == "__main__":
    asyncio.run(main())
