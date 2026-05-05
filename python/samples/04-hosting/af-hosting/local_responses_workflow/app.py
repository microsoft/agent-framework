# Copyright (c) Microsoft. All rights reserved.

"""Hosted workflow sample with a structured intake step + checkpoint location.

Same three-agent slogan workflow as
``../../foundry-hosted-agents/responses/04_workflows/main.py`` (writer →
legal reviewer → formatter), but with an extra **structured intake**
step at the front and driven through the ``agent-framework-hosting``
stack instead of the Foundry-Hosted-Agents runtime.

Workflow shape
--------------
``BriefIntakeExecutor`` (typed :class:`SloganBrief` input) → ``writer``
→ ``legal_reviewer`` → ``formatter``. The intake step formats the
structured brief into a prompt the writer agent understands.

What this sample shows
----------------------
- A :class:`~agent_framework.Workflow` is a valid hosting target — the
  host detects it and dispatches to ``workflow.run(...)`` instead of
  ``agent.run(...)``.
- ``ResponsesChannel(run_hook=...)`` (and the same hook on
  ``InvocationsChannel``) is the seam for **adapting the channel-native
  input into the workflow start executor's typed input**. The hook here
  parses the inbound text as JSON
  (``{"topic": ..., "style": ..., "audience": ...}``) — if parsing
  fails it falls back to using the whole text as ``topic`` with
  defaults — and replaces ``ChannelRequest.input`` with a
  :class:`SloganBrief`.
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
    export FOUNDRY_MODEL=gpt-5.4-nano
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
from dataclasses import dataclass, replace
from pathlib import Path

from agent_framework import (
    Agent,
    AgentExecutor,
    Executor,
    Message,
    WorkflowBuilder,
    WorkflowContext,
    handler,
)
from agent_framework_foundry import FoundryChatClient
from agent_framework_hosting import AgentFrameworkHost, ChannelRequest
from agent_framework_hosting_invocations import InvocationsChannel
from agent_framework_hosting_responses import ResponsesChannel
from azure.identity.aio import DefaultAzureCredential

CHECKPOINTS_DIR = Path(__file__).resolve().parent / "storage" / "checkpoints"
CHECKPOINTS_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class SloganBrief:
    """Typed input for the workflow's first executor."""

    topic: str
    style: str = "modern"
    audience: str = "general"


class BriefIntakeExecutor(Executor):
    """Format a :class:`SloganBrief` into a prompt for the writer agent."""

    @handler
    async def handle(self, brief: SloganBrief, ctx: WorkflowContext[str]) -> None:
        prompt = (
            f"Topic: {brief.topic}\n"
            f"Style: {brief.style}\n"
            f"Audience: {brief.audience}\n\n"
            "Write a single short slogan that fits the topic, style, and audience."
        )
        await ctx.send_message(prompt)


def _extract_text(value: object) -> str:
    """Pull plain text out of whatever the Responses channel produced.

    The channel hands the host either a ``str`` (rare on the Responses
    surface) or a list of :class:`Message`. The hook collapses both to
    a single concatenated string before attempting to parse a brief.
    """
    if isinstance(value, str):
        return value
    if isinstance(value, Message):
        return value.text
    if isinstance(value, list):
        return "\n".join(_extract_text(item) for item in value)
    return ""


def _parse_brief(text: str) -> SloganBrief:
    """Parse user text into a :class:`SloganBrief`.

    Accepts a JSON object with ``topic`` / ``style`` / ``audience``
    keys; falls back to using the whole text as ``topic`` with the
    other fields defaulted.
    """
    text = text.strip()
    if text.startswith("{"):
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = None
        if isinstance(data, dict) and "topic" in data:
            return SloganBrief(
                topic=str(data["topic"]),
                style=str(data.get("style", "modern")),
                audience=str(data.get("audience", "general")),
            )
    return SloganBrief(topic=text or "a generic product")


def brief_hook(request: ChannelRequest, **_: object) -> ChannelRequest:
    """Adapt the channel's free-form text into the workflow's typed input.

    Per ADR 0026 §5 / SPEC-002 "Channel run hook", this is the canonical
    seam for shaping ``ChannelRequest.input`` into the workflow start
    executor's input type — here :class:`SloganBrief` instead of
    ``str`` / ``list[Message]``. Shared between the Responses channel
    (which delivers a list of :class:`Message`) and the Invocations
    channel (which delivers a plain ``str``).
    """
    brief = _parse_brief(_extract_text(request.input))
    return replace(request, input=brief)


def build_host() -> AgentFrameworkHost:
    client = FoundryChatClient(credential=DefaultAzureCredential())

    writer = Agent(
        client=client,
        name="writer",
        instructions=(
            "You are an excellent slogan writer. You create new slogans based on the given topic."
        ),
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

    intake_ex = BriefIntakeExecutor(id="intake")
    # ``context_mode="last_agent"`` ensures each agent only sees the
    # previous executor's output — matching the Foundry sample.
    writer_ex = AgentExecutor(writer, context_mode="last_agent")
    legal_ex = AgentExecutor(legal, context_mode="last_agent")
    format_ex = AgentExecutor(formatter, context_mode="last_agent")

    workflow = (
        WorkflowBuilder(
            start_executor=intake_ex,
            output_executors=[format_ex],
        )
        .add_edge(intake_ex, writer_ex)
        .add_edge(writer_ex, legal_ex)
        .add_edge(legal_ex, format_ex)
        .build()
    )

    return AgentFrameworkHost(
        target=workflow,
        channels=[
            ResponsesChannel(run_hook=brief_hook),
            InvocationsChannel(run_hook=brief_hook),
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
