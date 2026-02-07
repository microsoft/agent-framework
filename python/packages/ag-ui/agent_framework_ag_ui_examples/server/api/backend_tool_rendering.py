# Copyright (c) Microsoft. All rights reserved.

"""Backend tool rendering endpoint."""

from typing import Any, cast

from agent_framework._clients import SupportsChatGetResponse
from agent_framework.ag_ui import add_agent_framework_fastapi_endpoint
from agent_framework.azure import AzureOpenAIChatClient
from fastapi import FastAPI

from ...agents.weather_agent import weather_agent


def register_backend_tool_rendering(app: FastAPI) -> None:
    """Register the backend tool rendering endpoint.

    Args:
        app: The FastAPI application.
    """
    # Create a chat client and call the factory function
    client = cast(SupportsChatGetResponse[Any], AzureOpenAIChatClient())

    add_agent_framework_fastapi_endpoint(
        app,
        weather_agent(client),
        "/backend_tool_rendering",
    )
