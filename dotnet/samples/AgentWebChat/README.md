# AgentWebChat (Microsoft Agent Framework sample)

AgentWebChat is a small end-to-end sample that hosts AI agents in an ASP.NET Core service and chats with them from a simple web UI. The whole sample is orchestrated with **.NET Aspire** so you can run everything together and configure the model provider from the Aspire Dashboard.

## What’s in this sample

- **Agent host**: `AgentWebChat.AgentHost`
  - Hosts multiple agents and workflows.
  - Exposes:
    - Agent discovery endpoint at `/agents`
    - A2A endpoints (e.g., `/a2a/pirate`, `/a2a/knights-and-knaves`)
    - OpenAI-compatible endpoints (Responses + Chat Completions)
    - Dev UI at `/devui`
- **Web front end**: `AgentWebChat.Web`
  - Blazor Server UI that can talk to the agent host.
- **Aspire AppHost**: `AgentWebChat.AppHost`
  - Starts everything and surfaces **Provider/Model/Endpoint/AccessKey** as interactive parameters.

## Prerequisites

- The .NET SDK required by this repo (see `global.json` at the repo root).
- An AI provider you can access:
  - **Ollama** running locally, or
  - **OpenAI-compatible** endpoint (OpenAI / compatible gateway), or
  - Azure OpenAI (see notes below).

## Run it (recommended: via Aspire)

From the `dotnet` folder:

```powershell
dotnet run --project .\samples\AgentWebChat\AgentWebChat.AppHost\AgentWebChat.AppHost.csproj
```

Or setup `AgentWebChat.AppHost` as your startup project in your IDE and run it.

Then:

1. Open the **Aspire Dashboard** (a link is printed in the console).
2. When prompted, provide the model configuration parameters (details below).
3. In the Dashboard, open the `webfrontend` resource endpoint to launch the chat UI.
4. Optional: open the `agenthost` resource endpoint to view:
   - `/devui` (Dev UI)
   - `/swagger` (OpenAPI UI)

## Configure model settings in the Aspire Dashboard

This sample uses Aspire **interactive parameters** (custom inputs) defined in `AgentWebChat.AppHost`.

When you run the AppHost, the Dashboard will prompt for:

- **Provider**: `OpenAI` (OpenAI-compatible), `AzureOpenAI`, or `Ollama`
- **Model**: model name (or deployment name, depending on provider)
- **Endpoint**: provider endpoint URL
- **AccessKey**: API key (secret)

Provider guidance:

- **Ollama**
  - Endpoint: `http://localhost:11434`
  - Model: e.g. `llama3.1`, `phi3.5`, etc.
  - AccessKey: not used (you can enter any placeholder)

- **OpenAI (OpenAI-compatible)**
  - Endpoint: e.g. `https://api.openai.com/v1/` (or your compatible gateway)
  - AccessKey: your API key
  - Model: e.g. `gpt-4o-mini` (whatever your endpoint supports)

- **Azure OpenAI**
    - Model: deployment name (e.g. `gpt-4o-mini`)
    - Authentication is handled using Default Azure Credentials

## What this sample demonstrates

- Using Microsoft Agent Framework in a **Web App** 
- **Hosting agents** with Microsoft Agent Framework in ASP.NET Core (`builder.AddAIAgent(...)`).
- **Different interaction surfaces for the same agents**:
  - A2A endpoints (`app.MapA2A(...)`)
  - OpenAI-compatible endpoints (`app.MapOpenAIResponses()`, `app.MapOpenAIChatCompletions(...)`)
  - Agent discovery (`app.MapAgentDiscovery("/agents")`)
- **Tools / function calling** by attaching custom AI tools to an agent.
- **Workflows** with multiple agents:
  - Sequential workflows
  - Concurrent workflows
  - A multi-agent “Knights & Knaves” example.
- **In-memory thread storage** for quick local demos.

## If you’re new to Microsoft Agent Framework

A quick mental model:

- An **agent** is a LLM component with instructions (system prompt), state, and optional tools.
- A **tool** is a function the agent can call to do real work (your code).
- A **workflow** composes multiple agents (sequentially or concurrently) to solve a task.