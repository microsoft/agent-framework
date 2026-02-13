# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os

from agent_framework.azure import AzureOpenAIResponsesClient
from azure.identity import AzureCliCredential

"""
Host Your Agent — Minimal A2A hosting stub

This sample shows the pattern for exposing an agent via the Agent-to-Agent
(A2A) protocol. It creates the agent and demonstrates how to wrap it with
the A2A hosting layer.

Prerequisites:
  pip install agent-framework[a2a] --pre

Environment variables:
  AZURE_AI_PROJECT_ENDPOINT        — Your Azure AI Foundry project endpoint
  AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME — Model deployment name (e.g. gpt-4o)

To run a full A2A server, see samples/04-hosting/a2a/ for a complete example.
"""


async def main() -> None:
    # <create_agent>
    credential = AzureCliCredential()
    client = AzureOpenAIResponsesClient(
        project_endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
        deployment_name=os.environ["AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME"],
        credential=credential,
    )

    agent = client.as_agent(
        name="HostedAgent",
        instructions="You are a helpful assistant exposed via A2A.",
    )
    # </create_agent>

    # <host_agent>
    # The A2A hosting integration wraps your agent behind an HTTP endpoint.
    # Import is gated so this sample can run without the a2a extra installed.
    try:
        from agent_framework.a2a import A2AAgent  # noqa: F401

        print("A2A support is available.")
        print("See samples/04-hosting/a2a/ for a runnable A2A server example.")
    except ImportError:
        print("Install a2a extras: pip install agent-framework[a2a] --pre")

    # Quick smoke-test: run the agent locally to verify it works
    result = await agent.run("Hello! What can you do?")
    print(f"Agent: {result}")
    # </host_agent>


if __name__ == "__main__":
    asyncio.run(main())
