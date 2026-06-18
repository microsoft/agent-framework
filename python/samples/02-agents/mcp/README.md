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
| **Sampling Approval** | [`mcp_sampling_approval.py`](mcp_sampling_approval.py) | Demonstrates gating server-initiated `sampling/createMessage` requests with a `sampling_approval_callback`, plus the `sampling_max_tokens` and `sampling_max_requests` guardrails. MCP sampling is denied by default |

## Prerequisites

Most samples in this folder use OpenAI:

- `OPENAI_API_KEY` environment variable
- `OPENAI_CHAT_MODEL` environment variable

Run `mcp_api_key_auth.py` with the MCP API key as the first command-line argument.

For `mcp_github_pat.py`:
- `GITHUB_PAT` - Your GitHub Personal Access Token (create at https://github.com/settings/tokens)

For `mcp_long_running_task.py` (uses Azure OpenAI via Entra-ID):
- Run `az login` once
- `AZURE_OPENAI_ENDPOINT` - your Azure OpenAI resource endpoint, e.g. `https://<resource>.openai.azure.com/`
- `AZURE_OPENAI_CHAT_MODEL` (or `AZURE_OPENAI_MODEL`) - the deployment name (e.g. `gpt-4o-mini`)
