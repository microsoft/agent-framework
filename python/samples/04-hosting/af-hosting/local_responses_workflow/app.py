# Copyright (c) Microsoft. All rights reserved.

"""Hosted workflow sample with run-hook input prep + checkpoint location.

Same three-agent slogan workflow as
``../../foundry-hosted-agents/responses/05_workflows/main.py`` (writer →
legal reviewer → formatter), driven through the ``agent-framework-hosting``
stack instead of the Foundry-Hosted-Agents runtime.

Workflow shape
--------------
``writer`` → ``legal_reviewer`` → ``formatter``. A single run hook parses
the Responses input and prepares the prompt the writer agent receives.

What this sample shows
----------------------
- A :class:`~agent_framework.Workflow` is a valid hosting target — the
  host detects it and dispatches to ``workflow.run(...)`` instead of
  ``agent.run(...)``.
- ``ResponsesChannel(run_hook=...)`` is the seam for **adapting the
  channel-native input into the workflow start executor's input**.
  The hook here parses the inbound text as JSON
  (``{"topic": ..., "style": ..., "audience": ...}``) — if parsing
  fails it falls back to using the whole text as ``topic`` with
  defaults — and replaces ``ChannelRequest.input`` with the prepared
  writer prompt.
- ``AgentFrameworkHost(checkpoint_location=...)`` enables
  per-conversation workflow checkpointing. The host scopes the
  checkpoint storage by ``ChannelRequest.session.isolation_key``
  (Responses uses ``previous_response_id`` / ``conversation_id`` as the
  isolation key), and restores from the latest checkpoint before each
  new turn — so a multi-turn workflow can resume across requests.
- No ``HistoryProvider`` is configured: the workflow owns its own state
  via the checkpoint store; the agent-history seam is for plain
  ``SupportsAgentRun`` agents.

Run
---
``app`` is a module-level Starlette ASGI app::

    uv sync
    az login
    export FOUNDRY_PROJECT_ENDPOINT=https://<your-project>.services.ai.azure.com
    export FOUNDRY_MODEL=gpt-5-nano
    uv run hypercorn app:app --bind 0.0.0.0:8000

Or for quick iteration::

    uv run python app.py

Then call it with a structured brief::

    uv run python call_server.py \\
        '{"topic": "electric SUV", "style": "playful", "audience": "young families"}'

Or with just a topic — the hook fills in defaults::

    uv run python call_server.py "Create a slogan for an electric SUV."
"""

from __future__ import annotations

import json
import os
from dataclasses import replace
from pathlib import Path

from agent_framework import (
    Agent,
    AgentExecutor,
    Message,
    WorkflowBuilder,
)
from agent_framework_foundry import FoundryChatClient
from agent_framework_hosting import AgentFrameworkHost, ChannelRequest
from agent_framework_hosting_responses import ResponsesChannel
from azure.identity.aio import DefaultAzureCredential

CHECKPOINTS_DIR = Path(__file__).resolve().parent / "storage" / "checkpoints"
CHECKPOINTS_DIR.mkdir(parents=True, exist_ok=True)


def prepare_writer_prompt(request: ChannelRequest, **_: object) -> ChannelRequest:
    """Prepare the workflow's initial writer prompt from Responses input.

    The channel hands the host either a ``str`` (rare on the Responses
    surface) or a list of :class:`Message`. This hook collapses that
    input to text, accepts either JSON or plain text, and replaces the
    request input with a plain prompt for the writer executor.
    """

    def extract_text(value: object) -> str:
        if isinstance(value, str):
            return value
        if isinstance(value, Message):
            return value.text
        if isinstance(value, list):
            return "\n".join(extract_text(item) for item in value)
        return ""

    text = extract_text(request.input).strip()
    topic = text or "a generic product"
    style = "modern"
    audience = "general"
    if topic.startswith("{"):
        try:
            data = json.loads(topic)
        except json.JSONDecodeError:
            data = None
        if isinstance(data, dict) and "topic" in data:
            topic = str(data["topic"])
            style = str(data.get("style", style))
            audience = str(data.get("audience", audience))

    prompt = (
        f"Topic: {topic}\n"
        f"Style: {style}\n"
        f"Audience: {audience}\n\n"
        "Write a single short slogan that fits the topic, style, and audience."
    )
    return replace(request, input=prompt)


def build_host() -> AgentFrameworkHost:
    client = FoundryChatClient(credential=DefaultAzureCredential())

    writer = Agent(
        client=client,
        name="writer",
        instructions=("You are an excellent slogan writer. You create new slogans based on the given topic."),
    )
    legal = Agent(
        client=client,
        name="legal_reviewer",
        instructions=(
            "You are an excellent legal reviewer. "
            "Make necessary corrections to the slogan so that it is legally compliant."
        ),
    )
    formatter = Agent(
        client=client,
        name="formatter",
        instructions=(
            "You are an excellent content formatter. "
            "You take the slogan and format it in a cool retro style when printing to a terminal."
        ),
    )

    # ``context_mode="last_agent"`` ensures each agent only sees the
    # previous executor's output — matching the Foundry sample.
    writer_ex = AgentExecutor(writer, context_mode="last_agent")
    legal_ex = AgentExecutor(legal, context_mode="last_agent")
    format_ex = AgentExecutor(formatter, context_mode="last_agent")

    workflow = (
        WorkflowBuilder(
            start_executor=writer_ex,
            output_executors=[format_ex],
        )
        .add_edge(writer_ex, legal_ex)
        .add_edge(legal_ex, format_ex)
        .build()
    )

    return AgentFrameworkHost(
        target=workflow,
        channels=[
            ResponsesChannel(run_hook=prepare_writer_prompt),
        ],
        # The host writes a per-conversation FileCheckpointStorage rooted
        # at ``CHECKPOINTS_DIR / <isolation_key>`` and restores from the
        # latest checkpoint at the start of every turn.
        checkpoint_location=CHECKPOINTS_DIR,
        debug=True,
    )


app = build_host().app


if __name__ == "__main__":
    build_host().serve(host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
