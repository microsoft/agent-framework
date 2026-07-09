# Copyright (c) Microsoft. All rights reserved.

"""Responses-only hosting sample that serves a harness agent.

This sample is the sibling of ``local_responses/``. It keeps the exact same
helper-first hosting shape but swaps the plain ``Agent`` target for a
batteries-included harness agent built with ``create_harness_agent``:

1. ``create_harness_agent`` (from core ``agent-framework``) assembles the full
   agent pipeline from a chat client: the function-invocation loop,
   per-service-call history persistence, context-window compaction, a todo
   provider, and heuristic tool approval.
2. ``agent-framework-hosting-responses`` converts Responses request/response
   payloads to and from Agent Framework run values.
3. ``agent-framework-hosting`` owns shared execution state via ``AgentState``
   and its ``SessionStore``.
4. FastAPI owns the route, request parsing, policy decisions, and response
   object.

The point of the sample is that a harness agent is just an ``Agent``, so it
drops straight into the same ``AgentState`` / Responses-helper seam as any
other target. The interactive-only harness features (plan/execute mode and the
Textual console) are turned off because a one-shot HTTP request has no console
to drive; web search is turned off to keep the sample self-contained. Todo
management and compaction stay on so the target is a genuine harness agent and
not just a relabelled plain ``Agent``.

Because the server runs headless, the ``lookup_weather`` tool is registered
with ``approval_mode="never_require"`` so a run never blocks waiting for a human
to approve a tool call.

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

Environment variables:
    FOUNDRY_PROJECT_ENDPOINT — Azure AI Foundry project endpoint URL
    FOUNDRY_MODEL            — Model deployment name

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
from typing import Annotated, Any, cast

from agent_framework import Agent, ResponseStream, create_harness_agent, tool
from agent_framework_foundry import FoundryChatClient
from agent_framework_hosting import AgentState
from agent_framework_hosting_responses import (
    create_response_id,
    responses_from_run,
    responses_from_streaming_run,
    responses_session_id,
    responses_to_run,
)
from azure.identity import AzureCliCredential
from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from hypercorn.asyncio import serve
from hypercorn.config import Config

# Token budget for the harness compaction feature.
MAX_CONTEXT_WINDOW_TOKENS = 128_000
MAX_OUTPUT_TOKENS = 16_384

WEATHER_INSTRUCTIONS = (
    "You are a friendly weather assistant. Use the lookup_weather tool for any "
    "weather question and answer in one short sentence."
)


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
    """Create the sample harness-based weather agent.

    ``create_harness_agent`` returns a plain ``Agent``, so the resulting target
    plugs into ``AgentState`` and the Responses helpers exactly like the
    ``local_responses`` sample's agent does. The harness supplies function
    invocation, per-service-call persistence, compaction, and todo management on
    top of the ``lookup_weather`` tool.
    """
    return create_harness_agent(
        # For authentication, run `az login` in a terminal or replace
        # AzureCliCredential with your preferred authentication option.
        client=FoundryChatClient(credential=AzureCliCredential()),
        name="HarnessWeatherAgent",
        description="A batteries-included harness agent that answers weather questions.",
        agent_instructions=WEATHER_INSTRUCTIONS,
        tools=[lookup_weather],
        max_context_window_tokens=MAX_CONTEXT_WINDOW_TOKENS,
        max_output_tokens=MAX_OUTPUT_TOKENS,
        # Turn off the interactive-only and provider-specific features so the
        # agent is a good fit for a headless, one-shot HTTP endpoint. Todo
        # management and compaction stay enabled.
        disable_mode=True,
        disable_web_search=True,
        # The app owns session state locally, so do not also persist server-side
        # Responses conversations.
        default_options={"store": False},
    )


app = FastAPI()
state = AgentState(create_agent)

ALLOWED_REQUEST_OPTIONS = frozenset({"max_tokens", "reasoning"})


@app.post("/responses", response_model=None)
async def responses(body: dict[str, Any] = Body(...)) -> JSONResponse | StreamingResponse:  # noqa: B008
    """Handle one OpenAI Responses-shaped request."""
    try:
        run = responses_to_run(body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    session_id = responses_session_id(body)
    response_id = create_response_id()

    # App-specific policy: allow only the request options this route is willing
    # to honor. This denies tools, tool_choice, deployment/persistence fields,
    # and all other caller-supplied options by default. Your app decides which
    # options are allowed, altered, or denied.
    options = {key: value for key, value in run["options"].items() if key in ALLOWED_REQUEST_OPTIONS}
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
                session_id=session_id,
            ):
                yield event
            # `agent.run(..., stream=True)` updates the session while the stream
            # is consumed/finalized. Store it under the newly minted response id
            # after finalization so a later `previous_response_id` can restore
            # this exact continuation point.
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
    # `agent.run(...)` updates the session. Store it under the newly minted
    # response id after the run so `previous_response_id=response_id` continues
    # from this exact point.
    await state.set_session(response_id, session)
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

# Sample output:
# User: What is the weather in Tokyo?
# Agent: Tokyo is clear with a high of 18°C.
# Response ID: resp_...
