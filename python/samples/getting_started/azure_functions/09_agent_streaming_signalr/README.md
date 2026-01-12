# Agent Response Callbacks with Azure SignalR

This sample demonstrates how to use Azure SignalR Service with agent response callbacks to enable real-time streaming for durable agents. The agent streams responses directly to connected web clients as the agent generates them.

## Key Concepts Demonstrated

- Using `AgentResponseCallbackProtocol` to capture streaming agent responses
- Real-time delivery of streaming chunks via Azure SignalR Service REST API
- Custom SignalR negotiation endpoint for browser client authentication
- Automatic reconnection support using SignalR JavaScript client
- Durable agent execution with streaming callbacks
- Conversation continuity across multiple messages
- **User isolation** - Each user only receives messages for their own conversation via SignalR groups

## Prerequisites

1. **Azure SignalR Service** - Create a SignalR Service instance in Azure (Serverless mode)
2. **Azure Functions Core Tools** - For local development
3. **Azure OpenAI** - Configured for agent model

Update `local.settings.json` with your configuration:

```json
{
  "Values": {
    "FUNCTIONS_WORKER_RUNTIME": "python",
    "AzureWebJobsStorage": "UseDevelopmentStorage=true",
    "DURABLE_TASK_SCHEDULER_CONNECTION_STRING": "Endpoint=http://localhost:8080;TaskHub=default;Authentication=None",
    "TASKHUB_NAME": "default",
    "AZURE_OPENAI_ENDPOINT": "<AZURE_OPENAI_ENDPOINT>",
    "AZURE_OPENAI_API_KEY": "<AZURE_OPENAI_API_KEY>",
    "AZURE_OPENAI_CHAT_DEPLOYMENT_NAME":  "<AZURE_OPENAI_CHAT_DEPLOYMENT_NAME>",
    "AzureSignalRConnectionString": "Endpoint=https://<your-signalr>.service.signalr.net;AccessKey=<your-key>;Version=1.0;ServiceMode=Serverless;",
    "SIGNALR_HUB_NAME": "travel",
  }
}
```

**Note:** There is no local SignalR emulation. You must use a deployed Azure SignalR Service instance.

## Running the Sample

### 1. Start the Azure Functions host

```bash
func start
```

The function app will start on `http://localhost:7071`

### 2. Open the web interface

Navigate to `http://localhost:7071/api/index` in your browser. The page will automatically:

- Connect to Azure SignalR Service via the `/api/agent/negotiate` endpoint
- Display the connection status (Connected/Disconnected)
- Enable the chat interface

Screenshot

### 3. Send a message to the agent

Type a travel planning request in the input box, for example:

```text
Plan a 3-day trip to Singapore
```

Click "Send" or press Enter. The agent will:

- Execute in the background via durable orchestration
- Stream responses in real-time as they're generated

### 4. Continue the conversation

The client maintains the `conversationId` (thread_id) across messages, so you can have a multi-turn conversation:

```text
Include neighbouring countries as well
```

The agent will have context from previous messages in the same conversation.

## API Endpoints

### POST `/api/agents/TravelPlanner/run`

Start or continue an agent conversation.

**Query Parameters:**

- `thread_id` (required for user isolation) - Conversation ID obtained from `/api/agent/create-thread`

**Headers:**

- `Content-Type: text/plain` - Plain text prompt
- `X-Wait-For-Response: false` - Return immediately without waiting for agent response

**Request Body:** Plain text prompt

```text
Plan a 3-day trip to Singapore
```

**Response (202 Accepted):**

```json
{
  "message": "Plan a 3-day trip to Singapore",
  "thread_id": "a1b2c3d4e5f6789012345678901234ab",
  "correlation_id": "f8e7d6c5b4a39281...",
  "status": "accepted"
}
```

### GET/POST `/api/agent/negotiate`

SignalR negotiation endpoint for browser clients.

**Response (200 OK):**

```json
{
  "url": "https://<your-signalr>.service.signalr.net/client/?hub=travel",
  "accessToken": "<jwt-token>"
}
```

### GET `/api/index`

Serves the web interface (index.html).

### POST `/api/agent/create-thread`

Create a new thread_id before starting a conversation. This is required for user isolation - the client must join a SignalR group before the agent starts streaming.

**Response (200 OK):**

```json
{
  "thread_id": "a1b2c3d4e5f6789012345678901234ab"
}
```

> **Note:** The agent framework auto-generates thread_ids, but we create one upfront so the client can join the SignalR group before sending messages, avoiding a race condition where messages stream before the client is subscribed.

### POST `/api/agent/join-group`

Add a SignalR connection to a conversation group for user isolation.

**Request Body:**

```json
{
  "group": "<thread_id>",
  "connectionId": "<signalr_connection_id>"
}
```

**Response (200 OK):**

```json
{
  "status": "joined",
  "group": "<thread_id>"
}
```

## How It Works

### 1. SignalR Service Client

A custom `SignalRServiceClient` class communicates with Azure SignalR Service via REST API:

