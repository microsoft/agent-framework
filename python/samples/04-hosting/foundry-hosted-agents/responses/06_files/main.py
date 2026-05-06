# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
from collections.abc import Callable
from typing import Any

from agent_framework import Agent, MCPStreamableHTTPTool, tool
from agent_framework.foundry import FoundryChatClient
from agent_framework_foundry_hosting import ResponsesHostServer
from azure.core.credentials import TokenCredential
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


def make_toolbox_header_provider(credential: TokenCredential) -> Callable[[dict[str, Any]], dict[str, str]]:
    """Build a header_provider that injects a fresh Azure AI bearer token on every MCP request."""
    get_token = get_bearer_token_provider(credential, "https://ai.azure.com/.default")

    def provide(_kwargs: dict[str, Any]) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {get_token()}",
        }

    return provide


@tool(description="Get the current working directory.", approval_mode="never_require")
def get_cwd() -> str:
    """Get the current working directory."""
    try:
        return os.getcwd()
    except Exception as e:
        return f"Error getting current working directory: {e}"


@tool(description="List files in a directory.", approval_mode="never_require")
def list_files(directory: str) -> list[str]:
    """List files in a directory."""
    try:
        return os.listdir(directory)
    except Exception as e:
        return [f"Error listing files in {directory}: {e}"]


@tool(description="Read the contents of a file.", approval_mode="never_require")
def read_file(file_path: str) -> str:
    """Read the contents of a file."""
    try:
        with open(file_path) as f:
            return f.read()
    except Exception as e:
        return f"Error reading file {file_path}: {e}"


async def main():
    credential = DefaultAzureCredential()

    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        credential=credential,
    )

    # Connect to the toolbox MCP endpoint and expose only the code_interpreter tool.
    # The toolbox deployed has two tools: (see agent.manifest.yaml)
    # - `code_interpreter`
    # - `web_search`
    # We only need the `code_interpreter` tool for this sample.
    toolbox_tool = MCPStreamableHTTPTool(
        name="foundry_toolbox",
        description="Tools exposed by the configured Foundry toolbox",
        url=os.environ["FOUNDRY_TOOLBOX_ENDPOINT"],
        header_provider=make_toolbox_header_provider(credential),
        load_prompts=False,
        allowed_tools=["code_interpreter"],
    )

    async with Agent(
        client=client,
        instructions=(
            "You are a friendly assistant. Keep your answers brief. "
            "Make sure all mathematical calculations are performed using the code interpreter "
            "instead of mental arithmetic."
        ),
        tools=[get_cwd, list_files, read_file, toolbox_tool],
        # History will be managed by the hosting infrastructure, thus there
        # is no need to store history by the service. Learn more at:
        # https://developers.openai.com/api/reference/resources/responses/methods/create
        default_options={"store": False},
    ) as agent:
        server = ResponsesHostServer(agent)
        await server.run_async()


if __name__ == "__main__":
    asyncio.run(main())
