# Copyright (c) Microsoft. All rights reserved.

"""AG-UI server example with server-side tools."""

from __future__ import annotations

import logging
import os

from agent_framework import Agent, tool
from agent_framework.ag_ui import add_agent_framework_fastapi_endpoint
from agent_framework.openai import OpenAIChatCompletionClient
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Security
from fastapi.security import APIKeyHeader

load_dotenv()

# Enable debug logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# Read required configuration
endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT")
model = os.environ.get("AZURE_OPENAI_MODEL")

if not endpoint:
    raise ValueError("AZURE_OPENAI_ENDPOINT environment variable is required")
if not model:
    raise ValueError("AZURE_OPENAI_MODEL environment variable is required")


# ============================================================================
# AUTHENTICATION EXAMPLE
# ============================================================================
# This demonstrates how to secure the AG-UI endpoint with API key authentication.
# In production, you should use a more robust authentication mechanism such as:
# - OAuth 2.0 / OpenID Connect
# - JWT tokens with proper validation
# - Azure AD / Entra ID integration
# - Your organization's identity provider
#
# The API key should be stored securely (e.g., Azure Key Vault, environment variables)
# and rotated regularly.
# ============================================================================

# API key header configuration
API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)

# Get the expected API key from environment variable
# In production, use a secrets manager like Azure Key Vault
EXPECTED_API_KEY = os.environ.get("AG_UI_API_KEY")


async def resolve_authorization_scope(api_key: str | None = Security(API_KEY_HEADER)) -> str:
    """Verify the API key and return its stable authorization scope.

    Args:
        api_key: The API key from the X-API-Key header

    Returns:
        The authorization scope shared by requests using the configured API key.

    Raises:
        HTTPException: If the API key is missing or invalid
    """
    if not EXPECTED_API_KEY:
        # If no API key is configured, log a warning but allow the request
        # This maintains backward compatibility but warns about the security risk
        logger.warning(
            "AG_UI_API_KEY environment variable not set. "
            "The endpoint is accessible without authentication. "
            "Set AG_UI_API_KEY to enable API key authentication."
        )
        return "local-single-user"

    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="Missing API key. Provide X-API-Key header.",
        )

    if api_key != EXPECTED_API_KEY:
        raise HTTPException(
            status_code=403,
            detail="Invalid API key.",
        )
    return "configured-api-key"


# Server-side tool (executes on server)
@tool(description="Get the time zone for a location.")
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
# and the function invocation mixin on AGUIChatClient will execute it client-side.
# This matches the .NET AG-UI hybrid execution pattern.
agent = Agent(
    name="AGUIAssistant",
    instructions="You are a helpful assistant. Use get_weather for weather and get_time_zone for time zones.",
    client=OpenAIChatCompletionClient(
        azure_endpoint=endpoint,
        model=model,
    ),
    tools=[get_time_zone],  # ONLY server-side tools
)

# Create FastAPI app
app = FastAPI(title="AG-UI Server")

# Register the AG-UI endpoint with authentication-backed authorization scoping.
add_agent_framework_fastapi_endpoint(
    app,
    agent,
    "/",
    authorization_scope_resolver=resolve_authorization_scope,
)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=5100, log_level="debug", access_log=True)
