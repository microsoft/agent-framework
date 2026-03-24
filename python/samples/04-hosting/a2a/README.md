# A2A Agent Examples

This sample demonstrates how to host and consume agents using the [A2A (Agent2Agent) protocol](https://a2a-protocol.org/latest/) with the `agent_framework` package. There are two runnable entry points:

| Run this file | To... |
|---------------|-------|
| **[`a2a_server.py`](a2a_server.py)** | Host an Agent Framework agent as an A2A-compliant server. |
| **[`agent_with_a2a.py`](agent_with_a2a.py)** | Connect to an A2A server and send requests (non-streaming and streaming). |

The remaining files are supporting modules used by the server:

| File | Description |
|------|-------------|
| [`agent_definitions.py`](agent_definitions.py) | Agent and AgentCard factory definitions for invoice, policy, and logistics agents. |
| [`agent_executor.py`](agent_executor.py) | Bridges the a2a-sdk `AgentExecutor` interface to Agent Framework agents. |
| [`invoice_data.py`](invoice_data.py) | Mock invoice data and tool functions for the invoice agent. |
| [`a2a_server.http`](a2a_server.http) | REST Client requests for testing the server directly from VS Code. |

## Environment Variables

Make sure to set the following environment variables before running the examples:

### Required (Server)
- `AZURE_AI_PROJECT_ENDPOINT` — Your Azure AI Foundry project endpoint
- `AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME` — Model deployment name (e.g. `gpt-4o`)

### Required (Client)
- `A2A_AGENT_HOST` — URL of the A2A server (e.g. `http://localhost:5001/`)

## Quick Start

All commands below should be run from this directory:

```powershell
cd python/samples/04-hosting/a2a
```

### 1. Start the A2A Server

Pick an agent type and start the server (each in its own terminal):

```powershell
uv run python a2a_server.py --agent-type invoice --port 5000
uv run python a2a_server.py --agent-type policy --port 5001
uv run python a2a_server.py --agent-type logistics --port 5002
```

You can run one agent or all three — each listens on its own port.

### 2. Run the A2A Client

In a separate terminal (from the same directory), point the client at a running server:

```powershell
$env:A2A_AGENT_HOST = "http://localhost:5001/"
uv run python agent_with_a2a.py
```
