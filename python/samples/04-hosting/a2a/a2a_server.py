# Copyright (c) Microsoft. All rights reserved.

import argparse
import logging
import os
import sys
import uuid
from asyncio import CancelledError
from typing import Generic, TypeVar

import uvicorn
from a2a.helpers import new_task_from_user_message
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore, TaskUpdater
from a2a.types import Part, TaskState
from agent_definitions import AGENT_CARD_FACTORIES, AGENT_FACTORIES  # pyrefly: ignore[missing-import]
from agent_framework import SupportsAgentRun
from agent_framework.foundry import FoundryChatClient
from agent_framework_hosting import AgentState
from agent_framework_hosting_a2a import a2a_from_run, a2a_to_run
from azure.identity import AzureCliCredential
from dotenv import load_dotenv
from starlette.applications import Starlette

# Load environment variables from .env file
load_dotenv()
logger = logging.getLogger(__name__)

AgentT = TypeVar("AgentT", bound=SupportsAgentRun)

"""
A2A Server Sample — Host an Agent Framework agent as an A2A endpoint

This sample creates a Python-based A2A-compliant server that wraps an Agent
Framework agent.  The server uses the a2a-sdk's Starlette application to handle
JSON-RPC requests and serves the AgentCard at /.well-known/agent.json.

Three agent types are available:
  - invoice   — Answers invoice queries using mock data and function tools.
  - policy    — Returns a fixed policy response.
  - logistics — Returns a fixed logistics response.

Usage:
  uv run python a2a_server.py --agent-type policy --port 5001
  uv run python a2a_server.py --agent-type invoice --port 5000
  uv run python a2a_server.py --agent-type logistics --port 5002

Environment variables:
  FOUNDRY_PROJECT_ENDPOINT              — Your Azure AI Foundry project endpoint
  FOUNDRY_MODEL — Model deployment name (e.g. gpt-4o)
"""


class AppAgentExecutor(AgentExecutor, Generic[AgentT]):
    """Native A2A SDK executor composed with Agent Framework conversion helpers."""

    def __init__(self, state: AgentState[AgentT]) -> None:
        self.state = state

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        if context.context_id is None:
            raise ValueError("A2A context id is required")
        updater = TaskUpdater(event_queue, context.task_id or "", context.context_id)
        await updater.cancel()

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        if context.message is None or context.context_id is None:
            raise ValueError("A2A message and context id are required")

        task = context.current_task
        if task is None:
            task = new_task_from_user_message(context.message)
            await event_queue.enqueue_event(task)

        updater = TaskUpdater(event_queue, task.id, context.context_id)
        await updater.submit()
        try:
            await updater.start_work()
            run = a2a_to_run(context.message, stream=True)
            agent = await self.state.get_target()
            # Demo-only key: the outer server must authenticate and authorize these protocol IDs for multi-user use.
            session_id = f"a2a:{context.tenant}:{context.context_id}"
            session = await self.state.get_or_create_session(session_id)
            if not run["stream"]:
                raise RuntimeError("This executor requires streaming run arguments.")
            stream = agent.run(  # pyright: ignore[reportCallIssue]
                run["messages"],
                session=session,
                options=run["options"],
                stream=run["stream"],
            )
            default_artifact_id = uuid.uuid4().hex
            streamed_artifact_ids: set[str] = set()
            async for update in stream:
                parts = a2a_from_run(update)
                if parts:
                    artifact_id = update.message_id or default_artifact_id
                    await updater.add_artifact(
                        parts=parts,
                        artifact_id=artifact_id,
                        append=True if artifact_id in streamed_artifact_ids else None,
                    )
                    streamed_artifact_ids.add(artifact_id)
            final_response = await stream.get_final_response()
            if not streamed_artifact_ids:
                parts = a2a_from_run(final_response)
                if parts:
                    await updater.update_status(
                        state=TaskState.TASK_STATE_WORKING,
                        message=updater.new_agent_message(parts),
                    )
            await self.state.set_session(session_id, session)
            await updater.complete()
        except CancelledError:
            await updater.update_status(state=TaskState.TASK_STATE_CANCELED)
        except Exception:
            logger.exception("A2A agent execution failed.")
            await updater.update_status(
                state=TaskState.TASK_STATE_FAILED,
                message=updater.new_agent_message([Part(text="Agent execution failed.")]),
            )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="A2A Agent Server")
    parser.add_argument(
        "--agent-type",
        choices=["invoice", "policy", "logistics"],
        default="policy",
        help="Type of agent to host (default: policy)",
    )
    parser.add_argument(
        "--host",
        default="localhost",
        help="Host to bind to (default: localhost)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=5001,
        help="Port to listen on (default: 5001)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # Validate environment
    project_endpoint = os.getenv("FOUNDRY_PROJECT_ENDPOINT")
    model = os.getenv("FOUNDRY_MODEL")

    if not project_endpoint:
        print("Error: FOUNDRY_PROJECT_ENDPOINT environment variable is not set.")
        sys.exit(1)
    if not model:
        print("Error: FOUNDRY_MODEL environment variable is not set.")
        sys.exit(1)

    # Create the LLM client
    credential = AzureCliCredential()
    client = FoundryChatClient(
        project_endpoint=project_endpoint,
        model=model,
        credential=credential,
    )

    # Create the Agent Framework agent for the chosen type
    agent_factory = AGENT_FACTORIES[args.agent_type]
    agent = agent_factory(client)
    state = AgentState(agent)

    # Build the A2A server components
    url = f"http://{args.host}:{args.port}/"
    agent_card = AGENT_CARD_FACTORIES[args.agent_type](url)
    executor = AppAgentExecutor(state)
    task_store = InMemoryTaskStore()
    request_handler = DefaultRequestHandler(
        agent_executor=executor,
        task_store=task_store,
        agent_card=agent_card,
    )

    app = Starlette(
        routes=[
            *create_agent_card_routes(agent_card),
            *create_jsonrpc_routes(request_handler, "/"),
        ]
    )

    print(f"Starting A2A server: {agent_card.name}")
    print(f"  Agent type : {args.agent_type}")
    print(f"  Listening  : {url}")
    print(f"  Agent card : {url}.well-known/agent.json")
    print()

    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
    )


if __name__ == "__main__":
    main()
