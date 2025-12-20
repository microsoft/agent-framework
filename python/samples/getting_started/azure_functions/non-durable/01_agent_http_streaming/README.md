# Agent HTTP Streaming

This sample demonstrates how to expose an Azure OpenAI-powered agent through an Azure Functions HTTP trigger with **real-time streaming responses**.

## 📖 Overview

This sample shows the simplest way to run an agent in Azure Functions with streaming output. Unlike the durable samples, this approach:

- Executes the agent **directly within the HTTP request**
- Streams responses in **real-time** using Server-Sent Events (SSE)
- Is **stateless** - no storage or orchestration required
- Returns results **synchronously** during the HTTP connection

## 🎯 What You'll Learn

- How to create an agent with `AzureOpenAIChatClient`
- How to stream agent responses using Azure Functions HTTP streaming
- How to format streaming data as Server-Sent Events (SSE)
- How to handle tool calls in a streaming context
- Error handling for streaming responses

## 🏗️ Architecture

```
HTTP POST Request
    ↓
Azure Function HTTP Trigger
    ↓
Create/Get Agent
    ↓
Run Agent with Streaming (agent.run_stream)
    ↓
Stream chunks via AsyncGenerator
    ↓
Format as SSE (data: {...}\n\n)
    ↓
HTTP Response (text/event-stream)
```

## 📋 Prerequisites

Before running this sample:

1. **Azure OpenAI Resource**
   - Endpoint URL (e.g., `https://your-resource.openai.azure.com`)
   - Chat deployment name (e.g., `gpt-4`, `gpt-35-turbo`)
   - Authentication via Azure CLI (`az login`) or API key

2. **Development Tools**
   - Python 3.10 or higher
   - [Azure Functions Core Tools 4.x](https://learn.microsoft.com/azure/azure-functions/functions-run-local)
   - [REST Client](https://marketplace.visualstudio.com/items?itemName=humao.rest-client) (optional)

## 🚀 Setup

### 1. Create Virtual Environment

**Windows (PowerShell):**
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

**Linux/macOS:**
```bash
python -m venv .venv
source .venv/bin/activate
```

### 2. Install Dependencies

```powershell
pip install -r requirements.txt
```

### 3. Configure Settings

Copy the template and update with your Azure OpenAI details:

```powershell
cp local.settings.json.template local.settings.json
```

Edit `local.settings.json`:
```json
{
  "IsEncrypted": false,
  "Values": {
    "FUNCTIONS_WORKER_RUNTIME": "python",
    "AzureWebJobsFeatureFlags": "EnableWorkerIndexing",
    "AZURE_OPENAI_ENDPOINT": "https://your-resource.openai.azure.com",
    "AZURE_OPENAI_CHAT_DEPLOYMENT_NAME": "gpt-4"
  }
}
```

**Note:** This sample uses `AzureCliCredential` by default. Run `az login` before starting, or set `AZURE_OPENAI_API_KEY` and modify the code to use API key authentication.

### 4. Start the Function

```powershell
func start
```

You should see output like:
```
Azure Functions Core Tools
...
Functions:
    stream_agent: [POST] http://localhost:7071/api/agent/stream
```

## 🧪 Testing

### Using REST Client (VS Code)

Open `demo.http` and click "Send Request" above any request:

```http
### Stream agent response with tool calling
POST http://localhost:7071/api/agent/stream
Content-Type: application/json

{
    "message": "What's the weather like in Seattle and Portland?"
}
```

### Using cURL

```bash
curl -X POST http://localhost:7071/api/agent/stream \
  -H "Content-Type: application/json" \
  -d '{"message": "What is the weather in Seattle?"}'
```

### Using Python

```python
import requests
import json

response = requests.post(
    'http://localhost:7071/api/agent/stream',
    json={'message': 'Tell me about Seattle weather'},
    stream=True
)

print("Agent: ", end='', flush=True)
for line in response.iter_lines():
    if line.startswith(b'data: '):
        data = json.loads(line[6:])
        if data.get('text'):
            print(data['text'], end='', flush=True)
print()
```

### Using JavaScript (Browser)

```html
<script>
const eventSource = new EventSource('http://localhost:7071/api/agent/stream?message=Hello');
eventSource.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.text) {
        document.body.innerHTML += data.text;
    }
};
</script>
```

## 📤 Expected Output

When you send a message, you'll receive a streaming response in SSE format:

```
data: {"text": "Let"}

data: {"text": " me"}

data: {"text": " check"}

data: {"text": " the"}

data: {"text": " weather"}

data: {"text": " for"}

data: {"text": " you"}

data: {"text": "."}

data: {"text": " The"}

data: {"text": " weather"}

data: {"text": " in"}

data: {"text": " Seattle"}

data: {"text": " is"}

data: {"text": " cloudy"}

data: {"text": " with"}

data: {"text": " a"}

data: {"text": " high"}

data: {"text": " of"}

data: {"text": " 15"}

data: {"text": "°C"}

data: {"text": "."}
```

Note: Tool calls happen transparently; only text output is streamed to the client.

## 🔍 Key Concepts

### 1. HTTP Streaming with AsyncGenerator

The function uses an async generator to yield streaming chunks:

```python
async def generate():
    async for chunk in _agent.run_stream(message):
        if chunk.text:
            yield f"data: {json.dumps({'text': chunk.text})}\n\n"
```

### 2. Server-Sent Events (SSE) Format

Each chunk is formatted as SSE with the `data:` prefix and double newline:
- `data: <JSON>\n\n`
- Compatible with browsers' `EventSource` API
- Simple to parse on the client side

### 3. Stateless Execution

- No storage account or Azurite required
- Each request is independent
- No state persisted between requests
- Agent executes directly in the HTTP handler

### 4. Tool Calling

The sample includes a `get_weather` function that the agent can call:
- Tool calls happen transparently during streaming
- Only text responses are streamed to the client
- All happens within the same HTTP request

## 🆚 Comparison with Durable Samples

| Feature | This Sample | Durable Samples (01-10) |
|---------|-------------|-------------------------|
| Response Mode | Real-time streaming | Fire-and-forget + polling |
| State Storage | None | Azure Storage/Azurite |
| Timeout | ~230s (HTTP timeout) | Hours/days |
| Status Queries | Not supported | Supported |
| Complexity | Low | Medium-High |
| Setup Required | Minimal | Storage + orchestration |

## ⚠️ Limitations

1. **Timeout Constraints**
   - HTTP connections time out (~230 seconds)
   - Not suitable for very long-running tasks
   - Use durable samples for longer executions

2. **No State Persistence**
   - Can't query status after completion
   - Can't resume interrupted executions
   - Use durable samples if you need these features

3. **No Orchestration Patterns**
   - No built-in concurrency, conditionals, or HITL
   - Use durable samples for complex workflows

## 🎓 Next Steps

- **[02_workflow_http_streaming](../02_workflow_http_streaming)** - Stream multi-agent workflows
- **[04_single_agent_orchestration_chaining](../../04_single_agent_orchestration_chaining)** - Learn durable orchestration
- **[07_single_agent_orchestration_hitl](../../07_single_agent_orchestration_hitl)** - Add human-in-the-loop

## 📚 References

- [Azure Functions Python Developer Guide](https://learn.microsoft.com/azure/azure-functions/functions-reference-python)
- [HTTP Streaming in Azure Functions](https://learn.microsoft.com/azure/azure-functions/functions-reference-python#http-streaming)
- [Server-Sent Events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events)
