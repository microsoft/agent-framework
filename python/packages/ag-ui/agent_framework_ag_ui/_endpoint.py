# Copyright (c) Microsoft. All rights reserved.

"""FastAPI endpoint creation for AG-UI agents."""

from __future__ import annotations

import copy
import logging
from collections.abc import AsyncGenerator, Sequence
from inspect import isawaitable
from typing import Any

from ag_ui.core import RunErrorEvent
from ag_ui.encoder import EventEncoder
from agent_framework import SupportsAgentRun, Workflow
from fastapi import FastAPI, HTTPException
from fastapi.params import Depends
from fastapi.responses import StreamingResponse

from ._agent import AgentFrameworkAgent
from ._snapshots import (
    _DEFAULT_STATE_INPUT_KEY,
    _SNAPSHOT_SCOPE_INPUT_KEY,
    AGUIThreadSnapshotStore,
    SnapshotScopeResolver,
)
from ._types import AGUIRequest
from ._workflow import AgentFrameworkWorkflow

logger = logging.getLogger(__name__)


def _get_snapshot_store(
    protocol_runner: AgentFrameworkAgent | AgentFrameworkWorkflow,
) -> AGUIThreadSnapshotStore | None:
    if isinstance(protocol_runner, AgentFrameworkAgent):
        return protocol_runner.config.snapshot_store
    return protocol_runner.snapshot_store


def _set_snapshot_store(
    protocol_runner: AgentFrameworkAgent | AgentFrameworkWorkflow,
    snapshot_store: AGUIThreadSnapshotStore,
) -> None:
    if isinstance(protocol_runner, AgentFrameworkAgent):
        protocol_runner.config.snapshot_store = snapshot_store
        return
    protocol_runner.snapshot_store = snapshot_store


def _configure_snapshot_persistence(
    protocol_runner: AgentFrameworkAgent | AgentFrameworkWorkflow,
    *,
    snapshot_store: AGUIThreadSnapshotStore | None,
    snapshot_scope_resolver: SnapshotScopeResolver | None,
) -> None:
    existing_snapshot_store = _get_snapshot_store(protocol_runner)
    if snapshot_store is not None:
        if existing_snapshot_store is not None and existing_snapshot_store is not snapshot_store:
            raise ValueError("snapshot_store is already configured on the AG-UI runner.")
        if existing_snapshot_store is None:
            _set_snapshot_store(protocol_runner, snapshot_store)
        existing_snapshot_store = snapshot_store

    if existing_snapshot_store is not None and snapshot_scope_resolver is None:
        raise ValueError(
            "snapshot_scope_resolver is required when snapshot_store is configured. "
            "AG-UI Thread ids identify threads but do not authorize snapshot access; "
            "provide a resolver that returns an explicit Snapshot Scope."
        )