```python
class SignalRServiceClient:
    def __init__(self, connection_string: str, hub_name: str):
        # Parse connection string for endpoint and access key
        self._endpoint = ...
        self._access_key = ...
        self._hub_name = hub_name
    
    async def send(self, *, target: str, arguments: list, group: str | None = None):
        # Generate JWT token for authentication
        token = self._generate_token(url)
        
        # POST message to SignalR REST API
        # Broadcasts to all connected clients
        async with session.post(url, headers={...}, json={...}):
            ...
```

### 2. SignalR Callback

`SignalRCallback` implements `AgentResponseCallbackProtocol` to capture streaming updates:

```python
class SignalRCallback(AgentResponseCallbackProtocol):
    async def on_streaming_response_update(self, update, context):
        # Send each chunk to the specific conversation group
        await self._client.send(
            target="agentMessage",
            arguments=[{
                "conversationId": context.thread_id,
                "correlationId": context.correlation_id,
                "text": update.text
            }],
            group=context.thread_id  # User isolation via groups
        )
    
    async def on_agent_response(self, response, context):
        # Notify completion to the specific group
        await self._client.send(
            target="agentDone",
            arguments=[{
                "conversationId": context.thread_id,
                "status": "completed"
            }],
            group=context.thread_id  # User isolation via groups
        )
```

The callback is configured as the default callback in the AgentFunctionApp.

### 3. Negotiate Endpoint

The `/api/agent/negotiate` endpoint provides SignalR connection info for browser clients:

```python
@app.route(route="agent/negotiate", methods=["POST", "GET"])
def negotiate(req):
    # Build client URL for the SignalR hub
    client_url = f"{base_url}/client/?hub={SIGNALR_HUB_NAME}"
    
    # Generate JWT token for client authentication
    access_token = signalr_client._generate_token(client_url)
    
    return {
        "url": client_url,
        "accessToken": access_token
    }
```

### 4. Browser Client

The client uses the SignalR JavaScript library with user isolation:

```javascript
// Get connection info from negotiate endpoint
const { url, accessToken } = await fetch('/api/agent/negotiate').then(r => r.json());

// Connect to SignalR
const connection = new signalR.HubConnectionBuilder()
    .withUrl(url, { accessTokenFactory: () => accessToken })
    .withAutomaticReconnect()
    .build();

// Listen for streaming messages
connection.on('agentMessage', (data) => {
    // Append text chunk to UI
    updateAgentMessage(data.text);
});

// Listen for completion
connection.on('agentDone', (data) => {
    // Enable input, clear typing indicator
    isAgentProcessing = false;
});

await connection.start();

// Before sending the first message, create thread and join group
async function sendMessage(message) {
    if (!conversationId) {
        // 1. Get thread_id from server
        const { thread_id } = await fetch('/api/agent/create-thread', { method: 'POST' })
            .then(r => r.json());
        conversationId = thread_id;
        
        // 2. Join the SignalR group for this thread
        await fetch('/api/agent/join-group', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                group: conversationId,
                connectionId: connection.connectionId
            })
        });
    }
    
    // 3. Now send message - agent will stream to this group
    await fetch(`/api/agents/TravelPlanner/run?thread_id=${conversationId}`, {
        method: 'POST',
        body: message
    });
}
```

### 5. Thread Management and User Isolation

The sample implements user isolation using SignalR groups:

1. **Thread Creation**: Before the first message, client requests a `thread_id` from `/api/agent/create-thread`
2. **Group Joining**: Client joins a SignalR group named after the `thread_id` via `/api/agent/join-group`
3. **Message Sending**: Client sends message with `thread_id` query parameter
4. **Streaming**: Agent callback sends messages to the `thread_id` group, not broadcast

This ensures:

- Each user only sees their own conversation
- No race condition between message sending and group subscription
- Multiple users can use the app simultaneously without interference

```
┌─────────┐      ┌──────────┐      ┌─────────────┐      ┌─────────┐
│ Client  │      │ Functions│      │   SignalR   │      │  Agent  │
└────┬────┘      └────┬─────┘      └──────┬──────┘      └────┬────┘
     │                │                   │                  │
     │ create-thread  │                   │                  │
     │───────────────>│                   │                  │
     │<─ thread_id ───│                   │                  │
     │                │                   │                  │
     │ join-group     │  add to group     │                  │
     │───────────────>│──────────────────>│                  │
     │<─ joined ──────│                   │                  │
     │                │                   │                  │
     │ run (thread_id)│                   │                  │
     │───────────────>│────────────────────────────────────>│
     │<─ 202 accepted │                   │                  │
     │                │                   │    streaming     │
     │                │                   │<─────────────────│
     │   agentMessage │<── to group ──────│                  │
     │<───────────────│                   │                  │
     │   agentDone    │<── to group ──────│                  │
     │<───────────────│                   │                  │
```

### 6. Agent Execution

The agent is defined with tools and streaming is automatic:

```python
def create_travel_agent():
    return AzureOpenAIChatClient(credential=AzureCliCredential()).create_agent(
        name="TravelPlanner",
        instructions="...",
        tools=[get_weather_forecast, get_local_events]
    )

# Create AgentFunctionApp with SignalR callback
app = AgentFunctionApp(
    agents=[create_travel_agent()],
    default_callback=signalr_callback,  # All agents use this callback
    enable_health_check=True
)
```

The framework automatically:

- Creates durable orchestrations for agent runs
- Invokes the callback as responses stream
- Manages conversation state (thread_id)
