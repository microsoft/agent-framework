# Copyright (c) Microsoft. All rights reserved.

import logging
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
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentInterface,
    AgentSkill,
    Part,
    TaskState,
)
from agent_framework import Agent, SupportsAgentRun
from agent_framework.openai import OpenAIChatClient
from agent_framework_hosting import AgentState
from agent_framework_hosting_a2a import a2a_from_run, a2a_to_run
from dotenv import load_dotenv
from starlette.applications import Starlette

load_dotenv()

logger = logging.getLogger(__name__)

AgentT = TypeVar("AgentT", bound=SupportsAgentRun)


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
        except Exception as exc:
            logger.exception("A2A agent execution failed.")
            await updater.update_status(
                state=TaskState.TASK_STATE_FAILED,
                message=updater.new_agent_message([Part(text=str(exc))]),
            )


if __name__ == "__main__":
    # --8<-- [start:AgentSkill]
    flight_skill = AgentSkill(
        id="Flight_Booking",
        name="Flight Booking",
        description="Search and book flights across Europe.",
        tags=["flights", "travel", "europe"],
        examples=[],
    )
    hotel_skill = AgentSkill(
        id="Hotel_Booking",
        name="Hotel Booking",
        description="Search and book hotels across Europe.",
        tags=["hotels", "travel", "accommodation"],
        examples=[],
    )
    # --8<-- [end:AgentSkill]

    # --8<-- [start:AgentCard]
    # This will be the public-facing agent card
    public_agent_card = AgentCard(
        name="Europe Travel Agent",
        description=(
            "A helpful Europe Travel Agent that can help users search and book flights and hotels across Europe."
        ),
        version="1.0.0",
        default_input_modes=["text"],
        default_output_modes=["text"],
        capabilities=AgentCapabilities(streaming=True),
        supported_interfaces=[AgentInterface(url="http://localhost:9999/", protocol_binding="JSONRPC")],
        skills=[flight_skill, hotel_skill],
    )
    # --8<-- [end:AgentCard]

    agent = Agent(
        client=OpenAIChatClient(),
        name="Europe Travel Agent",
        instructions=(
            "You are a helpful Europe Travel Agent. "
            "You can help users search and book flights and hotels across Europe."
        ),
    )
    state = AgentState(agent)

    request_handler = DefaultRequestHandler(
        agent_executor=AppAgentExecutor(state),
        task_store=InMemoryTaskStore(),
        agent_card=public_agent_card,
    )

    server = Starlette(
        routes=[
            *create_agent_card_routes(public_agent_card),
            *create_jsonrpc_routes(request_handler, "/"),
        ]
    )

    uvicorn.run(server, host="0.0.0.0", port=9999)
