# Hosted-Observability

A hosted [Agent Framework](https://github.com/microsoft/agent-framework) agent that demonstrates how the Foundry hosting pipeline emits OpenTelemetry traces, metrics and logs with no extra wiring.

The agent has two small tools, `GetCurrentLocation` and `GetWeather`, so an end-to-end run produces a span tree covering agent invocation, the underlying chat call, and tool execution.

## How it works

### Instrumentation is on by default

Unlike the Python SDK, the .NET hosting library is instrumented by default. `AddFoundryResponses(agent)` automatically wraps the agent with `OpenTelemetryAgent` (see `Microsoft.Agents.AI.Foundry.Hosting.ServiceCollectionExtensions.ApplyOpenTelemetry`) and the OTLP exporter pipeline is registered by `Azure.AI.AgentServer.Core`'s `AddAgentHostTelemetry()`. There is no `ENABLE_INSTRUMENTATION` flag to set.

### Sensitive content

Prompt, completion and tool argument content are omitted from spans by default. Set the OpenTelemetry standard environment variable to capture them:

```env
OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true
```

This is the .NET equivalent of the Python sample's `ENABLE_SENSITIVE_DATA`. It is read by `OpenTelemetryAgent.EnableSensitiveData`.

### Where the telemetry goes

Foundry injects `APPLICATIONINSIGHTS_CONNECTION_STRING` when the agent runs in the hosted environment, so traces, metrics and logs flow to Application Insights with no code change. To send telemetry from a local run, set the connection string yourself in `.env`.

## Prerequisites

- [.NET 10 SDK](https://dotnet.microsoft.com/download/dotnet/10.0)
- An Azure AI Foundry project with a deployed model (e.g., `gpt-4o`)
- Azure CLI logged in (`az login`)

## Configuration

```bash
cp .env.example .env
```

Edit `.env` and set your Azure AI Foundry project endpoint:

```env
AZURE_AI_PROJECT_ENDPOINT=https://<your-account>.services.ai.azure.com/api/projects/<your-project>
ASPNETCORE_URLS=http://+:8088
ASPNETCORE_ENVIRONMENT=Development
AZURE_AI_MODEL_DEPLOYMENT_NAME=gpt-4o
OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true
```

> **Note:** `.env` is gitignored. The `.env.example` template is checked in as a reference.

## Running directly (contributors)

```bash
cd dotnet/samples/04-hosting/FoundryHostedAgents/responses/Hosted-Observability
AGENT_NAME=hosted-observability dotnet run
```

The agent starts on `http://localhost:8088`.

### Test it

```bash
azd ai agent invoke --local "What is the current weather where I am?"
```

Or with curl:

```bash
curl -X POST http://localhost:8088/responses \
  -H "Content-Type: application/json" \
  -d '{"input": "What is the current weather where I am?", "model": "hosted-observability"}'
```

## Expected span tree

A single request produces approximately the following spans:

| Span | Source |
|------|--------|
| `invoke_agent` | Outer span emitted by the Azure AI AgentServer hosting SDK |
| `agent_invoke <name>` | Emitted by `OpenTelemetryAgent` for each agent invocation |
| `chat <model>` | Emitted by the underlying `IChatClient` for each model call |
| `execute_tool <tool>` | Emitted for each invocation of `GetCurrentLocation` / `GetWeather` |

See the [OpenTelemetry GenAI semantic conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/) for the attributes captured on each span.

## Running with Docker

This project uses `ProjectReference` to the local Agent Framework source, so use `Dockerfile.contributor` with a pre-published output:

```bash
dotnet publish -c Debug -f net10.0 -r linux-musl-x64 --self-contained false -o out
docker build -f Dockerfile.contributor -t hosted-observability .

export AZURE_BEARER_TOKEN=$(az account get-access-token --resource https://ai.azure.com --query accessToken -o tsv)
docker run --rm -p 8088:8088 \
  -e AGENT_NAME=hosted-observability \
  -e AZURE_BEARER_TOKEN=$AZURE_BEARER_TOKEN \
  --env-file .env \
  hosted-observability
```

## Deploying to Foundry and viewing traces

Once deployed, telemetry flows to the Application Insights instance attached to your Foundry project. In the Foundry UI, the **Traces** tab next to **Playground** lists conversations and lets you drill into the span tree for any request.

## NuGet package users

If consuming the Agent Framework as a NuGet package, use the standard `Dockerfile` instead of `Dockerfile.contributor`. See the commented section in `HostedObservability.csproj` for the `PackageReference` alternative.
