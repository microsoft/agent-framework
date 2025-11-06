# Copyright (c) Microsoft. All rights reserved.

"""Backend tool rendering endpoint."""

from fastapi import FastAPI

from agent_framework_ag_ui import add_agent_framework_fastapi_endpoint

from ...agents.weather_agent import weather_agent


def register_backend_tool_rendering(app: FastAPI) -> None:
    """Register the backend tool rendering endpoint.

    Args:
        app: The FastAPI application.
    """
    add_agent_framework_fastapi_endpoint(
        app,
        weather_agent,
        "/backend_tool_rendering",
    )
