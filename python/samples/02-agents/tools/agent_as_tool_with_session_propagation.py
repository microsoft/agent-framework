# Copyright (c) Microsoft. All rights reserved.

import asyncio
from collections.abc import Awaitable, Callable

from agent_framework import AgentContext, AgentSession, FunctionInvocationContext, tool
from agent_framework.openai import OpenAIResponsesClient
from dotenv import load_dotenv

load_dotenv()

"""
Agent-as-Tool: Session Propagation Example

Demonstrates how to share an AgentSession between a coordinator agent and a
sub-agent invoked as a tool using ``propagate_session=True``.

When session propagation is enabled, both agents share the same session object,
including session_id and the mutable state dict.  This allows correlated
conversation tracking and shared state across the agent hierarchy. The session
must be passed explicitly through ``function_invocation_kwargs`` for the
delegated tool call.

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
    session = ctx.kwargs.get("session")
    current_findings = session.state["findings"]
    if current_findings is None:
        session.state["findings"] = findings
    else:
        session.state["finding"] = f"{current_findings}\n{findings}"


@tool(description="Use this tool to gather the current findings from other agents.")
def recall_findings(ctx: FunctionInvocationContext) -> str:
    session = ctx.kwargs.get("session")
    current_findings = session.state["findings"]
    if current_findings is None:
        return "Nothing yet"
    return current_findings


async def main() -> None:
    print("=== Agent-as-Tool: Session Propagation ===\n")

    client = OpenAIResponsesClient()

    # --- Sub-agent: a research specialist ---
    # The sub-agent has the same log_session middleware to prove it receives the session.
    research_agent = client.as_agent(
        name="ResearchAgent",
        instructions="You are a research assistant. Provide concise answers and store your findings.",
        middleware=[log_session],
        tools=[store_findings, recall_findings],
    )

    # propagate_session=True forwards an explicitly supplied runtime session.
    research_tool = research_agent.as_tool(
        name="research",
        description="Research a topic and store your findings.",
        arg_name="query",
        arg_description="The research query",
        propagate_session=True,
    )

    # --- Coordinator agent ---
    coordinator = client.as_agent(
        name="CoordinatorAgent",
        instructions="You coordinate research. Use the 'research' tool to start research and then use the recall findings tool to gather up everything. You can also start by storing some of the background directly.",
        tools=[research_tool, store_findings, recall_findings],
        middleware=[log_session],
    )

    # Create a shared session and put some state in it
    session = coordinator.create_session()
    session.state["findings"] = None
    print(f"Session ID: {session.session_id}")
    print(f"Session state before run: {session.state}\n")

    query = "What are the latest developments in quantum computing and in AI?"
    print(f"User: {query}\n")

    result = await coordinator.run(
        query,
        session=session,
        function_invocation_kwargs={"session": session},
    )

    print(f"\nCoordinator: {result}\n")
    print(f"Session state after run: {session.state}")
    print("\nIf both agents show the same session_id above, session propagation is working.")


if __name__ == "__main__":
    asyncio.run(main())
