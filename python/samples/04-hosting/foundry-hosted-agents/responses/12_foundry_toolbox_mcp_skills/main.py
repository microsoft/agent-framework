# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os

from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from agent_framework_foundry_hosting import FoundryToolbox, ResponsesHostServer
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


async def main() -> None:
    credential = DefaultAzureCredential()

    # FoundryToolbox resolves the toolbox endpoint from the environment
    # (TOOLBOX_ENDPOINT, or FOUNDRY_PROJECT_ENDPOINT + TOOLBOX_NAME), authenticates
    # every request with the credential, and forwards the platform per-request
    # call-id. ``load_tools=False`` keeps the toolbox's tools hidden so only its
    # Agent Skills (SEP-2640) are surfaced; passing it via ``tools=`` connects the
    # MCP session that ``as_skills_provider()`` reads from.
    toolbox = FoundryToolbox(credential, load_tools=False)

    # as_skills_provider() discovers skills from skill://index.json on the toolbox
    # MCP session and exposes them as an agent context provider; SKILL.md bodies are
    # fetched on demand via resources/read.
    skills_provider = toolbox.as_skills_provider()

    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        credential=credential,
    )

    agent = Agent(
        client=client,
        name=os.environ.get("AGENT_NAME", "hosted-toolbox-mcp-skills"),
        instructions="You are a helpful assistant.",
        tools=toolbox,
        context_providers=[skills_provider],
        # History will be managed by the hosting infrastructure, thus there
        # is no need to store history by the service. Learn more at:
        # https://developers.openai.com/api/reference/resources/responses/methods/create
        default_options={"store": False},
    )

    server = ResponsesHostServer(agent)
    await server.run_async()


if __name__ == "__main__":
    asyncio.run(main())
