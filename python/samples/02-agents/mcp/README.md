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
| **Progressive Disclosure** | [`mcp_progressive_disclosure.py`](mcp_progressive_disclosure.py) | Demonstrates `use_progressive_disclosure`, `always_load`, `allowed_tools`, and prefixed `list_mcp_tools` / `load_tool` / `unload_tool` names. `load_tool` and `unload_tool` can accept one tool name or multiple names. Self-spawns a stdio MCP child server |

The previous long-running Tasks sample was removed during the MCP 2.x migration.
Agent Framework does not currently implement the MCP Tasks extension because
the supported Python SDK does not yet expose that runtime. Future Tasks support
is tracked in [#9215](https://github.com/microsoft/agent-framework/issues/9215).

## Protocol behavior

- Framework-created connections use SDK auto negotiation: modern servers use
  `server/discover`, while older servers fall back to `initialize`.
- The high-level SDK client owns MRTR retries and modern server-directed
  response caching. Agent Framework owns catalog subscription recovery and
  refresh around the SDK's event stream.
- Caller-supplied `ClientSession` objects remain caller-owned, low-level, and
  uncached; they do not gain automatic MRTR.

## Prerequisites

Most samples in this folder use OpenAI:

- `OPENAI_API_KEY` environment variable
- `OPENAI_CHAT_MODEL` environment variable

Run `mcp_api_key_auth.py` with the MCP API key as the first command-line argument.

`mcp_progressive_disclosure.py` self-spawns its demo MCP stdio server; no separate MCP server setup is required.

For `mcp_github_pat.py`:
- `GITHUB_PAT` - Your GitHub Personal Access Token (create at https://github.com/settings/tokens)
