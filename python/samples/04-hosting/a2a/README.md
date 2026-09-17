# A2A Server Hosting Examples

This sample demonstrates how to **host** Agent Framework agents as A2A-compliant servers using the [A2A (Agent2Agent) protocol](https://a2a-protocol.org/latest/).

`agent-framework-hosting-a2a` only converts between native A2A values and
Agent Framework run values. The sample deliberately keeps the A2A SDK's
`AgentExecutor`, task lifecycle, event queue, task store, and Starlette routes
in application code. The helper package does not choose a web framework.

> **Looking for client samples?** See [`samples/02-agents/a2a/`](../../02-agents/a2a/) for consuming remote A2A agents.

## Server Samples

| Run this file | To... |
|---------------|-------|
| **[`a2a_server.py`](a2a_server.py)** | Host an Agent Framework agent as an A2A-compliant server (multi-agent). |
| **[`agent_framework_to_a2a.py`](agent_framework_to_a2a.py)** | Expose a single agent with conversion helpers and a native `AgentCard` inferred from agent and skill metadata; the A2A server remains application-owned. |

## Supporting Modules

| File | Description |
|------|-------------|
| [`agent_definitions.py`](agent_definitions.py) | Agent and AgentCard factory definitions for invoice, policy, and logistics agents. |
| [`invoice_data.py`](invoice_data.py) | Mock invoice data and tool functions for the invoice agent. |
| [`a2a_server.http`](a2a_server.http) | REST Client requests for testing the server directly from VS Code. |

## Environment Variables

### Required (Server)
- `FOUNDRY_PROJECT_ENDPOINT` — Your Microsoft Foundry project endpoint
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

## Security considerations for multi-tenant hosting

These runnable samples intentionally configure no authentication or
authorization. Their `context.tenant`, `context.context_id`, and task IDs come
from protocol requests and are not trusted caller identities. Do not expose the
sample servers as multi-user services without an authenticated outer server,
middleware layer, or gateway.

A production host must authenticate the caller before the A2A request handler,
derive a trusted tenant and subject from that authentication context, authorize
all task/context continuation and cancellation IDs, and bind Agent Framework
session ownership to that trusted identity. The sample session key is only a
protocol-level demonstration; it is not sufficient isolation on its own.

The default `a2a-sdk` task/push-config stores scope ownership by `user_name`
only. A multi-tenant host must also pass an `owner_resolver` that uses the same
trusted tenant and subject to its stores, for example:

```python
from a2a.server.tasks import InMemoryTaskStore

def resolve_tenant_user_scope(context):
    # These values must be populated from the outer server's trusted auth context.
    return f"{context.tenant}:{context.user.user_name}"
task_store = InMemoryTaskStore(owner_resolver=resolve_tenant_user_scope)
```

Production applications must also use a durable session store when running
multiple replicas or transient workers.
