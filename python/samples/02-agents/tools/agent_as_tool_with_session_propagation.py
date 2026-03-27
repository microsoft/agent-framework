# Copyright (c) Microsoft. All rights reserved.

import asyncio
from collections.abc import Awaitable, Callable

from agent_framework import Agent, AgentContext, AgentSession, FunctionInvocationContext, tool
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
"""


async def log_session(
    context: AgentContext,
    call_next: Callable[[], Awaitable[None]],
) -> None:
    """Agent middleware that logs the session received by each agent."""
    session: AgentSession | None = context.session
    if not session:
        print("No session found.")
        await call_next()
        return
    agent_name = context.agent.name or "unknown"
    print(
        f"  [{agent_name}] session_id={session.session_id}, "
        f"service_session_id={session.service_session_id} state={session.state}"
    )
    await call_next()


@tool(description="Use this tool to store the findings so that other agents can reason over them.")
def store_findings(findings: str, ctx: FunctionInvocationContext) -> None:
    if ctx.session is None:
        return
    current_findings = ctx.session.state.get("findings")
    if current_findings is None:
        ctx.session.state["findings"] = findings
    else:
        ctx.session.state["findings"] = f"{current_findings}\n{findings}"


@tool(description="Use this tool to gather the current findings from other agents.")
def recall_findings(ctx: FunctionInvocationContext) -> str:
    if ctx.session is None:
        return "No session available"
    current_findings = ctx.session.state.get("findings")
    if current_findings is None:
        return "Nothing yet"
    return current_findings


async def main() -> None:
    print("=== Agent-as-Tool: Session Propagation ===\n")

    client = OpenAIResponsesClient()

    research_agent = Agent(
        client=client,
        name="ResearchAgent",
        instructions="You are a research assistant. Provide concise answers and store your findings.",
        middleware=[log_session],
        tools=[store_findings, recall_findings],
    )

    research_tool = research_agent.as_tool(
        name="research",
        description="Research a topic and store your findings.",
        arg_name="query",
        arg_description="The research query",
        propagate_session=True,
    )

    coordinator = Agent(
        client=client,
        name="CoordinatorAgent",
        instructions=(
            "You coordinate research. Use the 'research' tool to start research "
            "and then use the recall findings tool to gather up everything."
        ),
        tools=[research_tool, store_findings, recall_findings],
        middleware=[log_session],
    )

    session = coordinator.create_session()
    session.state["findings"] = None
    print(f"Session ID: {session.session_id}")
    print(f"Session state before run: {session.state}\n")

    query = "What are the latest developments in quantum computing and in AI?"
    print(f"User: {query}\n")

    result = await coordinator.run(query, session=session)

    print(f"\nCoordinator: {result}\n")
    print(f"Session state after run: {session.state}")


if __name__ == "__main__":
    asyncio.run(main())
