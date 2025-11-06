# Single Agent Sample (Python)

This sample demonstrates how to use the Durable Extension for Agent Framework to create a simple Azure Functions app that hosts a single AI agent and provides direct HTTP API access for interactive conversations.

## Key Concepts Demonstrated

- Defining a simple agent with the Microsoft Agent Framework and wiring it into
  an Azure Functions app via the Durable Extension for Agent Framework.
- Calling the agent through generated HTTP endpoints (`/api/agents/Joker/run`).
- Managing conversation state with session identifiers, so multiple clients can
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

- Azure Functions Core Tools 4.x – install from the official docs so you can run `func start` locally.
- Azurite storage emulator – the sample uses `AzureWebJobsStorage=UseDevelopmentStorage=true`; start Azurite before launching the app.
- Durable Task local backend – `DURABLE_TASK_SCHEDULER_CONNECTION_STRING` expects the Durable Task scheduler listening on `http://localhost:8080` (start the Durable Functions emulator if it is not already running).
- Python dependencies – from this folder, run `pip install -r requirements.txt` (or the equivalent in your active virtual environment).
- Environment variables – update `AZURE_OPENAI_ENDPOINT` and `AZURE_OPENAI_CHAT_DEPLOYMENT_NAME` in `local.settings.json` with your Azure OpenAI resource details; keep the other values as provided unless you are using custom infrastructure.

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
