# Copyright (c) Microsoft. All rights reserved.

import asyncio
from collections.abc import Awaitable, Callable

from agent_framework import AgentContext, AgentSession
from agent_framework.openai import OpenAIResponsesClient
from dotenv import load_dotenv

load_dotenv()

"""
Agent-as-Tool: Session Propagation Example

Demonstrates how to share an AgentSession between a coordinator agent and a
sub-agent invoked as a tool using ``propagate_session=True``.

When session propagation is enabled, both agents share the same session object,
including session_id and the mutable state dict.  This allows correlated
conversation tracking and shared state across the agent hierarchy.

The middleware functions below are purely for observability — they are NOT
required for session propagation to work.
"""


async def log_session(
    context: AgentContext,
    call_next: Callable[[], Awaitable[None]],
) -> None:
    """Agent middleware that logs the session received by each agent.

    NOT required for session propagation — only used to observe the flow.
    If propagation is working, both agents will show the same session_id.
    """
    session: AgentSession | None = context.session
    agent_name = context.agent.name or "unknown"
    session_id = session.session_id if session else None
    state = dict(session.state) if session else {}
    print(f"  [{agent_name}] session_id={session_id}, state={state}")
    await call_next()


async def main() -> None:
    print("=== Agent-as-Tool: Session Propagation ===\n")

    client = OpenAIResponsesClient()

    # --- Sub-agent: a research specialist ---
    # The sub-agent has the same log_session middleware to prove it receives the session.
    research_agent = client.as_agent(
        name="ResearchAgent",
        instructions="You are a research assistant. Provide concise answers.",
        middleware=[log_session],
    )

    # propagate_session=True: the coordinator's session will be forwarded
    research_tool = research_agent.as_tool(
        name="research",
        description="Research a topic and return findings",
        arg_name="query",
        arg_description="The research query",
        propagate_session=True,
    )

    # --- Coordinator agent ---
    coordinator = client.as_agent(
        name="CoordinatorAgent",
        instructions="You coordinate research. Use the 'research' tool to look up information.",
        tools=[research_tool],
        middleware=[log_session],
    )

    # Create a shared session and put some state in it
    session = coordinator.create_session()
    session.state["request_source"] = "demo"
    print(f"Session ID: {session.session_id}")
    print(f"Session state before run: {session.state}\n")

    query = "What are the latest developments in quantum computing?"
    print(f"User: {query}\n")

    result = await coordinator.run(query, session=session)

    print(f"\nCoordinator: {result}\n")
    print(f"Session state after run: {session.state}")
    print(
        "\nIf both agents show the same session_id above, session propagation is working."
    )


if __name__ == "__main__":
    asyncio.run(main())
