# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
import sys
from dataclasses import dataclass
from textwrap import dedent
from typing import Any

from agent_framework import Agent, Skill, SkillContext, SkillResource, SkillsProvider
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

Pattern 3: Typed Dependencies via SkillContext
  Pass deps to Skill so Pyright/mypy verify that @skill.resource callables
  declare a matching SkillContext[DepsT] parameter. The provider injects a typed
  context object at invocation time, giving the resource access to shared
  dependencies (database clients, config, etc.).

Pattern 4: Runtime kwargs
  Resource functions with **kwargs receive runtime arguments forwarded from
  agent.run(). Combine with SkillContext for both typed deps and dynamic args.

All patterns can be combined with file-based skills in a single SkillsProvider.
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
# Pattern 3: Typed Dependencies via SkillContext


@dataclass
class ProjectDeps:
    """Shared dependencies for project-info skill resources."""

    app_version: str = "2.4.1"


# By passing deps, Pyright/mypy verify that @skill.resource callables
# declare a matching SkillContext[ProjectDeps] parameter.
project_info_skill = Skill(
    name="project-info",
    description="Project status, configuration, team info, and request context",
    content=dedent("""\
        Use this skill for questions about the current project status,
        environment configuration, team structure, or request context.
    """),
    deps=ProjectDeps(),
)


@project_info_skill.resource
def environment(ctx: SkillContext[ProjectDeps]) -> str:
    """Get current environment configuration."""
    env = os.environ.get("APP_ENV", "development")
    region = os.environ.get("APP_REGION", "us-east-1")
    return f"""\
      # Environment Configuration
      - App Version: {ctx.deps.app_version}
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


# Pattern 4: Runtime kwargs — resource receives arguments from agent.run()
@project_info_skill.resource(name="caller-info", description="Information about the caller")
def get_caller_info(ctx: SkillContext[ProjectDeps], **kwargs: Any) -> str:
    """Return caller info combining typed deps and runtime kwargs."""
    caller = kwargs.get("caller_name", "unknown")
    role = kwargs.get("caller_role", "unknown")
    return f"""\
      # Caller Info
      - Name: {caller}
      - Role: {role}
      - App Version: {ctx.deps.app_version}
    """


@project_info_skill.resource(name="request-context", description="Request context from kwargs only")
def get_request_context(**kwargs: Any) -> str:
    """Return request context from runtime kwargs only (no SkillContext)."""
    request_id = kwargs.get("request_id", "none")
    client_agent = kwargs.get("client_agent", "unknown")
    return f"""\
      # Request Context
      - Request ID: {request_id}
      - Client Agent: {client_agent}
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

        # Example 2: Project info question (Patterns 2 & 3 — dynamic resources with SkillContext)
        print("Example 2: Project info question")
        print("---------------------------------")
        response = await agent.run("What environment are we running in and who is on the team?")
        print(f"Agent: {response}\n")

        # Example 3: kwargs forwarding (Pattern 4 — runtime kwargs reach resource functions)
        print("Example 3: Caller info via kwargs")
        print("----------------------------------")
        response = await agent.run(
            "Who is calling and what app version are we on?",
            caller_name="Alice Chen",
            caller_role="Tech Lead",
        )
        print(f"Agent: {response}\n")

        # Example 4: kwargs-only resource (no SkillContext, just **kwargs)
        print("Example 4: Request context via kwargs only")
        print("-------------------------------------------")
        response = await agent.run(
            "What is the current request context?",
            request_id="req-42",
            client_agent="cli",
        )
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

    Example 3: Caller info via kwargs
    ----------------------------------
    Agent: The caller is Alice Chen (Tech Lead), running app version 2.4.1.

    Example 4: Request context via kwargs only
    -------------------------------------------
    Agent: The current request context is Request ID req-42 from client agent cli.
    """


if __name__ == "__main__":
    asyncio.run(main())
