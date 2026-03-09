# Copyright (c) Microsoft. All rights reserved.

import asyncio
import json
import os
import random
import sys
from pathlib import Path
from textwrap import dedent

from agent_framework import (
    Agent,
    CallbackSkillScriptExecutor,
    Skill,
    SkillsProvider,
)
from agent_framework.azure import AzureOpenAIResponsesClient
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

# Add the skills folder root to sys.path so the shared subprocess_script_runner can be imported
_SKILLS_ROOT = str(Path(__file__).resolve().parent.parent)
if _SKILLS_ROOT not in sys.path:
    sys.path.insert(0, _SKILLS_ROOT)

from subprocess_script_runner import subprocess_script_runner  # noqa: E402

"""
Mixed Skills — Code skills and file skills in a single agent

This sample demonstrates how to combine **code-defined skills** (with
``@skill.script`` and ``@skill.resource`` decorators) and **file-based skills**
(discovered from ``SKILL.md`` files on disk) in a single agent using
``SkillsProvider`` and a ``CallbackSkillScriptExecutor``.

Key concepts shown:
- Code skills with ``@skill.script``: executable Python functions the agent
  can invoke directly in-process.
- Code skills with ``@skill.resource``: dynamic content the agent can read
  on demand.
- File skills from disk: ``SKILL.md`` files with reference documents and
  executable script files.
- ``CallbackSkillScriptExecutor``: routes all script execution (both code
  and file-based) through a single executor, enabling a unified experience.

The sample registers two skills:
1. **pin-generator** (code skill) — generates numeric PINs using
   ``@skill.script`` for generation and ``@skill.resource`` for guidelines.
2. **password-generator** (file skill) — generates secure passwords via a
   subprocess-executed Python script discovered from
   ``skills/password-generator/SKILL.md``.
"""

# Load environment variables from .env file
load_dotenv()

# ---------------------------------------------------------------------------
# 1. Define a code skill with @skill.script and @skill.resource decorators
# ---------------------------------------------------------------------------

pin_generator_skill = Skill(
    name="pin-generator",
    description="Generate numeric PINs for accounts, devices, and verification",
    content=dedent("""\
        Use this skill when the user asks for a numeric PIN (personal
        identification number).

        1. Review the pin-guidelines resource for length recommendations.
        2. Use the generate-pin script with the desired length.
    """),
)


@pin_generator_skill.resource(name="pin-guidelines", description="PIN length recommendations by use case")
def pin_guidelines() -> str:
    """Return PIN generation guidelines."""
    return dedent("""\
        # PIN Generation Guidelines

        | Use Case              | Length | Notes                    |
        |-----------------------|--------|--------------------------|
        | Bank / ATM            | 4      | Standard 4-digit PIN     |
        | Phone unlock          | 6      | Recommended for phones   |
        | Two-factor auth       | 6      | Common for OTP codes     |
        | Secure vault / safe   | 8      | Higher security          |
        | Device pairing        | 4      | Bluetooth / IoT pairing  |

        Always use cryptographically secure randomness.
        Never reuse PINs across accounts.
    """)


@pin_generator_skill.script(name="generate-pin", description="Generate a random numeric PIN of the given length")
def generate_pin(length: int) -> str:
    """Generate a cryptographically secure numeric PIN.

    Args:
        length: Number of digits (default 4, minimum 4, maximum 12).

    Returns:
        JSON string with the generated PIN and its length.
    """
    if length < 4:
        return json.dumps({"error": "PIN length must be >= 4"})
    if length > 12:
        return json.dumps({"error": "PIN length must be <= 12"})

    rng = random.SystemRandom()
    pin = "".join(str(rng.randint(0, 9)) for _ in range(length))
    return json.dumps({"pin": pin, "length": length})


# ---------------------------------------------------------------------------
# 2. Wire everything together and run the agent
# ---------------------------------------------------------------------------


async def main() -> None:
    """Run the combined skills demo."""
    endpoint = os.environ["AZURE_AI_PROJECT_ENDPOINT"]
    deployment = os.environ.get("AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME", "gpt-4o-mini")

    # Create the chat client
    client = AzureOpenAIResponsesClient(
        project_endpoint=endpoint,
        deployment_name=deployment,
        credential=AzureCliCredential(),
    )

    # Create the CallbackSkillScriptExecutor
    # Handles file-based scripts via the callback.  Code-defined
    # scripts (@skill.script) are executed in-process automatically.
    executor = CallbackSkillScriptExecutor(callback=subprocess_script_runner)

    # Create the SkillsProvider with both code and file skills
    skills_dir = Path(__file__).parent / "skills"
    skills_provider = SkillsProvider(
        skill_paths=str(skills_dir),
        skills=[pin_generator_skill],
        script_executor=executor,
    )

    # Run the agent
    async with Agent(
        client=client,
        instructions="You are a helpful assistant that can generate PINs and passwords.",
        context_providers=[skills_provider],
    ) as agent:
        # Ask the agent to generate both a PIN and a password
        print("Generating a PIN and a password")
        print("-" * 60)
        response = await agent.run(
            "I'm setting up a new bank account and need two "
            "things: a 6-digit PIN for ATM access, and a "
            "secure password for online banking. "
            "Please generate both."
        )
        print(f"Agent: {response}\n")


if __name__ == "__main__":
    asyncio.run(main())

"""
Sample output:

Generating a PIN and a password
------------------------------------------------------------
Agent: Here are your new credentials:

**ATM PIN (6 digits):** `839201`

**Online Banking Password (24 characters):**
`aR3$vK8!mN2@pQ7&xL5#wY9b`

The PIN was generated using a cryptographically secure random number
generator. The password follows the recommended guidelines for database
credentials — 24 characters with upper + lower case letters, digits,
and symbols.

Remember to store both securely and never reuse them across services.
"""
