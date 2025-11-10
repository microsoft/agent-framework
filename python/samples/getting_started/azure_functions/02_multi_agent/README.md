# Multi-Agent Sample

This sample demonstrates how to use the Durable Extension for Agent Framework to create an Azure Functions app that hosts multiple AI agents and provides direct HTTP API access for interactive conversations with each agent.

## Key Concepts Demonstrated

- Using the Microsoft Agent Framework to define multiple AI agents with unique names and instructions.
- Registering multiple agents with the Function app and running them using HTTP.
- Conversation management (via session IDs) for isolated interactions per agent.
- Two different methods for registering agents: list-based initialization and incremental addition.

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
- [Azurite storage emulator](https://learn.microsoft.com/azure/storage/common/storage-use-azurite?tabs=visual-studio) – install and start Azurite before launching the app; the sample expects `AzureWebJobsStorage=UseDevelopmentStorage=true`.
- Python dependencies – from this folder, run `pip install -r requirements.txt` (or use the equivalent command in your active virtual environment).

### 3. Configure local settings

- Copy `local.settings.json.template` to `local.settings.json`, then set the Azure OpenAI values (`AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_CHAT_DEPLOYMENT_NAME`, and optionally `AZURE_OPENAI_API_KEY`) to match your environment, and keep `TASKHUB_NAME` set to `default` unless you intend to change the durable task hub name.

## Running the Sample

With the environment setup and function app running, you can test the sample by sending HTTP requests to the different agent endpoints.

You can use the `demo.http` file to send messages to the agents, or a command line tool like `curl` as shown below:

### Test the Weather Agent

Bash (Linux/macOS/WSL):

```bash
curl -X POST http://localhost:7071/api/agents/WeatherAgent/run \
    -H "Content-Type: application/json" \
    -d '{"message": "What is the weather in Seattle?"}'
```

PowerShell:

```powershell
Invoke-RestMethod -Method Post `
    -Uri http://localhost:7071/api/agents/WeatherAgent/run `
    -ContentType application/json `
    -Body '{"message": "What is the weather in Seattle?"}'
```

Expected response:
```json
{
  "status": "accepted",
  "response": "Agent request accepted",
  "message": "What is the weather in Seattle?",
  "conversation_id": "<guid>",
  "correlation_id": "<guid>"
}
```

### Test the Math Agent

Bash (Linux/macOS/WSL):

```bash
curl -X POST http://localhost:7071/api/agents/MathAgent/run \
    -H "Content-Type: application/json" \
    -d '{"message": "Calculate a 20% tip on a $50 bill"}'
```

PowerShell:

```powershell
Invoke-RestMethod -Method Post `
    -Uri http://localhost:7071/api/agents/MathAgent/run `
    -ContentType application/json `
    -Body '{"message": "Calculate a 20% tip on a $50 bill"}'
```

Expected response:
```json
{
  "status": "accepted",
  "response": "Agent request accepted",
  "message": "Calculate a 20% tip on a $50 bill",
  "conversation_id": "<guid>",
  "correlation_id": "<guid>"
}
```

### Check Health

Bash (Linux/macOS/WSL):

```bash
curl http://localhost:7071/api/health
```

PowerShell:

```powershell
Invoke-RestMethod -Uri http://localhost:7071/api/health
```

Expected response:
```json
{
  "status": "healthy",
  "agents": [
    {"name": "WeatherAgent", "type": "ChatAgent"},
    {"name": "MathAgent", "type": "ChatAgent"}
  ],
  "agent_count": 2
}
```

## Code Structure

The sample demonstrates two ways to register multiple agents:

### Option 1: Pass list of agents during initialization
```python
app = AgentFunctionApp(agents=[weather_agent, math_agent])
```

### Option 2: Add agents incrementally (commented in sample)
```python
app = AgentFunctionApp()
app.add_agent(weather_agent)
app.add_agent(math_agent)
```

Each agent automatically gets:
- `POST /api/agents/{agent_name}/run` - Send messages to the agent

