# Copyright (c) Microsoft. All rights reserved.

"""Example FastAPI server with AG-UI endpoints."""

import logging
import os

import uvicorn
from agent_framework.azure import AzureOpenAIChatClient
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from agent_framework_ag_ui import add_agent_framework_fastapi_endpoint

from ..agents.document_writer_agent import document_writer_agent
from ..agents.human_in_the_loop_agent import human_in_the_loop_agent
from ..agents.recipe_agent import recipe_agent
from ..agents.simple_agent import simple_agent
from ..agents.task_steps_agent import task_steps_agent_wrapped
from ..agents.ui_generator_agent import ui_generator_agent
from ..agents.weather_agent import weather_agent

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

# Create a shared chat client for all agents
# You can use different chat clients for different agents if needed
chat_client = AzureOpenAIChatClient()

# Agentic Chat - basic chat agent
add_agent_framework_fastapi_endpoint(
    app=app,
    agent=simple_agent(chat_client),
    path="/agentic_chat",
)

# Backend Tool Rendering - agent with tools
add_agent_framework_fastapi_endpoint(
    app=app,
    agent=weather_agent(chat_client),
    path="/backend_tool_rendering",
)

# Shared State - recipe agent with structured output
add_agent_framework_fastapi_endpoint(
    app=app,
    agent=recipe_agent(chat_client),
    path="/shared_state",
)

# Predictive State Updates - document writer with predictive state
add_agent_framework_fastapi_endpoint(
    app=app,
    agent=document_writer_agent(chat_client),
    path="/predictive_state_updates",
)

# Human in the Loop - human-in-the-loop agent with step customization
add_agent_framework_fastapi_endpoint(
    app=app,
    agent=human_in_the_loop_agent(chat_client),
    path="/human_in_the_loop",
    state_schema={"steps": {"type": "array"}},
    predict_state_config={"steps": {"tool": "generate_task_steps", "tool_argument": "steps"}},
)

# Agentic Generative UI - task steps agent with streaming state updates
add_agent_framework_fastapi_endpoint(
    app=app,
    agent=task_steps_agent_wrapped(chat_client),  # type: ignore[arg-type]
    path="/agentic_generative_ui",
)

# Tool-based Generative UI - UI generator with frontend-rendered tools
add_agent_framework_fastapi_endpoint(
    app=app,
    agent=ui_generator_agent(chat_client),
    path="/tool_based_generative_ui",
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
