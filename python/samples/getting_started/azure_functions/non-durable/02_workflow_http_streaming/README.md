# Workflow HTTP Streaming

This sample demonstrates how to run **multi-agent workflows** through an Azure Functions HTTP trigger with **real-time streaming** of workflow execution steps.

## 📖 Overview

This sample shows how to execute Agent Framework workflows (MAF) in Azure Functions with streaming output. Unlike the durable orchestration samples, this approach:

- Executes the workflow **directly within the HTTP request**
- Streams workflow events **in real-time** (agent transitions, tool calls, responses)
- Is **stateless** - no storage or durable orchestration required
- Returns results **synchronously** during the HTTP connection

## 🎯 What You'll Learn

- How to create multi-agent workflows without durable orchestration
- How to stream workflow execution events in real-time
- How to track agent transitions and handoffs
- How to handle tool calls across multiple agents
- Formatting workflow events as Server-Sent Events (SSE)

## 🏗️ Architecture

```
HTTP POST Request
    ↓
Azure Function HTTP Trigger
    ↓
Create Workflow (Sequential/GroupChat)
    ↓
Run Workflow with Streaming
    ↓
Stream workflow events via AsyncGenerator
    │
    ├─→ Agent started
    ├─→ Tool call
    ├─→ Tool result
    ├─→ Response chunk
    ├─→ Agent transition
    └─→ Workflow complete
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
    stream_workflow: [POST] http://localhost:7071/api/workflow/stream
```

## 🧪 Testing

### Using REST Client (VS Code)

Open `demo.http` and click "Send Request" above any request:

```http
### Stream workflow with research assistant
POST http://localhost:7071/api/workflow/stream
Content-Type: application/json

{
    "message": "Research the weather in Seattle and write a short poem about it"
}
```

### Using cURL

```bash
curl -X POST http://localhost:7071/api/workflow/stream \
  -H "Content-Type: application/json" \
  -d '{"message": "Research Seattle weather and create a report"}'
```

### Using Python

```python
import requests
import json

response = requests.post(
    'http://localhost:7071/api/workflow/stream',
    json={'message': 'Research Seattle weather and write a short article'},
    stream=True
)

print("Workflow output: ", end='', flush=True)
for line in response.iter_lines():
    if line.startswith(b'data: '):
        data = json.loads(line[6:])
        if data.get('text'):
            print(data['text'], end='', flush=True)
print()
```

## 📤 Expected Output

When you send a message, you'll receive a streaming response showing text from both agents:

```
data: {"text": "Let"}

data: {"text": " me"}

data: {"text": " check"}

data: {"text": " the"}

data: {"text": " weather"}

data: {"text": " for"}

data: {"text": " Seattle"}

data: {"text": "."}

data: {"text": " The"}

data: {"text": " weather"}

data: {"text": " in"}

data: {"text": " Seattle"}

data: {"text": " is"}

data: {"text": " sunny"}

...

(Researcher completes, Writer begins)

data: {"text": "Based"}

data: {"text": " on"}

data: {"text": " the"}

data: {"text": " research"}

data: {"text": ","}

data: {"text": " here"}

data: {"text": "'s"}

data: {"text": " a"}

data: {"text": " short"}

data: {"text": " article"}

...
```

Note: The stream contains text from both agents sequentially. Agent transitions and tool calls happen transparently.

## 🔍 Key Concepts

### 1. Workflow Without Orchestration

This sample uses Agent Framework workflows directly without durable orchestration:

```python
workflow = (
    SequentialBuilder()
    .participants([research_agent, writer_agent])
    .build()
)
```

### 2. Streaming Workflow Events

The workflow streams text chunks as agents generate responses:

```python
async def generate():
    async for event in _workflow.run_stream(message):
        if isinstance(event, AgentRunUpdateEvent) and event.data:
            text = event.data.text
            if text:
                yield f"data: {json.dumps({'text': text})}\n\n"
```

Only text output is streamed; internal events (agent transitions, tool calls) happen transparently.

### 3. Multi-Agent Coordination

The sample demonstrates sequential workflow with handoffs:
1. Research Agent gathers information using tools
2. Writer Agent creates content based on research
3. All happens within a single HTTP request

### 4. Simple Client-Side Handling

Clients receive only text chunks, making parsing straightforward:
```python
for line in response.iter_lines():
    if line.startswith(b'data: '):
        data = json.loads(line[6:])
        if data.get('text'):
            print(data['text'], end='', flush=True)
```

## 🆚 Comparison with Durable Workflow Samples

| Feature | This Sample | Durable Workflow Samples |
|---------|-------------|--------------------------|
| Orchestration | None (direct execution) | Durable Task Framework |
| Agent Transitions | Streamed in real-time | Via orchestration activities |
| State Management | In-memory only | Persisted in storage |
| Timeout | ~230s (HTTP timeout) | Hours/days |
| Complexity | Low | Medium-High |
| Use Case | Quick multi-step tasks | Long-running workflows |

## ⚠️ Limitations

1. **Timeout Constraints**
   - Limited by HTTP timeout (~230 seconds)
   - Not suitable for very long workflows
   - Use durable samples for extended execution

2. **No State Persistence**
   - Workflow state lost after response completes
   - Can't resume interrupted workflows
   - Use durable samples for stateful workflows

3. **No Advanced Orchestration**
   - No built-in concurrency patterns
   - No conditional branching with state
   - No human-in-the-loop approval
   - Use durable samples for complex patterns

## 🎯 When to Use This Approach

**✅ Use Non-Durable Workflow Streaming When:**
- Workflow completes within a few minutes
- You need real-time progress updates
- State persistence isn't required
- Simple sequential or group chat patterns

**❌ Use Durable Workflows Instead When:**
- Workflow takes longer than HTTP timeout
- You need human approval/intervention
- State must persist across requests
- Complex orchestration patterns needed

## 🎓 Next Steps

- **[01_agent_http_streaming](../01_agent_http_streaming)** - Simpler single-agent streaming
- **[05_multi_agent_orchestration_concurrency](../../05_multi_agent_orchestration_concurrency)** - Concurrent agents with durable
- **[06_multi_agent_orchestration_conditionals](../../06_multi_agent_orchestration_conditionals)** - Conditional workflows

## 📚 References

- [Agent Framework Workflows](https://github.com/microsoft/agent-framework)
- [Azure Functions Python Developer Guide](https://learn.microsoft.com/azure/azure-functions/functions-reference-python)
- [Server-Sent Events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events)
