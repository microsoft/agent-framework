# Copyright (c) Microsoft. All rights reserved.

"""Azure Functions sample: stream agent responses to clients via Azure SignalR.

This sample demonstrates how to:
- Host an agent built with the `agent_framework` in an Azure Functions app
- Use Azure OpenAI (via `AzureOpenAIChatClient`) to power a travel planning agent
- Stream incremental agent responses and tool calls to clients over Azure SignalR Service
- Integrate a lightweight REST client (`SignalRServiceClient`) with the Functions runtime

Components used:
- Azure Functions (HTTP-triggered function with `AgentFunctionApp`)
- Azure OpenAI Chat model accessed via `AzureOpenAIChatClient`
- Azure SignalR Service accessed via a custom `SignalRServiceClient`
- `AgentResponseCallbackProtocol` implementation (`SignalRCallback`) to forward updates
- Tool functions imported from `tools` (e.g., `get_local_events`, `get_weather_forecast`)

Prerequisites:
- An Azure subscription with:
  - An Azure SignalR Service instance
  - An Azure OpenAI resource and chat model deployment
- Azure Functions Core Tools or an Azure Functions host to run this app
- Authentication configured for `AzureCliCredential` (e.g., `az login`)
- Environment variables:
  - `AzureSignalRConnectionString`: connection string for the SignalR resource
  - `SIGNALR_HUB_NAME`: name of the SignalR hub (defaults to "travel" if not set)
  - Any additional Azure OpenAI configuration required by `AzureOpenAIChatClient`
"""

import base64
import hashlib
import hmac
import json
import logging
import os
import time
import uuid

import aiohttp
from agent_framework import AgentRunResponseUpdate
import azure.functions as func
from agent_framework.azure import (
    AgentCallbackContext,
    AgentFunctionApp,
    AgentResponseCallbackProtocol,
    AzureOpenAIChatClient,
)
from azure.identity import AzureCliCredential

from tools import get_local_events, get_weather_forecast

# Configuration
SIGNALR_CONNECTION_STRING = os.environ.get("AzureSignalRConnectionString", "")
SIGNALR_HUB_NAME = os.environ.get("SIGNALR_HUB_NAME", "travel")

# Ensure local console logging is enabled when running the Functions host locally.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


class SignalRServiceClient:
    """Lightweight client for Azure SignalR Service REST API."""

    def __init__(self, connection_string: str, hub_name: str) -> None:
        parts = {
            key: value
            for key, value in (
                segment.split("=", 1)
                for segment in connection_string.split(";")
                if segment
            )
        }

        self._endpoint = parts.get("Endpoint", "").rstrip("/") + "/"
        self._access_key = parts.get("AccessKey")
        self._hub_name = hub_name

        if not self._endpoint or not self._access_key:
            raise ValueError(
                "AzureSignalRConnectionString must include Endpoint and AccessKey."
            )

    @staticmethod
    def _encode_segment(data: dict) -> bytes:
        return base64.urlsafe_b64encode(
            json.dumps(data, separators=(",", ":")).encode("utf-8")
        ).rstrip(b"=")

    def _generate_token(self, audience: str, expires_in_seconds: int = 3600) -> str:
        header = {"alg": "HS256", "typ": "JWT"}
        payload = {
            "aud": audience,
            "exp": int(time.time()) + expires_in_seconds,
        }

        signing_input = b".".join(
            [self._encode_segment(header), self._encode_segment(payload)]
        )
        # Azure SignalR expects HMAC signed with the raw access key (UTF-8)
        signature = hmac.new(
            self._access_key.encode("utf-8"), signing_input, hashlib.sha256  # type: ignore
        ).digest()
        token = b".".join(
            [signing_input, base64.urlsafe_b64encode(signature).rstrip(b"=")]
        )
        return token.decode("utf-8")

    async def send(  # noqa: D401 - simple REST send helper
        self,
        *,
        target: str,
        arguments: list,
        group: str | None = None,
        user_id: str | None = None,
    ) -> None:
        # Build the API path
        url_path = f"/api/v1/hubs/{self._hub_name}"
        if group:
            url_path += f"/groups/{group}"
        elif user_id:
            url_path += f"/users/{user_id}"

        # Construct full URL (no /:send suffix - just POST to the path)
        base_endpoint = self._endpoint.rstrip("/")
        url = f"{base_endpoint}{url_path}"

        # Token audience should match the URL path
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
                    raise RuntimeError(
                        f"SignalR send failed ({response.status}): {details}"
                    )

    async def add_connection_to_group(self, group: str, connection_id: str) -> None:
        """Add a connection to a group."""
        base_endpoint = self._endpoint.rstrip("/")
        url = f"{base_endpoint}/api/v1/hubs/{self._hub_name}/groups/{group}/connections/{connection_id}"
        token = self._generate_token(url)

        async with aiohttp.ClientSession() as session:
            async with session.put(
                url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
            ) as response:
                if response.status >= 300:
                    details = await response.text()
                    raise RuntimeError(
                        f"SignalR add to group failed ({response.status}): {details}"
                    )


