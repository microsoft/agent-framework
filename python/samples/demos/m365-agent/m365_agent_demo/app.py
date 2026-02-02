# Copyright (c) Microsoft. All rights reserved.
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "microsoft-agents-hosting-aiohttp",
#   "microsoft-agents-hosting-core",
#   "microsoft-agents-authentication-msal",
#   "microsoft-agents-activity",
#   "agent-framework-core",
#   "aiohttp"
# ]
# ///

import os
from dataclasses import dataclass
from random import randint
from typing import Annotated

from agent_framework import ChatAgent
from agent_framework import tool
from agent_framework.openai import OpenAIChatClient
from aiohttp import web
from aiohttp.web_middlewares import middleware
from microsoft_agents.activity import load_configuration_from_env
from microsoft_agents.authentication.msal import MsalConnectionManager
from microsoft_agents.hosting.aiohttp import CloudAdapter, start_agent_process
from microsoft_agents.hosting.core import (
    AgentApplication,
    AuthenticationConstants,
    Authorization,
    ClaimsIdentity,
    MemoryStorage,
    TurnContext,
    TurnState,
)
from pydantic import Field

"""
Demo application using Microsoft Agent 365 SDK.

This sample demonstrates how to build an AI agent using the Agent Framework,
integrating with Microsoft 365 authentication and hosting components.

The agent provides a simple weather tool and can be run in either anonymous mode
(no authentication required) or authenticated mode using MSAL and Azure AD.

Key features:
- Loads configuration from environment variables.
- Demonstrates agent creation and tool registration.
- Supports both anonymous and authenticated scenarios.
- Uses aiohttp for web hosting.

To run, set the appropriate environment variables (check .env.example file) for authentication or use
anonymous mode for local testing.
"""


@dataclass
class AppConfig:
    use_anonymous_mode: bool
    port: int
    agents_sdk_config: dict


def load_app_config() -> AppConfig:
    """Load application configuration from environment variables.

    Returns:
        AppConfig: Consolidated configuration including anonymous mode flag, port, and SDK config.
    """
    agents_sdk_config = load_configuration_from_env(os.environ)
    use_anonymous_mode = os.environ.get("USE_ANONYMOUS_MODE", "true").lower() == "true"
    port_str = os.getenv("PORT", "3978")
    try:
        port = int(port_str)
    except ValueError:
        port = 3978
    return AppConfig(use_anonymous_mode=use_anonymous_mode, port=port, agents_sdk_config=agents_sdk_config)

# NOTE: approval_mode="never_require" is for sample brevity. Use "always_require" in production; see samples/getting_started/tools/function_tool_with_approval.py and samples/getting_started/tools/function_tool_with_approval_and_threads.py.
@tool(approval_mode="never_require")
def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
) -> str:
    """Generate a mock weather report for the provided location.

    Args:
        location: The geographic location name.
    Returns:
        str: Human-readable weather summary.
    """
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    return f"The weather in {location} is {conditions[randint(0, 3)]} with a high of {randint(10, 30)}°C."


def build_agent() -> ChatAgent:
    """Create and return the chat agent instance with weather tool registered."""
    return OpenAIChatClient().as_agent(
        name="WeatherAgent", instructions="You are a helpful weather agent.", tools=get_weather
    )


def build_connection_manager(config: AppConfig) -> MsalConnectionManager | None:
    """Build the connection manager unless running in anonymous mode.

    Args:
        config: Application configuration.
    Returns:
        MsalConnectionManager | None: Connection manager when authenticated mode is enabled.
    """
    if config.use_anonymous_mode:
        return None
    return MsalConnectionManager(**config.agents_sdk_config)


def build_adapter(connection_manager: MsalConnectionManager | None) -> CloudAdapter:
    """Instantiate the CloudAdapter with the optional connection manager."""
    return CloudAdapter(connection_manager=connection_manager)


def build_authorization(
    storage: MemoryStorage, connection_manager: MsalConnectionManager | None, config: AppConfig
) -> Authorization | None:
    """Create Authorization component if not in anonymous mode.

    Args:
        storage: State storage backend.
        connection_manager: Optional connection manager.
        config: Application configuration.
    Returns:
        Authorization | None: Authorization component when enabled.
    """
    if config.use_anonymous_mode:
        return None
    return Authorization(storage, connection_manager, **config.agents_sdk_config)


def build_agent_application(
    storage: MemoryStorage,
    adapter: CloudAdapter,
    authorization: Authorization | None,
    config: AppConfig,
) -> AgentApplication[TurnState]:
    """Compose and return the AgentApplication instance.

    Args:
        storage: Storage implementation.
        adapter: CloudAdapter handling requests.
        authorization: Optional authorization component.
        config: App configuration.
    Returns:
        AgentApplication[TurnState]: Configured agent application.
    """
    return AgentApplication[TurnState](
        storage=storage, adapter=adapter, authorization=authorization, **config.agents_sdk_config
    )


def build_anonymous_claims_middleware(use_anonymous_mode: bool):
    """Return a middleware that injects anonymous claims when enabled.

    Args:
        use_anonymous_mode: Whether to apply anonymous identity for each request.
    Returns:
        Callable: Aiohttp middleware function.
    """

    @middleware
    async def anonymous_claims_middleware(request, handler):
        """Inject claims for anonymous users if anonymous mode is active."""
        if use_anonymous_mode:
            request["claims_identity"] = ClaimsIdentity(
                {
                    AuthenticationConstants.AUDIENCE_CLAIM: "anonymous",
                    AuthenticationConstants.APP_ID_CLAIM: "anonymous-app",
                },
                False,
                "Anonymous",
            )
        return await handler(request)

    return anonymous_claims_middleware


def create_app(config: AppConfig) -> web.Application:
    """Create and configure the aiohttp web application.

    Args:
        config: Loaded application configuration.
    Returns:
        web.Application: Fully initialized web application.
    """
    middleware_fn = build_anonymous_claims_middleware(config.use_anonymous_mode)
    app = web.Application(middleware=[middleware_fn])

    storage = MemoryStorage()
    agent = build_agent()
    connection_manager = build_connection_manager(config)
    adapter = build_adapter(connection_manager)
    authorization = build_authorization(storage, connection_manager, config)
    agent_app = build_agent_application(storage, adapter, authorization, config)

    @agent_app.activity("message")
    async def on_message(context: TurnContext, _: TurnState):
        user_message = context.activity.text or ""
        if not user_message.strip():
            return

        response = await agent.run(user_message)
        response_text = response.text

        await context.send_activity(response_text)

    async def health(request: web.Request) -> web.Response:
        return web.json_response({"status": "ok"})

    async def entry_point(req: web.Request) -> web.Response:
        return await start_agent_process(req, req.app["agent_app"], req.app["adapter"])

    app.add_routes([
        web.get("/api/health", health),
        web.get("/api/messages", lambda _: web.Response(status=200)),
        web.post("/api/messages", entry_point),
    ])

    app["agent_app"] = agent_app
    app["adapter"] = adapter

    return app


def main() -> None:
    """Entry point: load configuration, build app, and start server."""
    config = load_app_config()
    app = create_app(config)
    web.run_app(app, host="localhost", port=config.port)


if __name__ == "__main__":
    main()
