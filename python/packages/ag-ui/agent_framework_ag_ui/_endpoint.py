# Copyright (c) Microsoft. All rights reserved.

"""FastAPI endpoint creation for AG-UI agents."""

import logging
from typing import Any

from ag_ui.encoder import EventEncoder
from agent_framework import AgentProtocol
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse

from ._agent import AgentFrameworkAgent

logger = logging.getLogger(__name__)


def add_agent_framework_fastapi_endpoint(
    app: FastAPI,
    agent: AgentProtocol | AgentFrameworkAgent,
    path: str = "/",
    state_schema: dict[str, Any] | None = None,
    predict_state_config: dict[str, dict[str, str]] | None = None,
    allow_origins: list[str] | None = None,
) -> None:
    """Add an AG-UI endpoint to a FastAPI app.

    Args:
        app: The FastAPI application
        agent: The agent to expose (can be raw AgentProtocol or wrapped)
        path: The endpoint path
        state_schema: Optional state schema for shared state management
        predict_state_config: Optional predictive state update configuration.
            Format: {"state_key": {"tool": "tool_name", "tool_argument": "arg_name"}}
        allow_origins: CORS origins (not yet implemented)
    """
    if isinstance(agent, AgentProtocol):
        wrapped_agent = AgentFrameworkAgent(
            agent=agent,
            state_schema=state_schema,
            predict_state_config=predict_state_config,
        )
    else:
        wrapped_agent = agent

    @app.post(path)
    async def agent_endpoint(request: Request):  # type: ignore[misc]
        """Handle AG-UI agent requests.

        Note: Function is accessed via FastAPI's decorator registration,
        despite appearing unused to static analysis.
        """
        try:
            input_data = await request.json()
            print(f"\n{'=' * 80}")
            print(f"[{path}] RECEIVED REQUEST")
            print(f"  Run ID: {input_data.get('run_id', 'no-run-id')}")
            print(f"  Thread ID: {input_data.get('thread_id', 'no-thread-id')}")
            print(f"  Messages: {len(input_data.get('messages', []))}")

            # Debug: Print the entire input_data to see what the UI is sending
            import json

            print("  Full input data:")
            print(json.dumps(input_data, indent=2))

            print(f"{'=' * 80}\n")
            logger.info(f"Received request at {path}: {input_data.get('run_id', 'no-run-id')}")

            async def event_generator():
                encoder = EventEncoder()
                event_count = 0
                async for event in wrapped_agent.run_agent(input_data):
                    event_count += 1
                    print(f"[{path}] >>> EVENT {event_count}: {type(event).__name__}")
                    if hasattr(event, "model_dump"):
                        event_data = event.model_dump(exclude_none=True)
                        print(f"    Data: {event_data}")

                    logger.info(f"[{path}] Event {event_count}: {type(event).__name__}")
                    # Log event payload for debugging
                    if hasattr(event, "model_dump"):
                        event_data = event.model_dump(exclude_none=True)
                        logger.info(f"[{path}] Event payload: {event_data}")
                    encoded = encoder.encode(event)
                    print(f"    Encoded: {encoded[:150]}..." if len(encoded) > 150 else f"    Encoded: {encoded}")
                    logger.info(
                        f"[{path}] Encoded as: {encoded[:200]}..."
                        if len(encoded) > 200
                        else f"[{path}] Encoded as: {encoded}"
                    )
                    yield encoded
                print(f"\n[{path}] COMPLETED: {event_count} events total\n")
                logger.info(f"[{path}] Completed streaming {event_count} events")

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
            return {"error": str(e)}
