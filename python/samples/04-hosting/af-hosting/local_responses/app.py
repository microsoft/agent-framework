# Copyright (c) Microsoft. All rights reserved.

"""Minimal Responses-only hosting sample with native FastAPI routes.

This sample demonstrates the helper-first hosting shape:

1. ``agent-framework-hosting-responses`` converts Responses request/response
   payloads to and from Agent Framework run values.
2. ``agent-framework-hosting`` owns shared execution state via
   ``AgentFrameworkState`` and ``SessionStore``.
3. FastAPI owns the route, request parsing, policy decisions, and response
   object.

Run
---
``app`` is a module-level FastAPI ASGI app. Recommended local launch::

    uv sync
    az login
    export FOUNDRY_PROJECT_ENDPOINT=https://<your-project>.services.ai.azure.com
    export FOUNDRY_MODEL=gpt-5-nano
    uv run hypercorn app:app --bind 0.0.0.0:8000

Or use the ``__main__`` block (single-process Hypercorn) for quick
iteration::

    uv run python app.py

Then call it::

    uv run python call_server.py "What is the weather in Tokyo?"
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Annotated, Any, cast

from agent_framework import Agent, FileHistoryProvider, ResponseStream, tool
from agent_framework_foundry import FoundryChatClient
from agent_framework_hosting import AgentFrameworkState, SessionStore
from agent_framework_hosting_responses import (
    create_response_id,
    responses_from_run,
    responses_session_id,
    responses_stream_events_from_run,
    responses_to_run,
)
from azure.identity.aio import DefaultAzureCredential
from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from hypercorn.asyncio import serve
from hypercorn.config import Config

SESSIONS_DIR = Path(__file__).resolve().parent / "storage" / "sessions"
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)


@tool(approval_mode="never_require")
def lookup_weather(
    location: Annotated[str, "The city to look up weather for."],
) -> str:
    """Return a deterministic weather report for a city."""
    high_temp = 5 + (sum(location.encode("utf-8")) % 21)
    reports = {
        "Seattle": f"Seattle is rainy with a high of {high_temp}°C.",
        "Amsterdam": f"Amsterdam is cloudy with a high of {high_temp}°C.",
        "Tokyo": f"Tokyo is clear with a high of {high_temp}°C.",
    }
    return reports.get(location, f"{location} is sunny with a high of {high_temp}°C.")


def create_agent() -> Agent:
    """Create the sample weather agent."""
    return Agent(
        client=FoundryChatClient(credential=DefaultAzureCredential()),
        name="WeatherAgent",
        instructions=(
            "You are a friendly weather assistant. Use the lookup_weather tool "
            "for any weather question and answer in one short sentence."
        ),
        tools=[lookup_weather],
        context_providers=[FileHistoryProvider(SESSIONS_DIR)],
        default_options={"store": False},
    )


app = FastAPI()
state = AgentFrameworkState(create_agent, session_store=SessionStore)


@app.post("/responses")
async def responses(body: dict[str, Any] = Body(...)) -> JSONResponse | StreamingResponse:  # noqa: B008
    """Handle one OpenAI Responses-shaped request."""
    run = responses_to_run(body)
    session_id = responses_session_id(body)
    response_id = create_response_id()

    options = dict(run["options"])
    # App-specific policy: caller cannot pick deployment/persistence settings,
    # and this sample forces a consistent reasoning preset.
    options.pop("model", None)
    options.pop("temperature", None)
    options.pop("store", None)
    options["reasoning"] = {"effort": "medium", "summary": "auto"}
    options_for_run = cast(Any, options)

    target = cast(Agent[Any], await state.get_target())
    session = await state.get_session(session_id or response_id)
    if run["stream"]:
        stream = target.run(
            run["messages"],
            stream=True,
            session=session,
            options=options_for_run,
        )
        if not isinstance(stream, ResponseStream):
            raise HTTPException(status_code=500, detail="agent did not return a response stream")
        return StreamingResponse(
            responses_stream_events_from_run(
                stream,
                response_id=response_id,
                session_id=session_id,
            ),
            media_type="text/event-stream",
        )

    result = await target.run(
        run["messages"],
        session=session,
        options=options_for_run,
    )
    return JSONResponse(
        responses_from_run(
            result,
            response_id=response_id,
            session_id=session_id,
        )
    )


async def main() -> None:
    """Run the sample with Hypercorn for local development."""
    config = Config()
    config.bind = [f"0.0.0.0:{int(os.environ.get('PORT', '8000'))}"]
    await serve(cast(Any, app), config)


if __name__ == "__main__":
    asyncio.run(main())

"""
Sample output:
User: What is the weather in Tokyo?
Agent: Tokyo is clear with a high of 18°C.
Response ID: resp_...
"""
