# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
import os

from agent_framework import AgentSession
from agent_framework.foundry import FOUNDRY_HOSTED_AGENT_SESSION_ID_KEY, FoundryAgent
from azure.ai.projects.aio import AIProjectClient
from azure.ai.projects.models import VersionRefIndicator
from azure.identity.aio import AzureCliCredential
from dotenv import load_dotenv

load_dotenv()

"""
This sample demonstrates how to connect to the deployed basic Foundry agent with
`FoundryAgent`. It shows both service-managed and user-managed hosted-agent sessions.

The sample uses environment variables for configuration, which can be set in a .env file or in the environment directly:
Environment variables:
    FOUNDRY_PROJECT_ENDPOINT: Microsoft Foundry project endpoint.
    FOUNDRY_AGENT_NAME: Hosted agent name.
    FOUNDRY_AGENT_VERSION: Hosted agent version. Optional, defaults to latest if not specified.

After you deploy one of the agents in this directory, you can run this sample
to connect to it and have a conversation.

Note: The `allow_preview=True` flag is required to connect to the new hosted
agents, as this is a preview feature in Foundry.

"""


async def run_conversation(agent: FoundryAgent, session: AgentSession) -> None:
    """Run a multi-turn conversation using the supplied session."""
    queries = [
        "Hi!",
        "Your name is Javis. What can you do?",
        "What is your name?",
    ]
    for query in queries:
        print(f"\nUser: {query}")
        print("Agent: ", end="", flush=True)
        async for chunk in agent.run(query, session=session, stream=True):
            if chunk.text:
                print(chunk.text, end="", flush=True)
    print()


async def run_service_managed_session(
    *,
    agent: FoundryAgent,
    project_client: AIProjectClient,
    agent_name: str,
) -> None:
    """Let Foundry create the hosted-agent session, then delete it when finished."""
    session = AgentSession()
    print("\nService-managed hosted-agent session")
    print(f"Before first request: {session.state.get(FOUNDRY_HOSTED_AGENT_SESSION_ID_KEY)}")
    try:
        await run_conversation(agent, session)
        print(f"After conversation: {session.state.get(FOUNDRY_HOSTED_AGENT_SESSION_ID_KEY)}")
    finally:
        hosted_session_id = session.state.get(FOUNDRY_HOSTED_AGENT_SESSION_ID_KEY)
        if isinstance(hosted_session_id, str) and hosted_session_id:
            await project_client.agents.delete_session(agent_name, hosted_session_id)
            print(f"Deleted session: {hosted_session_id}")


async def run_user_managed_session(
    *,
    agent: FoundryAgent,
    project_client: AIProjectClient,
    agent_name: str,
    agent_version: str | None,
) -> None:
    """Create, attach, and delete a hosted-agent session explicitly."""
    resolved_agent_version = agent_version
    if resolved_agent_version is None:
        agent_details = await project_client.agents.get(agent_name)
        resolved_agent_version = agent_details.versions.latest.version

    hosted_session = await project_client.agents.create_session(
        agent_name,
        version_indicator=VersionRefIndicator(agent_version=resolved_agent_version),
    )
    session = AgentSession()
    session.state[FOUNDRY_HOSTED_AGENT_SESSION_ID_KEY] = hosted_session.agent_session_id

    print("\nUser-managed hosted-agent session")
    print(f"Created session: {hosted_session.agent_session_id}")
    try:
        await run_conversation(agent, session)
    finally:
        await project_client.agents.delete_session(agent_name, hosted_session.agent_session_id)
        print(f"Deleted session: {hosted_session.agent_session_id}")


async def main() -> None:
    credential = AzureCliCredential()
    project_endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
    agent_name = os.environ["FOUNDRY_AGENT_NAME"]
    agent_version = os.getenv("FOUNDRY_AGENT_VERSION")

    project_client = AIProjectClient(
        endpoint=project_endpoint,
        credential=credential,
        allow_preview=True,
    )
    async with (
        project_client,
        FoundryAgent(
            project_client=project_client,
            agent_name=agent_name,
            agent_version=agent_version,
            allow_preview=True,
        ) as agent,
    ):
        # Path 1: Let the service create the hosted-agent session on the first request,
        # then delete it when the conversation ends.
        await run_service_managed_session(
            agent=agent,
            project_client=project_client,
            agent_name=agent_name,
        )

        # Path 2: Create the hosted-agent session explicitly, attach its ID to AgentSession
        # state, and delete the hosted-agent session when the conversation ends.
        await run_user_managed_session(
            agent=agent,
            project_client=project_client,
            agent_name=agent_name,
            agent_version=agent_version,
        )


if __name__ == "__main__":
    asyncio.run(main())

"""
Sample output:
Service-managed hosted-agent session
Before first request: None
User: Hi!
Agent: Hello! How can I help you today?
User: Your name is Javis. What can you do?
Agent: I can answer questions and help with tasks using the instructions configured on the deployed agent.
User: What is your name?
Agent: My name is Javis.
After conversation: <service-created-session-id>
Deleted session: <service-created-session-id>

User-managed hosted-agent session
Created session: <user-created-session-id>
User: Hi!
Agent: Hello! How can I help you today?
User: Your name is Javis. What can you do?
Agent: I can answer questions and help with tasks using the instructions configured on the deployed agent.
User: What is your name?
Agent: My name is Javis.
Deleted session: <user-created-session-id>
"""
