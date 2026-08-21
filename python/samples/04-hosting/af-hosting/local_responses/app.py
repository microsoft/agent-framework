# Copyright (c) Microsoft. All rights reserved.

"""Minimal Responses-only hosting sample with native FastAPI routes.

This sample demonstrates the helper-first hosting shape:

1. ``agent-framework-hosting-responses`` converts Responses request/response
   payloads to and from Agent Framework run values.
2. ``agent-framework-hosting`` owns ``AgentState``; core provides its
   ``SessionStore``.
3. FastAPI owns the route, request parsing, policy decisions, and response
   object.

Production readiness
---
This sample is not a full-fledged production deployment. Before exposing this
route to callers, add authentication and authorization at the infrastructure
layer, the FastAPI app layer, or inside the route body.

Session continuation deserves particular care: treat ``previous_response_id``
and ``conversation_id`` as untrusted request values, authorize the caller
before loading or storing a session for those ids, and partition durable session
storage by tenant/user as appropriate for your application. See
``README.md#production-readiness``.

Unknown ``conversation_id`` values create a new local session in this sample.
Your app can choose a different policy, such as requiring a separate API to
create new conversations before callers can continue them.

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
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Annotated, Any, cast

from agent_framework import Agent, FileHistoryProvider, FileSessionStore, ResponseStream, tool
from agent_framework_foundry import FoundryChatClient
from agent_framework_hosting import AgentState
from agent_framework_hosting_responses import (
    create_response_id,
    responses_from_run,
    responses_from_streaming_run,
    responses_session_id,
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
state = AgentState(
    create_agent,
    session_store=FileSessionStore(SESSIONS_DIR / "snapshots"),
)

ALLOWED_REQUEST_OPTIONS = frozenset({"max_tokens", "reasoning"})


@app.post("/responses", response_model=None)
async def responses(body: dict[str, Any] = Body(...)) -> JSONResponse | StreamingResponse:  # noqa: B008
    """Handle one OpenAI Responses-shaped request."""
    try:
        run = responses_to_run(body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    session_id, is_conversation_id = responses_session_id(body)
    conversation_id = session_id if is_conversation_id else None
    response_id = create_response_id()

    # App-specific policy: allow only the request options this route is willing
    # to honor. This denies tools, tool_choice, deployment/persistence fields,
    # and all other caller-supplied options by default. Your app decides which
    # options are allowed, altered, or denied.
    options = {key: value for key, value in run["options"].items() if key in ALLOWED_REQUEST_OPTIONS}
    options["reasoning"] = {"effort": "medium", "summary": "auto"}
    options_for_run = cast(Any, options)

    target = await state.get_target()
    lookup_id = session_id or response_id
    # An unknown `conversation_id` becomes a new session here. Production apps
    # can choose to require a separate "create conversation" API instead.
    session = await state.get_or_create_session(lookup_id)
    if run["stream"]:
        stream = target.run(
            run["messages"],
            stream=True,
            session=session,
            options=options_for_run,
        )
        if not isinstance(stream, ResponseStream):
            raise HTTPException(status_code=500, detail="agent did not return a response stream")

        async def stream_events() -> AsyncIterator[str]:
            async for event in responses_from_streaming_run(
                stream,
                response_id=response_id,
                conversation_id=conversation_id,
            ):
                yield event
            # `agent.run(..., stream=True)` updates the session while the stream
            # is consumed/finalized. Persist the selected continuation only
            # after finalization.
            if conversation_id is not None:
                # A stable conversation id is a mutable head. Apps must ensure
                # only one caller advances it at a time; AgentState does not
                # serialize concurrent runs for the same id.
                await state.set_session(conversation_id, session)
            else:
                await state.set_session(response_id, session)

        return StreamingResponse(
            stream_events(),
            media_type="text/event-stream",
        )

    result = await target.run(
        run["messages"],
        session=session,
        options=options_for_run,
    )
    # `agent.run(...)` updates the session. Persist the selected continuation
    # only after the run completes.
    if conversation_id is not None:
        # Preserve sequential conversation continuity. Production apps must
        # provide their own per-conversation single-writer coordination.
        await state.set_session(conversation_id, session)
    else:
        await state.set_session(response_id, session)
    return JSONResponse(
        responses_from_run(
            result,
            response_id=response_id,
            conversation_id=conversation_id,
        )
    )


async def main() -> None:
    """Run the sample with Hypercorn for local development."""
    config = Config()
    config.bind = [f"0.0.0.0:{int(os.environ.get('PORT', '8000'))}"]
    await serve(cast(Any, app), config)


if __name__ == "__main__":
    asyncio.run(main())

# Sample output:
# User: What is the weather in Tokyo?
# Agent: Tokyo is clear with a high of 18°C.
# Response ID: resp_...
