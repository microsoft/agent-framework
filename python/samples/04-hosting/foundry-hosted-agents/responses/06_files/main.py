# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
import subprocess

from agent_framework import Agent, tool
from agent_framework.foundry import FoundryChatClient
from agent_framework_foundry import select_toolbox_tools
from agent_framework_foundry_hosting import ResponsesHostServer
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


@tool(
    description="Execute a shell command for filesystem operations.",
    approval_mode="never_require",
)
def run_bash(command: str) -> str:
    """Execute a shell command locally and return stdout, stderr, and exit code."""
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        parts: list[str] = []
        if result.stdout:
            parts.append(result.stdout)
        if result.stderr:
            parts.append(f"stderr: {result.stderr}")
        parts.append(f"exit_code: {result.returncode}")
        return "\n".join(parts)
    except subprocess.TimeoutExpired:
        return "Command timed out after 30 seconds"
    except Exception as e:
        return f"Error executing command: {e}"


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
        tools=[run_bash] + selected_tools,
        # History will be managed by the hosting infrastructure, thus there
        # is no need to store history by the service. Learn more at:
        # https://developers.openai.com/api/reference/resources/responses/methods/create
        default_options={"store": False},
    )

    server = ResponsesHostServer(agent)
    await server.run_async()


if __name__ == "__main__":
    asyncio.run(main())
