# Copyright (c) Microsoft. All rights reserved.

import asyncio
import logging
import uuid
from typing import Any

import uvicorn
from a2a.helpers import new_task_from_user_message
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore, TaskUpdater
from a2a.types import (
    AgentCapabilities,
    AgentInterface,
    Part,
    TaskState,
)
from agent_framework import Agent, InlineSkill, SkillFrontmatter, SkillsProvider
from agent_framework.openai import OpenAIChatClient
from agent_framework_hosting import AgentState
from agent_framework_hosting_a2a import AgentA2AAdapter
from dotenv import load_dotenv
from starlette.applications import Starlette

load_dotenv()

logger = logging.getLogger(__name__)


class AppAgentExecutor(AgentExecutor):
    """Native A2A SDK executor composed with Agent Framework conversion helpers."""

    def __init__(self, adapter: AgentA2AAdapter[Any]) -> None:
        self.adapter = adapter

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
            run = self.adapter.a2a_to_run(context.message, stream=True)
            agent = await self.adapter.state.get_target()
            # Demo-only key: the outer server must authenticate and authorize these protocol IDs for multi-user use.
            session_id = f"a2a:{context.tenant}:{context.context_id}"
            session = await self.adapter.state.get_or_create_session(session_id)
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
                parts = self.adapter.a2a_from_run(update)
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
                parts = self.adapter.a2a_from_run(final_response)
                if parts:
                    await updater.update_status(
                        state=TaskState.TASK_STATE_WORKING,
                        message=updater.new_agent_message(parts),
                    )
            await self.adapter.state.set_session(session_id, session)
            await updater.complete()
        except asyncio.CancelledError:
            await updater.update_status(state=TaskState.TASK_STATE_CANCELED)
        except Exception:
            logger.exception("A2A agent execution failed.")
            await updater.update_status(
                state=TaskState.TASK_STATE_FAILED,
                message=updater.new_agent_message([Part(text="Agent execution failed.")]),
            )


if __name__ == "__main__":
    flight_skill = InlineSkill(
        frontmatter=SkillFrontmatter(
            name="flight-booking",
            description="Search and book flights across Europe.",
        ),
        instructions="Help users search and book flights across Europe.",
    )
    hotel_skill = InlineSkill(
        frontmatter=SkillFrontmatter(
            name="hotel-booking",
            description="Search and book hotels across Europe.",
        ),
        instructions="Help users search and book hotels across Europe.",
    )
    agent = Agent(
        client=OpenAIChatClient(),
        name="Europe Travel Agent",
        description="Helps users search and book flights and hotels across Europe.",
        instructions="You are a helpful Europe Travel Agent.",
        context_providers=[SkillsProvider([flight_skill, hotel_skill])],
    )

    state = AgentState(agent)
    adapter = AgentA2AAdapter(
        state,
        version="1.0.0",
        capabilities=AgentCapabilities(streaming=True),
        supported_interfaces=[AgentInterface(url="http://localhost:9999/", protocol_binding="JSONRPC")],
    )
    public_agent_card = asyncio.run(adapter.get_card())
    request_handler = DefaultRequestHandler(
        agent_executor=AppAgentExecutor(adapter),
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
