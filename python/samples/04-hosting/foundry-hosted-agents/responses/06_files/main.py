# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os

from agent_framework import Agent, tool
from agent_framework.foundry import FoundryChatClient
from agent_framework_foundry import select_toolbox_tools
from agent_framework_foundry_hosting import ResponsesHostServer
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


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
    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        credential=DefaultAzureCredential(),
    )

    # Load the named toolbox from the Foundry project. Omitting `version`
    # resolves the toolbox's current default version at runtime.
    toolbox = await client.get_toolbox(os.environ["TOOLBOX_NAME"])
    # The toolbox deployed has two tools: (see agent.manifest.yaml)
    # - `code_interpreter`
    # - `web_search`
    # We only need the `code_interpreter` tool for this sample
    selected_tools = select_toolbox_tools(
        toolbox,
        include_names=["code_interpreter"],
    )

    agent = Agent(
        client=client,
        instructions=(
            "You are a friendly assistant. Keep your answers brief. "
            "Make sure all mathematical calculations are performed using the code interpreter "
            "instead of mental arithmetic."
        ),
        tools=[get_cwd, list_files, read_file] + selected_tools,
        # History will be managed by the hosting infrastructure, thus there
        # is no need to store history by the service. Learn more at:
        # https://developers.openai.com/api/reference/resources/responses/methods/create
        default_options={"store": False},
    )

    server = ResponsesHostServer(agent)
    await server.run_async()


if __name__ == "__main__":
    asyncio.run(main())
