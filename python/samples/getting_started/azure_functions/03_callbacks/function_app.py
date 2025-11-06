"""Capture agent response callbacks inside Azure Functions.

Components used in this sample:
- AzureOpenAIChatClient to build an agent that streams interim updates.
- AgentFunctionApp with a default AgentResponseCallbackProtocol implementation.
- Azure Functions HTTP triggers that expose callback telemetry via REST.

Prerequisites: set `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_CHAT_DEPLOYMENT_NAME`, and either
`AZURE_OPENAI_API_KEY` or authenticate with Azure CLI before starting the Functions host."""

import json
import logging
import os
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, DefaultDict

import azure.functions as func
from agent_framework import AgentRunResponseUpdate
from agent_framework.azure import AzureOpenAIChatClient
from azure.identity import AzureCliCredential

from agent_framework.azurefunctions import AgentFunctionApp, AgentCallbackContext, AgentResponseCallbackProtocol

logger = logging.getLogger(__name__)

# 1. Define the environment variable keys required to build the Azure OpenAI client.
AZURE_OPENAI_ENDPOINT_ENV = "AZURE_OPENAI_ENDPOINT"
AZURE_OPENAI_DEPLOYMENT_ENV = "AZURE_OPENAI_CHAT_DEPLOYMENT_NAME"
AZURE_OPENAI_API_KEY_ENV = "AZURE_OPENAI_API_KEY"


# 2. Centralize Azure OpenAI configuration so the agent uses consistent credentials.
def _build_client_kwargs() -> dict[str, Any]:
    endpoint = os.getenv(AZURE_OPENAI_ENDPOINT_ENV)
    if not endpoint:
        raise RuntimeError(f"{AZURE_OPENAI_ENDPOINT_ENV} environment variable is required.")

    deployment = os.getenv(AZURE_OPENAI_DEPLOYMENT_ENV)
    if not deployment:
        raise RuntimeError(f"{AZURE_OPENAI_DEPLOYMENT_ENV} environment variable is required.")

    client_kwargs: dict[str, Any] = {
        "endpoint": endpoint,
        "deployment_name": deployment,
    }

    api_key = os.getenv(AZURE_OPENAI_API_KEY_ENV)
    if api_key:
        client_kwargs["api_key"] = api_key
    else:
        client_kwargs["credential"] = AzureCliCredential()

    return client_kwargs


# 3. Maintain an in-memory store for callback events (replace with durable storage in production).
CallbackStore = DefaultDict[str, list[dict[str, Any]]]
callback_events: CallbackStore = defaultdict(list)


def _serialize_usage(usage: Any) -> Any:
    """Best-effort serialization for agent usage metadata."""

    if usage is None:
        return None

    model_dump = getattr(usage, "model_dump", None)
    if callable(model_dump):
        return model_dump()

    to_dict = getattr(usage, "to_dict", None)
    if callable(to_dict):
        return to_dict()

    return str(usage)


class ConversationAuditTrail(AgentResponseCallbackProtocol):
    """Callback that records streaming chunks and final responses for later inspection."""

    def __init__(self) -> None:
        self._logger = logging.getLogger("durableagent.samples.callbacks.audit")

    async def on_streaming_response_update(
        self,
        update: AgentRunResponseUpdate,
        context: AgentCallbackContext,
    ) -> None:
        event = self._build_base_event(context)
        event.update(
            {
                "event_type": "stream",
                "update_kind": getattr(update, "kind", "text"),
                "text": getattr(update, "text", None),
            }
        )
        conversation_id = context.conversation_id or ""
        callback_events[conversation_id].append(event)

        preview = event.get("text") or event.get("update_kind")
        self._logger.info(
            "[%s][%s] streaming chunk: %s",
            context.agent_name,
            context.correlation_id,
            preview,
        )

    async def on_agent_response(self, response, context: AgentCallbackContext) -> None:
        event = self._build_base_event(context)
        event.update(
            {
                "event_type": "final",
                "response_text": getattr(response, "text", None),
                "usage": _serialize_usage(getattr(response, "usage_details", None)),
            }
        )
        conversation_id = context.conversation_id or ""
        callback_events[conversation_id].append(event)

        self._logger.info(
            "[%s][%s] final response recorded",
            context.agent_name,
            context.correlation_id,
        )

    @staticmethod
    def _build_base_event(context: AgentCallbackContext) -> dict[str, Any]:
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agent_name": context.agent_name,
            "conversation_id": context.conversation_id,
            "correlation_id": context.correlation_id,
            "request_message": context.request_message,
        }


# 4. Create the agent that will emit streaming updates and final responses.
callback_agent = AzureOpenAIChatClient(**_build_client_kwargs()).create_agent(
    name="CallbackAgent",
    instructions=(
        "You are a friendly assistant that narrates actions while responding. "
        "Keep answers concise and acknowledge when callbacks capture streaming updates."
    ),
)


# 5. Register the agent inside AgentFunctionApp with a default callback instance.
audit_callback = ConversationAuditTrail()
app = AgentFunctionApp(enable_health_check=True, default_callback=audit_callback)
app.add_agent(callback_agent)


@app.function_name("get_callback_events")
@app.route(route="agents/{agent_name}/callbacks/{conversationId}", methods=["GET"])
async def get_callback_events(req: func.HttpRequest) -> func.HttpResponse:
    """Return all callback events collected for a conversation."""

    conversation_id = req.route_params.get("conversationId", "")
    events = callback_events.get(conversation_id, [])
    return func.HttpResponse(
        json.dumps(events, indent=2),
        status_code=200,
        mimetype="application/json",
    )


@app.function_name("reset_callback_events")
@app.route(route="agents/{agent_name}/callbacks/{conversationId}", methods=["DELETE"])
async def reset_callback_events(req: func.HttpRequest) -> func.HttpResponse:
    """Clear the stored callback events for a conversation."""

    conversation_id = req.route_params.get("conversationId", "")
    callback_events.pop(conversation_id, None)
    return func.HttpResponse(status_code=204)


"""
Expected output when querying `GET /api/agents/CallbackAgent/callbacks/{conversationId}`:

HTTP/1.1 200 OK
[
  {
    "timestamp": "2024-01-01T00:00:00Z",
    "agent_name": "CallbackAgent",
    "conversation_id": "<conversationId>",
    "correlation_id": "<guid>",
    "request_message": "Tell me a short joke",
    "event_type": "stream",
    "update_kind": "text",
    "text": "Sure, here's a joke..."
  },
  {
    "timestamp": "2024-01-01T00:00:01Z",
    "agent_name": "CallbackAgent",
    "conversation_id": "<conversationId>",
    "correlation_id": "<guid>",
    "request_message": "Tell me a short joke",
    "event_type": "final",
    "response_text": "Why did the cloud...",
    "usage": {
      "type": "usage_details",
      "input_token_count": 159,
      "output_token_count": 29,
      "total_token_count": 188
    }
  }
]
"""
