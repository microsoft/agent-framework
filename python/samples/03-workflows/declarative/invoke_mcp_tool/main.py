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
  4. Optionally pause the MCP tool call for human approval. The YAML reads
     ``requireApproval`` from ``Workflow.Inputs.requireApproval`` so the
     host can flip the behaviour without editing the workflow definition.
     Set the ``MCP_REQUIRE_APPROVAL`` environment variable (``1`` / ``true``
     / ``yes``) to enable the approval flow; leave it unset for the
     "fire-and-forget" default.

Security note:
    ``DefaultMCPToolHandler`` connects to whatever MCP server URL the
    workflow author specifies and performs **no** allowlisting or SSRF
    guards. For production use, replace it with a custom handler that
    enforces an allowlist and adds any required authentication headers
    per server. MCP tool outputs flow back into agent conversations and
    therefore share the same prompt-injection risk surface as
    ``HttpRequestAction``: only invoke MCP servers you trust.

    The approval flow is also a defence-in-depth control: even with a
    trusted server, requiring human approval lets a reviewer inspect
    tool name, arguments, and outbound header NAMES (never values)
    before any network call is made.

Run with:
    python samples/03-workflows/declarative/invoke_mcp_tool/main.py

Run with approval prompts:
    MCP_REQUIRE_APPROVAL=1 python -m samples.03-workflows.declarative.invoke_mcp_tool.main
"""

import asyncio
import os
from pathlib import Path

from agent_framework import Agent
from agent_framework.declarative import (
    DefaultMCPToolHandler,
    MCPToolApprovalRequest,
    ToolApprovalResponse,
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

_TRUTHY = {"1", "true", "yes", "on"}


def _read_require_approval_flag() -> bool:
    """Return True when the MCP_REQUIRE_APPROVAL env var requests approval."""
    return os.environ.get("MCP_REQUIRE_APPROVAL", "").strip().lower() in _TRUTHY


def _prompt_for_approval(request: MCPToolApprovalRequest) -> ToolApprovalResponse:
    """Render the pending MCP call to stdout and read approve/reject from the user."""
    print()
    print("-" * 60)
    print("MCP tool approval required")
    print("-" * 60)
    print(f"  tool:         {request.tool_name}")
    print(f"  server label: {request.server_label or '(unset)'}")
    print(f"  server url:   {request.server_url}")
    if request.arguments:
        print("  arguments:")
        for key, value in request.arguments.items():
            print(f"    {key}: {value!r}")
    if request.header_names:
        # Only NAMES are surfaced; values are intentionally withheld because
        # they typically carry authentication secrets.
        print(f"  outbound header names: {', '.join(request.header_names)}")
    else:
        print("  outbound header names: (none)")
    print("-" * 60)

    while True:
        answer = input("Approve this MCP call? [y/N] ").strip().lower()  # noqa: ASYNC250
        if answer in {"y", "yes"}:
            return ToolApprovalResponse(approved=True)
        if answer in {"", "n", "no"}:
            reason = input("Reason for rejection (optional): ").strip()  # noqa: ASYNC250
            return ToolApprovalResponse(approved=False, reason=reason or None)
        print("Please answer 'y' or 'n'.")


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

    require_approval = _read_require_approval_flag()

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
        if require_approval:
            print("(MCP_REQUIRE_APPROVAL is set — you will be prompted before the tool runs)")
        else:
            print("(set MCP_REQUIRE_APPROVAL=1 to enable the human-approval flow)")
        print("=" * 60)
        print()
        print("Ask one question that can be answered from the Microsoft Learn docs or provide a keyword to search.")
        print()

        user_input = input("You: ").strip()  # noqa: ASYNC250
        if not user_input:
            user_input = "What is the Agent Framework declarative workflow runtime?"

        # Drive the workflow via dict-shaped inputs so the YAML can read
        # both the user's question (``Workflow.Inputs.text``) and the
        # approval toggle (``Workflow.Inputs.requireApproval``) without
        # any Python-side mutation of the workflow definition.
        workflow_inputs: dict[str, object] = {
            "text": user_input,
            "requireApproval": require_approval,
        }

        # The request_info loop below handles the MCP approval flow when
        # the YAML requests it. When ``requireApproval`` is false the
        # workflow never emits an ``MCPToolApprovalRequest`` event, so
        # the loop runs exactly once and exits cleanly — both modes share
        # the same code path.
        pending: tuple[str, MCPToolApprovalRequest] | None = None
        produced_output = False
        printed_agent_prefix = False

        while True:
            if pending is None:
                stream = workflow.run(workflow_inputs, stream=True)
            else:
                pending_id, pending_request = pending
                response = _prompt_for_approval(pending_request)
                stream = workflow.run(stream=True, responses={pending_id: response})
                pending = None

            async for event in stream:
                if event.type == "output" and isinstance(event.data, str):
                    if not printed_agent_prefix:
                        print("\nAgent: ", end="", flush=True)
                        printed_agent_prefix = True
                    print(event.data, end="", flush=True)
                    produced_output = True
                elif event.type == "request_info" and isinstance(event.data, MCPToolApprovalRequest):
                    pending = (event.request_id, event.data)

            if pending is None:
                if not produced_output:
                    # Workflow finished without producing any agent output
                    # (e.g. the user rejected the MCP tool call and the
                    # downstream agent had nothing to summarise).
                    print("\n(no response produced)")
                else:
                    print()
                break


if __name__ == "__main__":
    asyncio.run(main())
