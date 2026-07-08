# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
from collections.abc import Callable
from urllib.parse import urlsplit

import httpx
from agent_framework import Agent, MCPStreamableHTTPTool, tool
from agent_framework.foundry import FoundryChatClient
from agent_framework_foundry_hosting import ResponsesHostServer
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


def resolve_toolbox_endpoint() -> str:
    """Resolve the toolbox MCP endpoint URL.

    Prefers the explicit ``TOOLBOX_ENDPOINT`` env var (set in ``agent.yaml`` or
    ``agent.manifest.yaml`` and via ``azd env set TOOLBOX_ENDPOINT`` after the toolbox
    is created); falls back to constructing the URL from ``FOUNDRY_PROJECT_ENDPOINT``
    and ``TOOLBOX_NAME``.
    """
    if (endpoint := os.environ.get("TOOLBOX_ENDPOINT")) is not None:
        if not endpoint:
            raise ValueError("TOOLBOX_ENDPOINT is set but empty")
        return endpoint
    try:
        project_endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"].rstrip("/")
        toolbox_name = os.environ["TOOLBOX_NAME"]
    except KeyError as e:
        raise ValueError(
            "Either set TOOLBOX_ENDPOINT, or set both FOUNDRY_PROJECT_ENDPOINT "
            "and TOOLBOX_NAME to build the toolbox MCP endpoint."
        ) from e
    return f"{project_endpoint}/toolboxes/{toolbox_name}/mcp?api-version=v1"


def _toolbox_name_from_endpoint(endpoint: str) -> str:
    """Extract the toolbox name from a toolbox MCP endpoint URL.

    Handles both the versioned (``.../toolboxes/<name>/versions/<n>/mcp``) and
    unversioned (``.../toolboxes/<name>/mcp``) endpoint shapes that Foundry
    produces. Falls back to ``"toolbox"`` when the path has no ``toolboxes``
    segment.
    """
    segments = urlsplit(endpoint).path.split("/")
    if "toolboxes" in segments:
        idx = segments.index("toolboxes")
        if idx + 1 < len(segments) and segments[idx + 1]:
            return segments[idx + 1]
    return "toolbox"


class ToolboxAuth(httpx.Auth):
    """Injects a fresh bearer token on every request."""

    def __init__(self, token_provider: Callable[[], str]):
        self._get_token = token_provider

    def auth_flow(self, request: httpx.Request):
        request.headers["Authorization"] = f"Bearer {self._get_token()}"
        yield request


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

    # Create the toolbox
    token_provider = get_bearer_token_provider(credential, "https://ai.azure.com/.default")

    # Resolve the endpoint once and derive a friendly tool name from it. When
    # ``TOOLBOX_NAME`` isn't set, extract the toolbox name from the URL path so
    # the tool's local name matches the upstream toolbox.
    toolbox_endpoint = resolve_toolbox_endpoint()
    toolbox_name = os.environ.get("TOOLBOX_NAME") or _toolbox_name_from_endpoint(toolbox_endpoint)

    async with httpx.AsyncClient(
        auth=ToolboxAuth(token_provider),
        timeout=120.0,
    ) as http_client:
        toolbox = MCPStreamableHTTPTool(
            name=toolbox_name,
            url=toolbox_endpoint,
            http_client=http_client,
            load_prompts=False,
        )

        # Create the chat client
        client = FoundryChatClient(
            project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
            model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
            credential=credential,
        )

        agent = Agent(
            client=client,
            instructions=(
                "You are a friendly assistant. Keep your answers brief. "
                "Make sure all mathematical calculations are performed using the code interpreter "
                "instead of mental arithmetic."
            ),
            tools=[get_cwd, list_files, read_file, toolbox],
            # History will be managed by the hosting infrastructure, thus there
            # is no need to store history by the service. Learn more at:
            # https://developers.openai.com/api/reference/resources/responses/methods/create
            default_options={"store": False},
        )
        server = ResponsesHostServer(agent)
        await server.run_async()


if __name__ == "__main__":
    asyncio.run(main())
