# Agent Streaming with Azure SignalR Service

This sample demonstrates how to stream durable agent responses to web clients in real time using Azure SignalR Service. The agent processes requests via Azure Functions with durable orchestration, and each streaming chunk is pushed to the browser through SignalR groups for user isolation.

![Demo](./az_func_signalr_demo.gif)

## Key Concepts Demonstrated

- `AgentResponseCallbackProtocol` to capture streaming agent responses
- Real-time delivery of streaming chunks via Azure SignalR Service REST API
- **Multi-user isolation** using SignalR user-targeted messaging (each client only receives its own messages)
- Custom SignalR negotiation endpoint with user identity embedded via `nameid` JWT claim
- Automatic reconnection support using the SignalR JavaScript client
- Durable agent execution with streaming callbacks
- Multi-turn conversation continuity

## Prerequisites

1. **Azure SignalR Service** — Create a SignalR Service instance in Azure (Serverless mode). There is no local emulator.
2. **Azure Functions Core Tools** — [Install Core Tools 4.x](https://learn.microsoft.com/azure/azure-functions/functions-run-local)
3. **Azurite** — [Install the storage emulator](https://learn.microsoft.com/azure/storage/common/storage-install-azurite)
4. **Azure OpenAI** — An Azure OpenAI resource with a chat model deployment
5. **Azure CLI** — Logged in via `az login` for `AzureCliCredential`

## Setup

### 1. Create and activate a virtual environment

```bash
python -m venv .venv
source .venv/bin/activate   # Linux/macOS
# .venv\Scripts\Activate.ps1  # Windows PowerShell
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure settings

Copy `local.settings.json.template` to `local.settings.json` and fill in:

- `AZURE_OPENAI_ENDPOINT` — Your Azure OpenAI endpoint
- `AZURE_OPENAI_CHAT_DEPLOYMENT_NAME` — Your chat model deployment name
- `AzureSignalRConnectionString` — Your Azure SignalR Service connection string
- `SIGNALR_HUB_NAME` — Hub name (defaults to `travel`)

The sample uses `AzureCliCredential` by default. Alternatively, set `AZURE_OPENAI_API_KEY` for API key authentication.

### 4. Start Azurite

```bash
azurite --silent
```

## Running the Sample

### 1. Start the Azure Functions host

```bash
func start
```

The function app starts on `http://localhost:7071`.

### 2. Open the web interface

Navigate to `http://localhost:7071/api/index` in your browser. The page automatically:

- Connects to Azure SignalR Service via the `/api/agent/negotiate` endpoint
- Displays the connection status (Connected / Disconnected)
- Enables the chat interface

### 3. Send a message

Type a travel planning request, for example:

```text
Plan a 3-day trip to Singapore
```

Click **Send** (or press Enter). The agent:

- Executes in the background via durable orchestration
- Streams responses in real time as they are generated

### 4. Continue the conversation

The client maintains the `thread_id` across messages for multi-turn conversation:

```text
Include neighbouring countries as well
```

## API Endpoints

| Method | Route | Description |
|--------|-------|-------------|
| POST | `/api/agents/TravelPlanner/run?thread_id=<id>` | Start or continue an agent conversation |
| GET/POST | `/api/agent/negotiate` | SignalR negotiation (pass `x-user-id` header) |
| POST | `/api/agent/create-thread` | Create a `thread_id` and register the user mapping (pass `x-user-id` header) |
| GET | `/api/index` | Serve the web interface |

## How It Works

### Flow

```
Client          Functions        SignalR Service      Agent
  │                │                   │                │
  │ negotiate      │                   │                │
  │ (x-user-id)    │                   │                │
  │───────────────>│                   │                │
  │<─ url+token ───│  (nameid claim    │                │
  │                │   = user_id)      │                │
  │                │                   │                │
  │ connect(token) │                   │                │
  │────────────────────────────────────>│                │
  │                │                   │                │
  │ create-thread  │                   │                │
  │ (x-user-id)    │                   │                │
  │───────────────>│  stores mapping   │                │
  │<─ thread_id ───│  thread→user      │                │
  │                │                   │                │
  │ run (thread_id)│                   │                │
  │───────────────>│──────────────────────────────────>│
  │<─ 202 accepted │                   │                │
  │                │                   │   streaming    │
  │                │                   │<───────────────│
  │  agentMessage  │<── to user ───────│                │
  │<───────────────│                   │                │
  │  agentDone     │<── to user ───────│                │
  │<───────────────│                   │                │
```

### User Isolation

1. **Client generates a user ID** — stored in `sessionStorage` for the browser tab lifetime.
2. **Negotiate** — The client sends `x-user-id` header; the server embeds it as a `nameid` claim in the JWT so SignalR binds the connection to that user.
3. **Thread creation** — The client sends `x-user-id` when creating a thread; the server stores a `thread_id → user_id` mapping.
4. **Streaming** — The `SignalRCallback` looks up the `user_id` for the `thread_id` and sends messages via the `/users/{userId}` REST API path.

This ensures:

- Each user only sees their own conversation
- No groups or group-join race conditions
- Multiple users can use the app simultaneously without interference
- Works correctly across page refreshes within the same tab
