# Copyright (c) Microsoft. All rights reserved.

"""Invoke MCP Tool sample - demonstrates the InvokeMcpTool declarative action.

This sample shows how to:
  1. Configure a ``WorkflowFactory`` with a ``MCPToolHandler`` so the YAML
     ``InvokeMcpTool`` action can dispatch real MCP tool calls.
  2. Invoke a tool on a public unauthenticated MCP server (the Microsoft
     Learn Docs MCP server at ``https://learn.microsoft.com/api/mcp``,
     calling ``microsoft_docs_search``).
  3. Bind the parsed tool result to a workflow variable and mirror it into
     the conversation via ``conversationId`` so a downstream Foundry agent
     can answer questions using only that context.

Security note:
    ``DefaultMCPToolHandler`` connects to whatever MCP server URL the
    workflow author specifies and performs **no** allowlisting or SSRF
    guards. For production use, replace it with a custom handler that
    enforces an allowlist and adds any required authentication headers
    per server. MCP tool outputs flow back into agent conversations and
    therefore share the same prompt-injection risk surface as
    ``HttpRequestAction``: only invoke MCP servers you trust.

Run with:
    python -m samples.03-workflows.declarative.invoke_mcp_tool.main
"""

import asyncio
import os
from pathlib import Path

from agent_framework import Agent
from agent_framework.declarative import (
    DefaultMCPToolHandler,
    WorkflowFactory,
)
from agent_framework.foundry import FoundryChatClient
from azure.identity import AzureCliCredential

DOCS_AGENT_INSTRUCTIONS = """\
You answer the user's question about Microsoft technology using ONLY the
search results already present in the conversation history. If the answer is
not contained in the conversation, say so plainly rather than guessing. Be
concise and cite the relevant document title or URL when possible.
"""


async def main() -> None:
    """Run the invoke MCP tool workflow."""
    chat_client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["FOUNDRY_MODEL"],
        credential=AzureCliCredential(),
    )

    # The agent has no tools — it answers using only the search results that
    # ``InvokeMcpTool`` adds to the conversation.
    docs_agent = Agent(
        client=chat_client,
        name="DocsAgent",
        instructions=DOCS_AGENT_INSTRUCTIONS,
    )

    agents = {"DocsAgent": docs_agent}

    # The default MCPToolHandler is sufficient for this sample because the
    # Microsoft Learn Docs MCP server is public and unauthenticated. For
    # authenticated servers, supply a ``client_provider`` callback to route
    # requests through a pre-configured ``httpx.AsyncClient`` carrying the
    # appropriate credentials, or wrap the handler with one that injects
    # headers per call.
    async with DefaultMCPToolHandler() as mcp_handler:
        factory = WorkflowFactory(
            agents=agents,
            mcp_tool_handler=mcp_handler,
        )

        workflow_path = Path(__file__).parent / "workflow.yaml"
        workflow = factory.create_workflow_from_yaml_path(workflow_path)

        print("=" * 60)
        print("Invoke MCP Tool Workflow Demo")
        print("=" * 60)
        print()
        print("Ask one question that can be answered from the Microsoft Learn docs or provide a keyword to search.")
        print()

        user_input = input("You: ").strip()  # noqa: ASYNC250
        if not user_input:
            user_input = "What is the Agent Framework declarative workflow runtime?"

        print("\nAgent: ", end="", flush=True)
        async for event in workflow.run(user_input, stream=True):
            if event.type == "output" and isinstance(event.data, str):
                print(event.data, end="", flush=True)
        print()


if __name__ == "__main__":
    asyncio.run(main())
