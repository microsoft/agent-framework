# A2A Server Hosting Examples

This sample demonstrates how to **host** Agent Framework agents as A2A-compliant servers using the [A2A (Agent2Agent) protocol](https://a2a-protocol.org/latest/).

> **Looking for client samples?** See [`samples/02-agents/a2a/`](../../02-agents/a2a/) for consuming remote A2A agents.

## Server Samples

| Run this file | To... |
|---------------|-------|
| **[`a2a_server.py`](a2a_server.py)** | Host an Agent Framework agent as an A2A-compliant server (multi-agent). |
| **[`agent_framework_to_a2a.py`](agent_framework_to_a2a.py)** | Minimal example: expose a single agent as an A2A server. |

## Supporting Modules

| File | Description |
|------|-------------|
| [`agent_definitions.py`](agent_definitions.py) | Agent and AgentCard factory definitions for invoice, policy, and logistics agents. |
| [`invoice_data.py`](invoice_data.py) | Mock invoice data and tool functions for the invoice agent. |
| [`a2a_server.http`](a2a_server.http) | REST Client requests for testing the server directly from VS Code. |

## Environment Variables

### Required (Server)
- `FOUNDRY_PROJECT_ENDPOINT` — Your Azure AI Foundry project endpoint
- `FOUNDRY_MODEL` — Model deployment name (e.g. `gpt-4o`)

## Quick Start

All commands below should be run from this directory:

```powershell
cd python/samples/04-hosting/a2a
```

### 0. Install Dependencies

Copy `.env.example` to `.env` and fill in your values:

```powershell
copy .env.example .env
```

**Option A — pip (standard):**

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1      # Windows
# source .venv/bin/activate     # macOS / Linux
pip install -r requirements.txt
```

**Option B — uv:**

```powershell
uv run python a2a_server.py --agent-type policy
```

### 1. Start the A2A Server

> **Note (Option A — pip users):** Replace `uv run python` with `python` in all `uv run` commands below. `uv` is not required once the virtual environment is activated.

Pick an agent type and start the server (each in its own terminal):

```powershell
uv run python a2a_server.py --agent-type invoice --port 5000
uv run python a2a_server.py --agent-type policy --port 5001
uv run python a2a_server.py --agent-type logistics --port 5002
```

You can run one agent or all three — each listens on its own port.

### 2. Run a Client

Once a server is running, use any of the client samples in [`samples/02-agents/a2a/`](../../02-agents/a2a/):

```powershell
cd python/samples/02-agents/a2a
$env:A2A_AGENT_HOST = "http://localhost:5001/"
uv run python agent_with_a2a.py
```
