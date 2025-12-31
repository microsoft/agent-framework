# Non-Durable Azure Functions Samples

These samples demonstrate how to expose agents and workflows through Azure Functions HTTP triggers with **real-time streaming responses**, without using Durable Functions orchestration.

## 📖 Overview

This directory contains samples that show the **simple, stateless approach** to running agents and workflows in Azure Functions. Unlike the durable samples (01-10), these samples:

- ✅ Use direct HTTP streaming for real-time responses
- ✅ Are stateless and don't require storage accounts
- ✅ Stream results using Server-Sent Events (SSE)
- ✅ Execute synchronously within the HTTP request lifecycle
- ❌ Don't use orchestration or durable state management
- ❌ Don't support fire-and-forget or status polling patterns

## 🔄 When to Use Non-Durable vs Durable

| Feature | Non-Durable (This Folder) | Durable (01-10 Samples) |
|---------|---------------------------|-------------------------|
| **Response Time** | Real-time streaming | Async with polling |
| **State Management** | Stateless | Persisted state |
| **Execution Model** | Synchronous | Orchestrated, async |
| **Complexity** | Simple, direct | More complex patterns |
| **Best For** | Quick responses, chat UIs | Long-running workflows, HITL |
| **Timeout Limits** | HTTP timeout (~230s) | Hours/days |
| **Storage Required** | No | Yes (Azurite/Azure Storage) |

### Choose Non-Durable When:
- You need **real-time streaming** for chat interfaces
- Responses complete within a few minutes
- You want **simple, stateless** execution
- You don't need to track execution status over time
- You want minimal infrastructure dependencies

### Choose Durable When:
- You need **human-in-the-loop** approval workflows
- Execution takes longer than HTTP timeout limits
- You need to query status or resume execution later
- You want **complex orchestration patterns** (concurrency, conditionals)
- You need reliable state persistence

## 📂 Samples in This Directory

### [01_agent_http_streaming](./01_agent_http_streaming)
Demonstrates exposing a single agent through an HTTP trigger with streaming responses using Server-Sent Events (SSE).

**Key Concepts:**
- Direct agent execution in HTTP trigger
- Streaming responses with `AsyncGenerator`
- SSE format for browser compatibility
- Tool calling with function results
- Error handling in streaming context

### [02_workflow_http_streaming](./02_workflow_http_streaming)
Shows how to run multi-agent workflows with real-time streaming of intermediate steps and agent handoffs.

**Key Concepts:**
- Workflow execution without orchestration
- Streaming workflow events (agent transitions, tool calls)
- Multi-agent coordination in real-time
- Step-by-step progress updates

## 🚀 Environment Setup

### Prerequisites

1. **Install Azure Functions Core Tools 4.x**
   ```powershell
   # Windows (using npm)
   npm install -g azure-functions-core-tools@4 --unsafe-perm true
   ```

2. **Create Azure OpenAI Resource**
   - Create an [Azure OpenAI](https://azure.microsoft.com/products/ai-services/openai-service) resource
   - Deploy a chat model (e.g., gpt-4, gpt-4o, gpt-35-turbo)
   - Note the endpoint and deployment name

3. **Install REST Client** (optional but recommended)
   - [REST Client for VS Code](https://marketplace.visualstudio.com/items?itemName=humao.rest-client)
   - Or use cURL from the command line

### Running a Sample

1. **Navigate to the sample directory:**
   ```powershell
   cd python\samples\getting_started\azure_functions\non-durable\01_agent_http_streaming
   ```

2. **Create and activate a virtual environment:**
   ```powershell
   python -m venv .venv
   .venv\Scripts\Activate.ps1
   ```

3. **Install dependencies:**
   ```powershell
   pip install -r requirements.txt
   ```

4. **Configure settings:**
   ```powershell
   # Copy the template
   cp local.settings.json.template local.settings.json
   
   # Edit local.settings.json with your values
   # Set AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_CHAT_DEPLOYMENT_NAME
   ```

5. **Authenticate with Azure CLI** (if using AzureCliCredential):
   ```powershell
   az login
   ```

6. **Start the function:**
   ```powershell
   func start
   ```

7. **Test the endpoint:**
   - Use the `demo.http` file with REST Client extension
   - Or use cURL examples in the sample's README

## 🌐 HTTP Streaming with Azure Functions

These samples use Azure Functions' native support for HTTP streaming via async generators:

```python
@app.route(route="agent/stream", methods=["POST"])
async def stream_response(req: func.HttpRequest) -> func.HttpResponse:
    async def generate():
        async for chunk in agent.run_stream(message):
            if chunk.text:
                # Format as Server-Sent Events
                yield f"data: {json.dumps({'text': chunk.text})}\n\n"
    
    return func.HttpResponse(
        body=generate(),
        mimetype="text/event-stream",
        status_code=200
    )
```

### Client-Side Consumption

**JavaScript (Browser):**
```javascript
const eventSource = new EventSource('http://localhost:7071/api/agent/stream');
eventSource.onmessage = (event) => {
    const data = JSON.parse(event.data);
    console.log(data.text);
};
```

**Python:**
```python
import requests

response = requests.post(
    'http://localhost:7071/api/agent/stream',
    json={'message': 'Hello!'},
    stream=True
)

for line in response.iter_lines():
    if line.startswith(b'data: '):
        data = json.loads(line[6:])
        print(data['text'], end='', flush=True)
```

## 📚 Additional Resources

- [Azure Functions Python Developer Guide](https://learn.microsoft.com/azure/azure-functions/functions-reference-python)
- [HTTP Streaming in Azure Functions](https://learn.microsoft.com/azure/azure-functions/functions-reference-python#http-streaming)
- [Server-Sent Events (SSE) Specification](https://html.spec.whatwg.org/multipage/server-sent-events.html)
- [Durable Functions Samples](../) - For orchestration patterns

## 🤝 Contributing

When adding new non-durable samples:
- Keep them simple and focused on HTTP streaming
- Avoid orchestration patterns (use durable samples for that)
- Document when to use this approach vs durable
- Include comprehensive `demo.http` examples
- Follow the [Sample Guidelines](../../../SAMPLE_GUIDELINES.md)
