# Copyright (c) Microsoft. All rights reserved.

import asyncio
import logging
from pathlib import Path

from agent_framework import HostedCodeInterpreterTool, HostedFileContent
from agent_framework.anthropic import AnthropicClient

logger = logging.getLogger(__name__)
"""
Anthropic Skills Agent Example

This sample demonstrates using Anthropic with:
- Listing and using Anthropic-managed Skills.
- One approach to add additional beta flags.
    You can also set additonal_chat_options with "additional_beta_flags" per request.
- Creating an agent with the Code Interpreter tool and a Skill.
- Catching and downloading generated files from the agent.
"""


async def main() -> None:
    """Example of streaming response (get results as they are generated)."""
    client = AnthropicClient(additional_beta_flags=["skills-2025-10-02"])

    # List Anthropic-managed Skills
    skills = await client.anthropic_client.beta.skills.list(source="anthropic", betas=["skills-2025-10-02"])
    for skill in skills.data:
        print(f"{skill.source}: {skill.id} (version: {skill.latest_version})")

    # Create a agent with the pptx skill enabled
    # Skills also need the code interpreter tool to function
    agent = client.create_agent(
        name="DocsAgent",
        instructions="You are a helpful agent for creating powerpoint presentations.",
        tools=HostedCodeInterpreterTool(),
        max_tokens=20000,
        additional_chat_options={
            "thinking": {"type": "enabled", "budget_tokens": 10000},
            "container": {"skills": [{"type": "anthropic", "skill_id": "pptx", "version": "latest"}]},
        },
    )

    print(
        "The agent output will use the following colors:\n"
        "\033[0mUser: (default)\033[0m\n"
        "\033[0mAgent: (default)\033[0m\n"
        "\033[32mAgent Reasoning: (green)\033[0m\n"
        "\033[34mUsage: (blue)\033[0m\n"
    )
    query = "Create a presentation about renewable energy with 5 slides"
    print(f"User: {query}")
    print("Agent: ", end="", flush=True)
    files: list[HostedFileContent] = []
    async for chunk in agent.run_stream(query):
        for content in chunk.contents:
            match content.type:
                case "text":
                    print(content.text, end="", flush=True)
                case "text_reasoning":
                    print(f"\033[32m{content.text}\033[0m", end="", flush=True)
                case "usage":
                    print(f"\n\033[34m[Usage so far: {content.details}]\033[0m\n", end="", flush=True)
                case "hosted_file":
                    # Catch generated files
                    files.append(content)
                case _:
                    logger.debug("Unhandled content type: %s", content.type)
                    pass

    print("\n")
    if files:
        # Save to a new file (will be in the folder where you are running this script)
        # When running this sample multiple times, the files will be overritten
        # Since I'm using the pptx skill, the files will be PowerPoint presentations
        print("Generated files:")
        for idx, file in enumerate(files):
            file_content = await client.anthropic_client.beta.files.download(
                file_id=file.file_id, betas=["files-api-2025-04-14"]
            )
            with open(Path(__file__).parent / f"renewable_energy-{idx}.pptx", "wb") as f:
                await file_content.write_to_file(f.name)
            print(f"File {idx}: renewable_energy-{idx}.pptx saved to disk.")


if __name__ == "__main__":
    asyncio.run(main())