class SignalRCallback(AgentResponseCallbackProtocol):
    """Callback that pushes streaming updates directly to SignalR clients."""

    def __init__(
        self,
        client: SignalRServiceClient,
        *,
        message_target: str = "agentMessage",
        done_target: str = "agentDone",
    ) -> None:
        self._client = client
        self._message_target = message_target
        self._done_target = done_target
        self._logger = logging.getLogger("durableagent.samples.signalr_streaming")

    async def on_streaming_response_update(
        self,
        update: AgentRunResponseUpdate,
        context: AgentCallbackContext,
    ) -> None:
        text = update.text
        if not text:
            return

        payload = {
            "conversationId": context.thread_id,
            "correlationId": context.correlation_id,
            "text": text,
        }

        try:
            # Send to the specific conversation group for user isolation
            await self._client.send(
                target=self._message_target,
                arguments=[payload],
                group=context.thread_id,
            )
        except Exception as ex:
            if "404" not in str(ex):
                self._logger.error("SignalR send failed: %s", ex)

    async def on_agent_response(self, response, context: AgentCallbackContext) -> None:
        payload = {
            "conversationId": context.thread_id,
            "correlationId": context.correlation_id,
            "status": "completed",
        }

        try:
            # Send to the specific conversation group for user isolation
            await self._client.send(
                target=self._done_target,
                arguments=[payload],
                group=context.thread_id,
            )
        except Exception as ex:
            if "404" not in str(ex):
                self._logger.error("SignalR send failed: %s", ex)


signalr_client = SignalRServiceClient(
    connection_string=SIGNALR_CONNECTION_STRING,
    hub_name=SIGNALR_HUB_NAME,
)
signalr_callback = SignalRCallback(client=signalr_client)


# Create the travel planner agent
def create_travel_agent():
    """Create the TravelPlanner agent with tools."""
    return AzureOpenAIChatClient(credential=AzureCliCredential()).create_agent(
        name="TravelPlanner",
        instructions="""You are an expert travel planner who creates detailed, personalized travel itineraries.
When asked to plan a trip, you should:
1. Create a comprehensive day-by-day itinerary
2. Include specific recommendations for activities, restaurants, and attractions
3. Provide practical tips for each destination
4. Consider weather and local events when making recommendations
5. Include estimated times and logistics between activities

Always use the available tools to get current weather forecasts and local events
for the destination to make your recommendations more relevant and timely.

Format your response with clear headings for each day and include emoji icons
to make the itinerary easy to scan and visually appealing.""",
        tools=[get_weather_forecast, get_local_events],
    )


# Create AgentFunctionApp with the SignalR callback
app = AgentFunctionApp(
    agents=[create_travel_agent()],
    enable_health_check=True,
    default_callback=signalr_callback,
    max_poll_retries=100,  # Increase for longer-running agents
)

def _get_signalr_endpoint_from_connection_string(connection_string: str) -> str:
    """Extract the SignalR service endpoint from a connection string."""
    for part in connection_string.split(";"):
        if part.startswith("Endpoint="):
            # Strip the 'Endpoint=' prefix and any trailing slash for consistency
            return part[len("Endpoint=") :].rstrip("/")
    raise ValueError("Endpoint not found in Azure SignalR connection string.")


@app.function_name("negotiate")
@app.route(route="agent/negotiate", methods=["POST", "GET"])
def negotiate(req: func.HttpRequest) -> func.HttpResponse:
    """Provide SignalR connection info for clients (manual negotiation)."""
    try:
        # Build client URL for the configured hub
        # Endpoint format: https://<name>.service.signalr.net/client/?hub=<hub>
        base_url = signalr_client._endpoint.rstrip("/")
        client_url = f"{base_url}/client/?hub={SIGNALR_HUB_NAME}"

        # Generate token with the CLIENT URL as audience for browser clients
        # Azure SignalR Service expects audience to match the client connection URL
        access_token = signalr_client._generate_token(client_url)

        # Return negotiation response for SignalR JS client
        body = json.dumps({"url": client_url, "accessToken": access_token})
        return func.HttpResponse(body=body, mimetype="application/json")
    except Exception as ex:
        logging.error("Failed to negotiate SignalR connection: %s", ex)
        return func.HttpResponse(
            json.dumps({"error": str(ex)}),
            status_code=500,
            mimetype="application/json",
        )


@app.function_name("joinGroup")
@app.route(route="agent/join-group", methods=["POST"])
async def join_group(req: func.HttpRequest) -> func.HttpResponse:
    """Add a SignalR connection to a conversation group for user isolation."""
    try:
        body = req.get_json()
        group = body.get("group")
        connection_id = body.get("connectionId")

        if not group or not connection_id:
            return func.HttpResponse(
                json.dumps({"error": "group and connectionId are required"}),
                status_code=400,
                mimetype="application/json",
            )

        await signalr_client.add_connection_to_group(group, connection_id)
        return func.HttpResponse(
            json.dumps({"status": "joined", "group": group}),
            mimetype="application/json",
        )
    except Exception as ex:
        logging.error("Failed to join group: %s", ex)
        return func.HttpResponse(
            json.dumps({"error": str(ex)}),
            status_code=500,
            mimetype="application/json",
        )


@app.function_name("createThread")
@app.route(route="agent/create-thread", methods=["POST"])
def create_thread(req: func.HttpRequest) -> func.HttpResponse:
    """Create a new thread_id for a conversation.

    Note: The agent framework auto-generates thread_ids, but we need to create
    one upfront so the client can join the SignalR group before sending messages.
    """
    thread_id = uuid.uuid4().hex  # Match agent framework format (32-char hex)
    return func.HttpResponse(
        json.dumps({"thread_id": thread_id}),
        mimetype="application/json",
    )


@app.route(route="index", methods=["GET"])
def index(req: func.HttpRequest) -> func.HttpResponse:
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
