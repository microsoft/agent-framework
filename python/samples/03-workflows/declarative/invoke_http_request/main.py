# Copyright (c) Microsoft. All rights reserved.

"""Invoke HTTP Request sample - demonstrates the HttpRequestAction declarative action.

This sample shows how to:
  1. Configure a ``WorkflowFactory`` with a ``HttpRequestHandler`` so the YAML
     ``HttpRequestAction`` can dispatch real HTTP calls.
  2. Fetch JSON from a public REST endpoint (the GitHub repository API) and
     bind the parsed response to a workflow variable.
  3. Mirror the response body into the conversation via ``conversationId`` so
     a downstream Foundry agent can answer questions about it using only that
     conversation context.

Security note:
    ``DefaultHttpRequestHandler`` issues HTTP calls to whatever URL the
    workflow author specifies and performs **no** allowlisting or SSRF
    guards. For production use, replace it with a custom handler that
    enforces an allowlist or DNS-rebinding-resistant policy and adds any
    required authentication headers per call.

Run with:
    python -m samples.03-workflows.declarative.invoke_http_request.main
"""

import asyncio
import os
from pathlib import Path

from agent_framework import Agent
from agent_framework.declarative import (
    DefaultHttpRequestHandler,
    WorkflowFactory,
)
from agent_framework.foundry import FoundryChatClient
from azure.identity import AzureCliCredential

GITHUB_REPO_INFO_AGENT_INSTRUCTIONS = """\
You answer the user's question about a GitHub repository using ONLY the JSON
data already present in the conversation history. If the answer is not
contained in the conversation, say so plainly rather than guessing. Be concise
and helpful.
"""


async def main() -> None:
    """Run the invoke HTTP request workflow."""
    chat_client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["FOUNDRY_MODEL"],
        credential=AzureCliCredential(),
    )

    # The agent has no tools — it answers the question about the GitHub
    # repository using only the JSON data that ``HttpRequestAction`` adds to
    # the conversation.
    github_repo_info_agent = Agent(
        client=chat_client,
        name="GitHubRepoInfoAgent",
        instructions=GITHUB_REPO_INFO_AGENT_INSTRUCTIONS,
    )

    agents = {"GitHubRepoInfoAgent": github_repo_info_agent}

    # The default HttpRequestHandler is sufficient for this sample because
    # the GitHub REST endpoint used here does not require authentication.
    # For authenticated endpoints, supply a custom client_provider callback
    # to DefaultHttpRequestHandler so each request can be routed through a
    # pre-configured httpx.AsyncClient with the appropriate credentials.
    async with DefaultHttpRequestHandler() as http_handler:
        factory = WorkflowFactory(
            agents=agents,
            http_request_handler=http_handler,
        )

        workflow_path = Path(__file__).parent / "workflow.yaml"
        workflow = factory.create_workflow_from_yaml_path(workflow_path)

        print("=" * 60)
        print("Invoke HTTP Request Workflow Demo")
        print("=" * 60)
        print()
        print("Ask one question about the microsoft/agent-framework repo.")
        print()

        user_input = input("You: ").strip()  # noqa: ASYNC250
        if not user_input:
            user_input = "Please summarize the repository."

        print("\nAgent: ", end="", flush=True)
        async for event in workflow.run(user_input, stream=True):
            if event.type == "output" and isinstance(event.data, str):
                print(event.data, end="", flush=True)
        print()


if __name__ == "__main__":
    asyncio.run(main())
