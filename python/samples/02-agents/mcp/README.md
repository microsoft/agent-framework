# MCP (Model Context Protocol) Examples

This folder contains examples demonstrating how to work with MCP using Agent Framework.

## What is MCP?

The Model Context Protocol (MCP) is an open standard for connecting AI agents to data sources and tools. It enables secure, controlled access to local and remote resources through a standardized protocol.

## Examples

| Sample | File | Description |
|--------|------|-------------|
| **Agent as MCP Server** | [`agent_as_mcp_server.py`](agent_as_mcp_server.py) | Shows how to expose an Agent Framework agent as an MCP server that other AI applications can connect to |
| **API Key Authentication** | [`mcp_api_key_auth.py`](mcp_api_key_auth.py) | Demonstrates API key authentication with MCP servers |
| **GitHub Integration with PAT (OpenAI Responses)** | [`mcp_github_pat_openai_responses.py`](mcp_github_pat_openai_responses.py) | Demonstrates connecting to GitHub's MCP server using PAT with OpenAI Responses Client |
| **GitHub Integration with PAT (Azure OpenAI)** | [`mcp_github_pat_azure_chat.py`](mcp_github_pat_azure_chat.py) | Demonstrates connecting to GitHub's MCP server using PAT with Azure OpenAI Chat Client |

## Prerequisites

Each sample requires its own set of environment variables. See below for details.

For `mcp_github_pat_openai_responses.py`:
- `GITHUB_PAT` - Your GitHub Personal Access Token (create at https://github.com/settings/tokens)
- `OPENAI_API_KEY` - Your OpenAI API key
- `OPENAI_RESPONSES_MODEL_ID` - Your OpenAI model ID

For `mcp_github_pat_azure_chat.py`:
- `GITHUB_PAT` - Your GitHub Personal Access Token (create at https://github.com/settings/tokens)
- `AZURE_OPENAI_ENDPOINT` - Your Azure OpenAI endpoint
- `AZURE_OPENAI_CHAT_DEPLOYMENT_NAME` - Your Azure OpenAI chat deployment name
- Or use Azure CLI credential for authentication (run `az login`)
