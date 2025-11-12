# Single Agent Sample (Python)

This sample demonstrates how to use the Durable Extension for Agent Framework to create a simple Azure Functions app that hosts a single AI agent and provides direct HTTP API access for interactive conversations.

## Key Concepts Demonstrated

- Defining a simple agent with the Microsoft Agent Framework and wiring it into
  an Azure Functions app via the Durable Extension for Agent Framework.
- Calling the agent through generated HTTP endpoints (`/api/agents/Joker/run`).
- Managing conversation state with thread identifiers, so multiple clients can
  interact with the agent concurrently without sharing context.

## Environment Setup

### 1. Create and activate a virtual environment

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

### 2. Install dependencies

- [Azure Functions Core Tools 4.x](https://learn.microsoft.com/azure/azure-functions/functions-run-local?tabs=windows%2Cpython%2Cv2&pivots=programming-language-python#install-the-azure-functions-core-tools) – install so you can run `func start` locally.
- [Azurite storage emulator](https://learn.microsoft.com/azure/storage/common/storage-use-azurite?tabs=visual-studio) – install and start Azurite before launching the app (the sample uses `AzureWebJobsStorage=UseDevelopmentStorage=true`).
- Python dependencies – from this folder, run `pip install -r requirements.txt` (or the equivalent in your active virtual environment).
- Copy `local.settings.json.template` to `local.settings.json`, then update `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_CHAT_DEPLOYMENT_NAME`, and `AZURE_OPENAI_API_KEY` so the Azure OpenAI SDK can authenticate; keep `TASKHUB_NAME` set to `default` unless you plan to change the durable task hub name.

## Running the Sample

With the environment configured and the Functions host running, you can interact
with the Joker agent using the provided `demo.http` file or any HTTP client. For
example:

```bash
curl -X POST http://localhost:7071/api/agents/Joker/run \
     -H "Content-Type: text/plain" \
     -d "Tell me a short joke about cloud computing."
```

The agent responds with a JSON payload that includes the generated joke.

## Expected Output

When you send a POST request with plain-text input, the Functions host responds with an HTTP 202 and queues the request for the durable agent entity. A typical response body looks like the following:

```json
{
  "status": "accepted",
  "response": "Agent request accepted",
  "message": "Tell me a short joke about cloud computing.",
  "threadId": "<guid>",
  "correlationId": "<guid>"
}
```
