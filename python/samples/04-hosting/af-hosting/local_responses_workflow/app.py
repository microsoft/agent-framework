# Copyright (c) Microsoft. All rights reserved.

"""Responses helper sample with a local workflow target and native FastAPI route.

This sample demonstrates the helper-first hosting shape for workflows:

1. ``agent-framework-hosting-responses`` converts the Responses request body to
   Agent Framework run values and renders the final response payload.
2. ``agent-framework-hosting`` resolves the workflow target via ``WorkflowState``.
3. FastAPI owns the route, request parsing, policy decisions, response object,
   and file-backed checkpoint cursor.

Production readiness
---
This sample is not a full-fledged production deployment. Before exposing this
route to callers, add authentication and authorization at the infrastructure
layer, the FastAPI app layer, or inside the route body.

This sample demonstrates continuation with ``previous_response_id`` only. It
rejects ``conversation_id`` continuity with HTTP 400. Treat every
``previous_response_id`` as an untrusted request value, authorize the caller
before restoring or storing a checkpoint cursor for that id, and partition
durable checkpoint/cursor storage by tenant/user as appropriate for your
application. See ``README.md#production-readiness``.

Run
---
``app`` is a module-level FastAPI ASGI app. Recommended local launch::

    uv sync
    az login
    export FOUNDRY_PROJECT_ENDPOINT=https://<your-project>.services.ai.azure.com
    export FOUNDRY_MODEL=gpt-5-nano
    uv run hypercorn app:app --bind 0.0.0.0:8000

Or use the ``__main__`` block (single-process Hypercorn) for quick iteration::

    uv run python app.py

Then call it with a structured brief::

    uv run python call_server.py \
        '{"topic": "electric SUV", "style": "playful", "audience": "young families"}'
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any, TypedDict, cast

from agent_framework import (
    Agent,
    AgentExecutor,
    AgentExecutorResponse,
    AgentResponse,
    Content,
    Executor,
    FileCheckpointStorage,
    Message,
    WorkflowBuilder,
    WorkflowContext,
    handler,
)
from agent_framework_foundry import FoundryChatClient
from agent_framework_hosting import WorkflowState
from agent_framework_hosting_responses import (
    create_response_id,
    responses_from_run,
    responses_session_id,
    responses_to_run,
)
from azure.identity.aio import DefaultAzureCredential
from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import JSONResponse
from hypercorn.asyncio import serve
from hypercorn.config import Config

STORAGE_ROOT = Path(__file__).resolve().parent / "storage"
CHECKPOINTS_ROOT = STORAGE_ROOT / "checkpoints"
CHECKPOINT_CURSOR_PATH = STORAGE_ROOT / "checkpoint_cursors.json"
CHECKPOINTS_ROOT.mkdir(parents=True, exist_ok=True)


class CheckpointCursor(TypedDict):
    """Stored pointer to a workflow checkpoint and its storage bucket."""

    checkpoint_id: str
    storage_id: str


class CheckpointCursorStore:
    """File-backed mapping from Responses ids to workflow checkpoint ids."""

    def __init__(self, path: Path) -> None:
        """Create a cursor store at the given path.

        Args:
            path: JSON file containing response-id to checkpoint-id mappings.
        """
        self._path = path

    def get(self, key: str) -> CheckpointCursor | None:
        """Return the checkpoint cursor for a previous response id."""
        return self._load().get(key)

    def set_many(self, cursors: Mapping[str, CheckpointCursor]) -> None:
        """Persist one or more checkpoint cursors."""
        data = self._load()
        data.update(cursors)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def _load(self) -> dict[str, CheckpointCursor]:
        if not self._path.exists():
            return {}

        raw = json.loads(self._path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("Checkpoint cursor file must contain a JSON object.")

        data: dict[str, CheckpointCursor] = {}
        for key, value in raw.items():
            if not isinstance(key, str) or not isinstance(value, Mapping):
                raise ValueError("Checkpoint cursor file must map string ids to checkpoint cursor objects.")
            checkpoint_id = value.get("checkpoint_id")
            storage_id = value.get("storage_id")
            if not isinstance(checkpoint_id, str) or not isinstance(storage_id, str):
                raise ValueError("Checkpoint cursor objects must contain string checkpoint_id and storage_id fields.")
            data[key] = CheckpointCursor(checkpoint_id=checkpoint_id, storage_id=storage_id)
        return data


checkpoint_cursor_store = CheckpointCursorStore(CHECKPOINT_CURSOR_PATH)


def checkpoint_storage_for(storage_id: str) -> FileCheckpointStorage:
    """Return file checkpoint storage scoped to a single continuation bucket."""
    storage_key = hashlib.sha256(storage_id.encode("utf-8")).hexdigest()
    return FileCheckpointStorage(str(CHECKPOINTS_ROOT / storage_key))


def workflow_prompt_from_messages(messages: Any) -> str:
    """Prepare the workflow's initial writer prompt from Responses input."""

    def extract_text(value: object) -> str:
        if isinstance(value, str):
            return value
        if isinstance(value, Message):
            return value.text
        if isinstance(value, list):
            return "\n".join(extract_text(item) for item in value)
        return ""

    text = extract_text(messages).strip()
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

    return (
        f"Topic: {topic}\n"
        f"Style: {style}\n"
        f"Audience: {audience}\n\n"
        "Write a single short slogan that fits the topic, style, and audience."
    )


