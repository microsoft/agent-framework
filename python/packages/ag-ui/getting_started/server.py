# Copyright (c) Microsoft. All rights reserved.

"""AG-UI server example with server-side tools."""

import logging
import os

from agent_framework import ChatAgent, ai_function
from agent_framework.ag_ui import add_agent_framework_fastapi_endpoint
from agent_framework.azure import AzureOpenAIChatClient
from dotenv import load_dotenv
from fastapi import FastAPI

load_dotenv()

# Enable debug logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# Read required configuration
endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT")
deployment_name = os.environ.get("AZURE_OPENAI_CHAT_DEPLOYMENT_NAME")

if not endpoint:
    raise ValueError("AZURE_OPENAI_ENDPOINT environment variable is required")
if not deployment_name:
    raise ValueError("AZURE_OPENAI_CHAT_DEPLOYMENT_NAME environment variable is required")


# Server-side tool (executes on server)
@ai_function(description="Get the time zone for a location.")
def get_time_zone(location: str) -> str:
    """Get the time zone for a location.

    Args:
        location: The city or location name
    """
    print(f"[SERVER] get_time_zone tool called with location: {location}")
    timezone_data = {
        "seattle": "Pacific Time (UTC-8)",
        "san francisco": "Pacific Time (UTC-8)",
        "new york": "Eastern Time (UTC-5)",
        "london": "Greenwich Mean Time (UTC+0)",
    }
    result = timezone_data.get(location.lower(), f"Time zone data not available for {location}")
    print(f"[SERVER] get_time_zone returning: {result}")
    return result


# Create the AI agent with ONLY server-side tools
# IMPORTANT: Do NOT include tools that the client provides!
# In this example:
# - get_time_zone: SERVER-ONLY tool (only server has this)
# - get_weather: CLIENT-ONLY tool (client provides this, server should NOT include it)
# The client will send get_weather tool metadata so the LLM knows about it,
# and @use_function_invocation on AGUIChatClient will execute it client-side.
# This matches the .NET AG-UI hybrid execution pattern.
agent = ChatAgent(
    name="AGUIAssistant",
    instructions="You are a helpful assistant. Use get_weather for weather and get_time_zone for time zones.",
    chat_client=AzureOpenAIChatClient(
        endpoint=endpoint,
        deployment_name=deployment_name,
    ),
    tools=[get_time_zone],  # ONLY server-side tools
)

# Create FastAPI app
app = FastAPI(title="AG-UI Server")

# Register the AG-UI endpoint
add_agent_framework_fastapi_endpoint(app, agent, "/")

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=5100, log_level="debug", access_log=True)