def add_agent_framework_fastapi_endpoint(
    app: FastAPI,
    agent: SupportsAgentRun | AgentFrameworkAgent | Workflow | AgentFrameworkWorkflow,
    path: str = "/",
    state_schema: Any | None = None,
    predict_state_config: dict[str, dict[str, str]] | None = None,
    allow_origins: list[str] | None = None,
    default_state: dict[str, Any] | None = None,
    tags: list[str] | None = None,
    dependencies: Sequence[Depends] | None = None,
    snapshot_store: AGUIThreadSnapshotStore | None = None,
    snapshot_scope_resolver: SnapshotScopeResolver | None = None,
) -> None:
    """Add an AG-UI endpoint to a FastAPI app.

    Args:
        app: The FastAPI application
        agent: The agent to expose (can be raw SupportsAgentRun or wrapped)
        path: The endpoint path
        state_schema: Optional state schema for shared state management; accepts dict or Pydantic model/class
        predict_state_config: Optional predictive state update configuration.
            Format: {"state_key": {"tool": "tool_name", "tool_argument": "arg_name"}}
        allow_origins: CORS origins (not yet implemented)
        default_state: Optional initial state to seed when the client does not provide state keys
        tags: OpenAPI tags for endpoint categorization (defaults to ["AG-UI"])
        dependencies: Optional FastAPI dependencies for authentication/authorization.
            These dependencies run before the endpoint handler. Use this to add
            authentication checks, rate limiting, or other middleware-like behavior.
            Example: `dependencies=[Depends(verify_api_key)]`
        snapshot_store: Optional AG-UI Thread Snapshot store. Snapshot persistence is opt-in and requires an
            explicit Snapshot Scope resolver.
        snapshot_scope_resolver: Optional resolver for the application-defined Snapshot Scope. Required whenever
            a snapshot store is configured because an AG-UI Thread id is not an authorization boundary.
    """
    protocol_runner: AgentFrameworkAgent | AgentFrameworkWorkflow
    if isinstance(agent, AgentFrameworkWorkflow):
        protocol_runner = agent
    elif isinstance(agent, AgentFrameworkAgent):
        protocol_runner = agent
    elif isinstance(agent, Workflow):
        protocol_runner = AgentFrameworkWorkflow(workflow=agent)
    elif isinstance(agent, SupportsAgentRun):
        protocol_runner = AgentFrameworkAgent(
            agent=agent,
            state_schema=state_schema,
            predict_state_config=predict_state_config,
            snapshot_store=snapshot_store,
        )
    else:
        raise TypeError("agent must be SupportsAgentRun, Workflow, AgentFrameworkAgent, or AgentFrameworkWorkflow.")

    _configure_snapshot_persistence(
        protocol_runner,
        snapshot_store=snapshot_store,
        snapshot_scope_resolver=snapshot_scope_resolver,
    )

    @app.post(path, tags=tags or ["AG-UI"], dependencies=dependencies, response_model=None)  # type: ignore[arg-type]
    async def agent_endpoint(request_body: AGUIRequest) -> StreamingResponse:
        """Handle AG-UI agent requests.

        Note: Function is accessed via FastAPI's decorator registration,
        despite appearing unused to static analysis.
        """
        try:
            input_data = request_body.model_dump(exclude_none=True)
            snapshot_persistence_active = False
            if snapshot_scope_resolver is not None and _get_snapshot_store(protocol_runner) is not None:
                snapshot_scope = snapshot_scope_resolver(request_body)
                if isawaitable(snapshot_scope):
                    snapshot_scope = await snapshot_scope
                input_data[_SNAPSHOT_SCOPE_INPUT_KEY] = snapshot_scope
                snapshot_persistence_active = True
            if default_state:
                if snapshot_persistence_active:
                    # Defer default application to the runner so defaults only fill keys
                    # missing from both the stored snapshot state and the request state.
                    input_data[_DEFAULT_STATE_INPUT_KEY] = copy.deepcopy(default_state)
                else:
                    state = input_data.setdefault("state", {})
                    for key, value in default_state.items():
                        if key not in state:
                            state[key] = copy.deepcopy(value)
            logger.debug(
                f"[{path}] Received request - Run ID: {input_data.get('run_id', 'no-run-id')}, "
                f"Thread ID: {input_data.get('thread_id', 'no-thread-id')}, "
                f"Messages: {len(input_data.get('messages', []))}"
            )
            logger.info(f"Received request at {path}: {input_data.get('run_id', 'no-run-id')}")

            async def event_generator() -> AsyncGenerator[str]:
                encoder = EventEncoder()
                event_count = 0
                try:
                    async for event in protocol_runner.run(input_data):
                        event_count += 1
                        event_type_name = getattr(event, "type", type(event).__name__)
                        # Log important events at INFO level
                        if "TOOL_CALL" in str(event_type_name) or "RUN" in str(event_type_name):
                            if hasattr(event, "model_dump"):
                                event_data = event.model_dump(exclude_none=True)
                                logger.info(f"[{path}] Event {event_count}: {event_type_name} - {event_data}")
                            else:
                                logger.info(f"[{path}] Event {event_count}: {event_type_name}")

                        try:
                            encoded = encoder.encode(event)
                        except Exception as encode_error:
                            logger.exception("[%s] Failed to encode event %s", path, event_type_name)
                            run_error = RunErrorEvent(
                                message="An internal error has occurred while streaming events.",
                                code=type(encode_error).__name__,
                            )
                            try:
                                yield encoder.encode(run_error)
                            except Exception:
                                logger.exception("[%s] Failed to encode RUN_ERROR event", path)
                            return

                        logger.debug(
                            f"[{path}] Encoded as: {encoded[:200]}..."
                            if len(encoded) > 200
                            else f"[{path}] Encoded as: {encoded}"
                        )
                        yield encoded

                    logger.info(f"[{path}] Completed streaming {event_count} events")
                except Exception as stream_error:
                    logger.exception("[%s] Streaming failed", path)
                    run_error = RunErrorEvent(
                        message="An internal error has occurred while streaming events.",
                        code=type(stream_error).__name__,
                    )
                    try:
                        yield encoder.encode(run_error)
                    except Exception:
                        logger.exception("[%s] Failed to encode RUN_ERROR event", path)

            return StreamingResponse(
                event_generator(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                },
            )
        except Exception as e:
            logger.error(f"Error in agent endpoint: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="An internal error has occurred.") from e
