# MCP (Model Context Protocol) Examples

This folder contains examples demonstrating how to work with MCP using Agent Framework.

## What is MCP?

The Model Context Protocol (MCP) is an open standard for connecting AI agents to data sources and tools. It enables secure, controlled access to local and remote resources through a standardized protocol.

## Examples

| Sample | File | Description |
|--------|------|-------------|
| **Agent as MCP Server** | [`agent_as_mcp_server.py`](agent_as_mcp_server.py) | Shows how to expose an Agent Framework agent as an MCP server that other AI applications can connect to |
| **API Key Authentication** | [`mcp_api_key_auth.py`](mcp_api_key_auth.py) | Demonstrates API key authentication with MCP servers using `header_provider`, runtime invocation kwargs, and a command-line API key argument |
| **GitHub Integration with PAT** | [`mcp_github_pat.py`](mcp_github_pat.py) | Demonstrates connecting to GitHub's MCP server using Personal Access Token (PAT) authentication |
| **Long-Running Task** | [`mcp_long_running_task.py`](mcp_long_running_task.py) | Demonstrates transparent SEP-2663 long-running task handling for MCP tools that advertise `taskSupport=required`. Self-spawns a stdio MCP child server |
| **Progressive Disclosure** | [`mcp_progressive_disclosure.py`](mcp_progressive_disclosure.py) | Demonstrates `use_progressive_disclosure`, `always_load`, `allowed_tools`, and prefixed `list_mcp_tools` / `load_tool` / `unload_tool` names. `load_tool` and `unload_tool` can accept one tool name or multiple names. Self-spawns a stdio MCP child server |
| **Sampling Approval** | [`mcp_sampling_approval.py`](mcp_sampling_approval.py) | Demonstrates gating server-initiated `sampling/createMessage` requests with a `sampling_approval_callback`, plus the `sampling_max_tokens` and `sampling_max_requests` guardrails. MCP sampling is denied by default |

## Anonymous web search and fetch

Use `MCPStreamableHTTPTool` with [Parallel Search MCP](https://docs.parallel.ai/integrations/mcp/search-mcp) to search the public web and extract page content. This example calls the tools directly, so it needs neither a Parallel API key nor a model provider account. Free access is rate limited.

Install the client dependencies in a Python 3.10+ environment:

```bash
pip install agent-framework-core "mcp>=1.24,<2"
```

Save this as `parallel_search.py` and run `python parallel_search.py`:

```python
import asyncio
from uuid import uuid4

from agent_framework import MCPStreamableHTTPTool


async def main() -> None:
    session_id = str(uuid4())  # Reuse for related search and fetch calls.
    async with MCPStreamableHTTPTool(
        name="parallel-search",
        url="https://search.parallel.ai/mcp",
        load_prompts=False,
        request_timeout=30,
        # Use the text payload once; Parallel also returns it as structured content.
        parse_tool_results=lambda result: "\n".join(c.text for c in result.content if c.type == "text"),
    ) as mcp:
        print("Tools:", [tool.name for tool in mcp.functions])
        search_result = await mcp.call_tool(
            "web_search",
            objective="Find Microsoft Agent Framework MCP documentation",
            search_queries=["Microsoft Agent Framework MCP tools"],
            session_id=session_id,
        )
        fetch_result = await mcp.call_tool(
            "web_fetch",
            urls=["https://github.com/microsoft/agent-framework"],
            objective="Describe the framework's MCP support",
            session_id=session_id,
        )
        for result in (search_result, fetch_result):
            print(result)


if __name__ == "__main__":
    asyncio.run(main())
```

The output lists `web_search` and `web_fetch`, followed by their results, including source URLs and excerpts. Queries, requested URLs, objectives, and the session identifier are sent to Parallel when the calls run. The context manager closes the connection afterward.

To make these tools available to an existing agent, pass the MCP tool as `tools` when constructing `Agent`. The agent can then choose to invoke them during a run; remove that tool to disable access. This example does not change any configured providers or defaults.

## Prerequisites

Most samples in this folder use OpenAI:

- `OPENAI_API_KEY` environment variable
- `OPENAI_CHAT_MODEL` environment variable

Run `mcp_api_key_auth.py` with the MCP API key as the first command-line argument.

`mcp_progressive_disclosure.py` self-spawns its demo MCP stdio server; no separate MCP server setup is required.

For `mcp_github_pat.py`:
- `GITHUB_PAT` - Your GitHub Personal Access Token (create at https://github.com/settings/tokens)

For `mcp_long_running_task.py` (uses Azure OpenAI via Entra-ID):
- Run `az login` once
- `AZURE_OPENAI_ENDPOINT` - your Azure OpenAI resource endpoint, e.g. `https://<resource>.openai.azure.com/`
- `AZURE_OPENAI_CHAT_MODEL` (or `AZURE_OPENAI_MODEL`) - the deployment name (e.g. `gpt-4o-mini`)