def response_from_workflow_result(result: Any) -> AgentResponse[Any]:
    """Collapse workflow outputs to one assistant response for Responses rendering."""
    outputs = result.get_outputs() if hasattr(result, "get_outputs") else []
    output = outputs[-1] if outputs else "(no workflow output)"
    text = output.text if isinstance(output, AgentResponse) else str(output)
    return AgentResponse(messages=Message(role="assistant", contents=[Content.from_text(text=text)]))


class TerminalFormatter(Executor):
    """Format the writer's output as the workflow's final response."""

    @handler
    async def handle(self, response: AgentExecutorResponse, ctx: WorkflowContext[Any, str]) -> None:
        """Yield one terminal-friendly slogan string.

        Args:
            response: The writer agent's response.
            ctx: Workflow context used to yield the final output.
        """
        slogan = response.agent_response.text.strip().strip('"')
        await ctx.yield_output(f'Slogan: "{slogan}"')


client = FoundryChatClient(credential=DefaultAzureCredential())
writer = Agent(
    client=client,
    name="writer",
    instructions="You are an excellent slogan writer. Create one short slogan from the given brief.",
)
writer_ex = AgentExecutor(writer, context_mode="last_agent")
formatter_ex = TerminalFormatter(id="terminal_formatter")

workflow_builder = WorkflowBuilder(
    name="local_responses_slogan_workflow",
    start_executor=writer_ex,
    output_from=[formatter_ex],
).add_edge(writer_ex, formatter_ex)


app = FastAPI()
state = WorkflowState(workflow_builder, cache_target=False)


@app.post("/responses", response_model=None)
async def responses(body: dict[str, Any] = Body(...)) -> JSONResponse:  # noqa: B008
    """Handle one OpenAI Responses-shaped request for the workflow."""
    try:
        run = responses_to_run(body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # This sample demonstrates only Responses `previous_response_id`
    # continuation, so reject `conversation_id` instead of treating it as a
    # checkpoint cursor.
    previous_response_id, is_conversation_id = responses_session_id(body)
    if is_conversation_id:
        raise HTTPException(
            status_code=400,
            detail="This server supports previous_response_id continuation only; conversation_id is not implemented.",
        )
    response_id = create_response_id()

    target = await state.get_target()
    if previous_response_id and (checkpoint_cursor := checkpoint_cursor_store.get(previous_response_id)) is not None:
        # Restore first. Workflow.run does not allow `message` and
        # `checkpoint_id` in the same call.
        await target.run(
            checkpoint_id=checkpoint_cursor["checkpoint_id"],
            checkpoint_storage=checkpoint_storage_for(checkpoint_cursor["storage_id"]),
        )

    storage_id = response_id
    checkpoint_storage = checkpoint_storage_for(storage_id)
    result = await target.run(
        message=workflow_prompt_from_messages(run["messages"]),
        checkpoint_storage=checkpoint_storage,
    )

    latest = await checkpoint_storage.get_latest(workflow_name=target.name)
    if latest is not None:
        # Responses `previous_response_id` can point to any response id. Store
        # the current response id as the cursor for this workflow continuation.
        cursor = CheckpointCursor(checkpoint_id=latest.checkpoint_id, storage_id=storage_id)
        checkpoint_cursor_store.set_many({response_id: cursor})

    return JSONResponse(
        responses_from_run(
            response_from_workflow_result(result),
            response_id=response_id,
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
# User: {"topic": "electric SUV", "style": "playful", "audience": "young families"}
# Assistant: Slogan: "Big Adventures. Tiny Emissions."
# Response ID: resp_...
