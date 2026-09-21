# Copyright (c) Microsoft. All rights reserved.

"""Example FastAPI server with AG-UI endpoints."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, cast

import uvicorn
from agent_framework import ChatOptions
from agent_framework._clients import SupportsChatGetResponse
from agent_framework.ag_ui import add_agent_framework_fastapi_endpoint
from agent_framework.azure import AzureOpenAIChatClient
from agent_framework.openai import OpenAIChatCompletionClient
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ..agents.a2ui_agents import (
    A2UI_DEMO_CONFIG,
    a2ui_advanced_agent,
    a2ui_dynamic_schema_agent,
    a2ui_fixed_schema_agent,
    a2ui_recovery_agent,
)
from ..agents.document_writer_agent import document_writer_agent
from ..agents.human_in_the_loop_agent import human_in_the_loop_agent
from ..agents.recipe_agent import recipe_agent
from ..agents.simple_agent import simple_agent
from ..agents.subgraphs_agent import subgraphs_agent
from ..agents.task_steps_agent import task_steps_agent_wrapped
from ..agents.ui_generator_agent import ui_generator_agent
from ..agents.weather_agent import weather_agent
from ..agents.weather_state_agent import weather_state_agent

AnthropicClient: type[Any] | None
try:
    import agent_framework.anthropic as _anthropic_namespace
except ImportError:
    # If the Anthropic client isn't installed, we can still run the server with Azure OpenAI as the default chat client
    AnthropicClient = None
else:
    AnthropicClient = cast(type[Any] | None, getattr(_anthropic_namespace, "AnthropicClient", None))

# Configure logging to file and console (disabled by default - set ENABLE_DEBUG_LOGGING=1 to enable)
if os.getenv("ENABLE_DEBUG_LOGGING"):
    log_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "ag_ui_server.log")

    # Remove any existing handlers
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Configure new handlers
    file_handler = logging.FileHandler(log_file, mode="w")
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))

    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)
    root_logger.setLevel(logging.INFO)

    # Explicitly set log levels for our modules
    logging.getLogger("agent_framework_ag_ui").setLevel(logging.INFO)
    logging.getLogger("agent_framework").setLevel(logging.INFO)

    logger = logging.getLogger(__name__)
    logger.info(f"AG-UI Examples Server starting... Logs writing to: {log_file}")

app = FastAPI(title="Agent Framework AG-UI Example Server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Load the examples .env (OPENAI_API_KEY etc.) before constructing any chat client.
# python-dotenv is an examples-only convenience; if it isn't installed, fall back to
# whatever the shell already exported. override=True so a stale/empty exported
# OPENAI_API_KEY doesn't shadow the .env value.
try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None  # type: ignore[assignment]
if load_dotenv is not None:
    load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=True)

# Create a shared chat client for all agents
# You can use different chat clients for different agents if needed
# Set CHAT_CLIENT=anthropic for Anthropic, CHAT_CLIENT=openai (or just an
# OPENAI_API_KEY) for OpenAI Chat-Completions; otherwise defaults to Azure OpenAI.
_chat_client_kind = os.getenv("CHAT_CLIENT", "").lower()


def _default_shared_client() -> SupportsChatGetResponse[ChatOptions]:
    if AnthropicClient is not None and _chat_client_kind == "anthropic":
        return cast(SupportsChatGetResponse[ChatOptions], AnthropicClient())
    if _chat_client_kind == "openai" or (not _chat_client_kind and os.getenv("OPENAI_API_KEY")):
        return cast(
            SupportsChatGetResponse[ChatOptions],
            OpenAIChatCompletionClient(model=os.getenv("OPENAI_CHAT_MODEL_ID", "gpt-4o")),
        )
    return cast(SupportsChatGetResponse[ChatOptions], AzureOpenAIChatClient())


client: SupportsChatGetResponse[ChatOptions] = _default_shared_client()

# Agentic Chat - basic chat agent
add_agent_framework_fastapi_endpoint(
    app=app,
    agent=simple_agent(client),
    path="/agentic_chat",
)

# Backend Tool Rendering - agent with tools
add_agent_framework_fastapi_endpoint(
    app=app,
    agent=weather_agent(client),
    path="/backend_tool_rendering",
)

# Shared State - recipe agent with structured output
add_agent_framework_fastapi_endpoint(
    app=app,
    agent=recipe_agent(client),
    path="/shared_state",
)

# Predictive State Updates - document writer with predictive state
add_agent_framework_fastapi_endpoint(
    app=app,
    agent=document_writer_agent(client),
    path="/predictive_state_updates",
)

# Human in the Loop - human-in-the-loop agent with step customization
add_agent_framework_fastapi_endpoint(
    app=app,
    agent=human_in_the_loop_agent(client),
    path="/human_in_the_loop",
    state_schema={"steps": {"type": "array"}},
    predict_state_config={"steps": {"tool": "generate_task_steps", "tool_argument": "steps"}},
)

# Agentic Generative UI - task steps agent with streaming state updates
add_agent_framework_fastapi_endpoint(
    app=app,
    agent=task_steps_agent_wrapped(client),
    path="/agentic_generative_ui",
)

# Tool-based Generative UI - UI generator with frontend-rendered tools
add_agent_framework_fastapi_endpoint(
    app=app,
    agent=ui_generator_agent(client),
    path="/tool_based_generative_ui",
)

# Subgraphs - deterministic travel planner with interrupt-driven selections
add_agent_framework_fastapi_endpoint(
    app=app,
    agent=subgraphs_agent(),
    path="/subgraphs",
)

# Deterministic Tool-Driven State - tool returns state_update() to push snapshot
# from actual tool output (see issue #3167).
add_agent_framework_fastapi_endpoint(
    app=app,
    agent=weather_state_agent(client),
    path="/deterministic_state",
)

# --- A2UI (agent-generated UI) demos ---------------------------------------
# A2UI surface streaming needs a Chat-Completions client: it emits render_a2ui
# argument deltas per chunk (progressive paint) and replays the balancing tool
# result cleanly, where the Responses/Azure path buffers. Use a dedicated
# OpenAIChatCompletionClient for these endpoints when OPENAI_API_KEY is set; otherwise fall
# back to the shared client with a warning (streaming may not paint incrementally).
if os.getenv("OPENAI_API_KEY"):
    a2ui_client: SupportsChatGetResponse[ChatOptions] = cast(
        SupportsChatGetResponse[ChatOptions],
        OpenAIChatCompletionClient(model=os.getenv("OPENAI_CHAT_MODEL_ID", "gpt-4o")),
    )
else:
    logging.getLogger(__name__).warning(
        "OPENAI_API_KEY not set; A2UI demos fall back to the shared client and may not "
        "stream render_a2ui deltas incrementally. Set it in the examples .env."
    )
    a2ui_client = client

# Dynamic schema — subagent generates a surface against the dojo catalog.
add_agent_framework_fastapi_endpoint(
    app=app,
    agent=a2ui_dynamic_schema_agent(a2ui_client),
    path="/a2ui_dynamic_schema",
    a2ui_config=A2UI_DEMO_CONFIG,
)

# Advanced — ZERO-CONFIG: no backend catalog/guide; catalog arrives on forwardedProps.
add_agent_framework_fastapi_endpoint(
    app=app,
    agent=a2ui_advanced_agent(a2ui_client),
    path="/a2ui_advanced",
)

# Recovery — validate->retry loop; structural validation drives regeneration.
add_agent_framework_fastapi_endpoint(
    app=app,
    agent=a2ui_recovery_agent(a2ui_client),
    path="/a2ui_recovery",
    a2ui_config=A2UI_DEMO_CONFIG,
)

# Fixed schema — direct backend tool returns a pre-authored a2ui_operations envelope.
add_agent_framework_fastapi_endpoint(
    app=app,
    agent=a2ui_fixed_schema_agent(a2ui_client),
    path="/a2ui_fixed_schema",
)


def main():
    """Run the server."""
    port = int(os.getenv("PORT", "8887"))
    host = os.getenv("HOST", "127.0.0.1")

    print(f"\nAG-UI Examples Server starting on http://{host}:{port}")
    print("Set ENABLE_DEBUG_LOGGING=1 for detailed request logging\n")

    # Use log_config=None to prevent uvicorn from reconfiguring logging
    # This preserves our file + console logging setup
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_config=None,
    )


if __name__ == "__main__":
    main()
