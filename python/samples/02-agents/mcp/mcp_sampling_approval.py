# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework import Agent, MCPStreamableHTTPTool
from agent_framework.openai import OpenAIChatClient
from dotenv import load_dotenv
from mcp import types

# Load environment variables from .env file
load_dotenv()

"""
MCP Sampling Approval Example

MCP servers can send the client a ``sampling/createMessage`` request, asking the
client to run an LLM completion on the server's behalf. Because remote MCP
servers are untrusted third parties, forwarding these server-controlled prompts
to your chat client without review is a confused-deputy risk: a malicious server
could exfiltrate context, force tool calls, or burn through your token budget.

For that reason Agent Framework **denies MCP sampling by default**. To allow it,
pass a ``sampling_approval_callback`` to the MCP tool. The callback receives the
raw ``CreateMessageRequestParams`` and returns ``True`` to approve or ``False``
to deny. It may be synchronous or asynchronous, so you can implement a
human-in-the-loop prompt, a policy check, or an audit log.

Two further guardrails apply to approved requests:
- ``sampling_max_tokens`` caps the server-requested ``maxTokens``.
- ``sampling_max_requests`` limits how many sampling requests a single session
  may make.

To restore the legacy "always approve" behavior (only do this for servers you
trust), pass ``sampling_approval_callback=lambda params: True``.
"""


async def approve_sampling(params: types.CreateMessageRequestParams) -> bool:
    """Human-in-the-loop approval gate for server-initiated sampling.

    Shows the server-supplied system prompt and messages, then asks the user to
    approve or deny. Returning ``False`` rejects the request.
    """
    print("\n--- MCP server requested a sampling/createMessage ---")
    if params.systemPrompt:
        print(f"System prompt: {params.systemPrompt}")
    for message in params.messages:
        text = getattr(message.content, "text", message.content)
        print(f"{message.role}: {text}")
    answer = await asyncio.to_thread(input, "Approve this sampling request? [y/N]: ")
    return answer.strip().lower() in {"y", "yes"}


async def main() -> None:
    """Run an agent against an MCP server with a sampling approval gate."""
    async with Agent(
        client=OpenAIChatClient(),
        name="Agent",
        instructions="You are a helpful assistant. Use your MCP tool when answering the user's question.",
        tools=MCPStreamableHTTPTool(
            name="MCP tool",
            description="MCP tool description.",
            url="<your mcp server url>",
            # Passing ``client`` enables sampling; the approval callback gates it.
            client=OpenAIChatClient(),
            sampling_approval_callback=approve_sampling,
            sampling_max_tokens=2048,
            sampling_max_requests=5,
        ),
    ) as agent:
        query = "Use your MCP tool to help answer this question."
        print(f"User: {query}")
        result = await agent.run(query)
        print(f"Agent: {result.text}")


if __name__ == "__main__":
    asyncio.run(main())
