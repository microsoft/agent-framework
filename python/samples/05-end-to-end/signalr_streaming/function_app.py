# Copyright (c) Microsoft. All rights reserved.

"""Stream agent responses to clients in real time via Azure SignalR Service.

This sample demonstrates how to:
- Host an agent built with Agent Framework in an Azure Functions app
- Use Azure OpenAI (via AzureOpenAIChatClient) to power a travel planning agent
- Stream incremental agent responses to clients over Azure SignalR Service
- Implement user isolation using SignalR user-targeted messaging so each client only receives its own messages

Components used in this sample:
- AgentFunctionApp to expose HTTP endpoints via the Durable Functions extension.
- AzureOpenAIChatClient to call the Azure OpenAI chat deployment.
- AgentResponseCallbackProtocol to forward streaming updates to SignalR.
- A lightweight REST client (SignalRServiceClient) to call the SignalR Service REST API.
- Mock tool functions (get_weather_forecast, get_local_events) for the travel agent.

Prerequisites:
- An Azure SignalR Service instance (Serverless mode). There is no local emulator.
- An Azure OpenAI resource with a chat model deployment.
- Azure Functions Core Tools and Azurite for local development.
- Logged in via ``az login`` for AzureCliCredential.
- Environment variables set in local.settings.json (see local.settings.json.template).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import time
import uuid
from typing import Any

import aiohttp
import azure.functions as func
from agent_framework import AgentResponseUpdate
from agent_framework.azure import (
    AgentCallbackContext,
    AgentFunctionApp,
    AgentResponseCallbackProtocol,
    AzureOpenAIChatClient,
)
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

from tools import get_local_events, get_weather_forecast

# Load environment variables from .env file
load_dotenv()

# Configuration
SIGNALR_CONNECTION_STRING = os.environ.get("AzureSignalRConnectionString", "")
SIGNALR_HUB_NAME = os.environ.get("SIGNALR_HUB_NAME", "travel")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


# ---------------------------------------------------------------------------
# 1. SignalR Service REST client
# ---------------------------------------------------------------------------


class SignalRServiceClient:
    """Lightweight client for Azure SignalR Service REST API."""

    def __init__(self, connection_string: str, hub_name: str) -> None:
        parts = {
            key: value
            for key, value in (segment.split("=", 1) for segment in connection_string.split(";") if segment)
        }

        self._endpoint = parts.get("Endpoint", "").rstrip("/") + "/"
        self._access_key = parts.get("AccessKey")
        self._hub_name = hub_name

        if not self._endpoint or not self._access_key:
            raise ValueError("AzureSignalRConnectionString must include Endpoint and AccessKey.")

    @staticmethod
    def _encode_segment(data: dict) -> bytes:
        return base64.urlsafe_b64encode(json.dumps(data, separators=(",", ":")).encode("utf-8")).rstrip(b"=")

    def _generate_token(
        self, audience: str, expires_in_seconds: int = 3600, *, user_id: str | None = None
    ) -> str:
        header = {"alg": "HS256", "typ": "JWT"}
        payload: dict[str, Any] = {
            "aud": audience,
            "exp": int(time.time()) + expires_in_seconds,
        }
        if user_id:
            payload["nameid"] = user_id

        signing_input = b".".join([self._encode_segment(header), self._encode_segment(payload)])
        signature = hmac.new(
            self._access_key.encode("utf-8"),  # type: ignore[union-attr]
            signing_input,
            hashlib.sha256,
        ).digest()
        token = b".".join([signing_input, base64.urlsafe_b64encode(signature).rstrip(b"=")])
        return token.decode("utf-8")

    async def send(
        self,
        *,
        target: str,
        arguments: list,
        group: str | None = None,
        user_id: str | None = None,
    ) -> None:
        """Send a message to SignalR clients via the REST API."""
        url_path = f"/api/v1/hubs/{self._hub_name}"
        if group:
            url_path += f"/groups/{group}"
        elif user_id:
            url_path += f"/users/{user_id}"

        base_endpoint = self._endpoint.rstrip("/")
        url = f"{base_endpoint}{url_path}"
        token = self._generate_token(url)

        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json={"target": target, "arguments": arguments},
            ) as response:
                if response.status >= 300:
                    details = await response.text()
                    raise RuntimeError(f"SignalR send failed ({response.status}): {details}")




# ---------------------------------------------------------------------------
# 2. Callback that pushes streaming updates to SignalR
# ---------------------------------------------------------------------------


# Thread-to-user mapping for routing SignalR messages to the correct user.
# In production, use a shared store (e.g., Redis) for multi-instance deployments.
_thread_user_map: dict[str, str] = {}


class SignalRCallback(AgentResponseCallbackProtocol):
    """Callback that pushes streaming updates to the correct SignalR user."""

    def __init__(
        self,
        client: SignalRServiceClient,
        thread_user_map: dict[str, str],
        *,
        message_target: str = "agentMessage",
        done_target: str = "agentDone",
    ) -> None:
        self._client = client
        self._thread_user_map = thread_user_map
        self._message_target = message_target
        self._done_target = done_target
        self._logger = logging.getLogger("durableagent.samples.signalr_streaming")

    def _resolve_user(self, thread_id: str | None) -> str | None:
        """Look up the user_id for a given thread_id."""
        if not thread_id:
            return None
        return self._thread_user_map.get(thread_id)

    async def on_streaming_response_update(
        self,
        update: AgentResponseUpdate,
        context: AgentCallbackContext,
    ) -> None:
        text = update.text
        if not text:
            return

        target_user = self._resolve_user(context.thread_id)
        if not target_user:
            self._logger.warning("No user_id mapped for thread %s", context.thread_id)
            return

        payload = {
            "conversationId": context.thread_id,
            "correlationId": context.correlation_id,
            "text": text,
        }

        try:
            await self._client.send(
                target=self._message_target,
                arguments=[payload],
                user_id=target_user,
            )
        except Exception as ex:
            if "404" not in str(ex):
                self._logger.error("SignalR send failed: %s", ex)

    async def on_agent_response(self, response: Any, context: AgentCallbackContext) -> None:
        target_user = self._resolve_user(context.thread_id)
        if not target_user:
            return

        payload = {
            "conversationId": context.thread_id,
            "correlationId": context.correlation_id,
            "status": "completed",
        }

        try:
            await self._client.send(
                target=self._done_target,
                arguments=[payload],
                user_id=target_user,
            )
        except Exception as ex:
            if "404" not in str(ex):
                self._logger.error("SignalR send failed: %s", ex)


# ---------------------------------------------------------------------------
# 3. Create SignalR client and callback instances
# ---------------------------------------------------------------------------

signalr_client = SignalRServiceClient(
    connection_string=SIGNALR_CONNECTION_STRING,
    hub_name=SIGNALR_HUB_NAME,
)
signalr_callback = SignalRCallback(client=signalr_client, thread_user_map=_thread_user_map)


# ---------------------------------------------------------------------------
# 4. Create the travel planner agent
# ---------------------------------------------------------------------------


def _create_travel_agent() -> Any:
    """Create the TravelPlanner agent with tools."""
    return AzureOpenAIChatClient(credential=AzureCliCredential()).as_agent(
        name="TravelPlanner",
        instructions=(
            "You are an expert travel planner who creates detailed, personalized travel itineraries.\n"
            "When asked to plan a trip, you should:\n"
            "1. Create a comprehensive day-by-day itinerary\n"
            "2. Include specific recommendations for activities, restaurants, and attractions\n"
            "3. Provide practical tips for each destination\n"
            "4. Consider weather and local events when making recommendations\n"
            "5. Include estimated times and logistics between activities\n\n"
            "Always use the available tools to get current weather forecasts and local events\n"
            "for the destination to make your recommendations more relevant and timely.\n\n"
            "Format your response with clear headings for each day and include emoji icons\n"
            "to make the itinerary easy to scan and visually appealing."
        ),
        tools=[get_weather_forecast, get_local_events],
    )


# ---------------------------------------------------------------------------
# 5. Register with AgentFunctionApp
# ---------------------------------------------------------------------------

app = AgentFunctionApp(
    agents=[_create_travel_agent()],
    enable_health_check=True,
    default_callback=signalr_callback,
    max_poll_retries=100,
)


# ---------------------------------------------------------------------------
# 6. Custom HTTP endpoints
# ---------------------------------------------------------------------------


@app.function_name("negotiate")
@app.route(route="agent/negotiate", methods=["POST", "GET"])
def negotiate(req: func.HttpRequest) -> func.HttpResponse:
    """Provide SignalR connection info with the user identity embedded in the token.

    The client must pass an ``x-user-id`` header so that SignalR can route
    messages to the correct user via the ``nameid`` JWT claim.
    """
    try:
        user_id = req.headers.get("x-user-id", "")
        base_url = signalr_client._endpoint.rstrip("/")
        client_url = f"{base_url}/client/?hub={SIGNALR_HUB_NAME}"
        access_token = signalr_client._generate_token(client_url, user_id=user_id or None)

        body = json.dumps({"url": client_url, "accessToken": access_token})
        return func.HttpResponse(body=body, mimetype="application/json")
    except Exception as ex:
        logging.error("Failed to negotiate SignalR connection: %s", ex)
        return func.HttpResponse(
            json.dumps({"error": str(ex)}),
            status_code=500,
            mimetype="application/json",
        )


@app.function_name("createThread")
@app.route(route="agent/create-thread", methods=["POST"])
def create_thread(req: func.HttpRequest) -> func.HttpResponse:
    """Create a new thread_id and register the user mapping.

    The client must pass an ``x-user-id`` header so that the callback knows
    which SignalR user to target when streaming responses for this thread.
    """
    user_id = req.headers.get("x-user-id", "")
    thread_id = uuid.uuid4().hex
    if user_id:
        _thread_user_map[thread_id] = user_id
    return func.HttpResponse(
        json.dumps({"thread_id": thread_id}),
        mimetype="application/json",
    )


@app.route(route="index", methods=["GET"])
def index(req: func.HttpRequest) -> func.HttpResponse:
    """Serve the web interface."""
    html_path = os.path.join(os.path.dirname(__file__), "content", "index.html")
    try:
        with open(html_path) as f:
            return func.HttpResponse(f.read(), mimetype="text/html")
    except FileNotFoundError:
        logging.error("index.html not found at path: %s", html_path)
        return func.HttpResponse(
            json.dumps({"error": "index.html not found"}),
            status_code=404,
            mimetype="application/json",
        )
    except OSError as ex:
        logging.error("Failed to read index.html at path %s: %s", html_path, ex)
        return func.HttpResponse(
            json.dumps({"error": "Failed to load index page"}),
            status_code=500,
            mimetype="application/json",
        )


"""
Sample output:

1. Start the Functions host: func start
2. Open http://localhost:7071/api/index in a browser
3. The page connects to Azure SignalR Service and displays a chat interface
4. Type "Plan a 3-day trip to Singapore" and press Send
5. The agent streams its response in real time through SignalR

User:> Plan a 3-day trip to Singapore
Agent:> 🌴 **3-Day Singapore Itinerary** ...
       (response streamed chunk-by-chunk via SignalR)
"""
