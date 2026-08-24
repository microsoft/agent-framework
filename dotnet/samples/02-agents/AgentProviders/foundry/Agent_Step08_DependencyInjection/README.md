# Dependency Injection with the Responses API

This sample demonstrates how to register a `ChatClientAgent` in a dependency injection container and use it from a hosted service.

## What this sample demonstrates

- Registering `ChatClientAgent` as an `AIAgent` in the service collection
- Using the agent from a `IHostedService` with an interactive chat loop
- Streaming responses in a hosted service context
- No server-side agent creation or cleanup required

## Prerequisites

- .NET 10 SDK or later
- Microsoft Foundry service endpoint and deployment configured
- An authenticated Azure identity (for example, sign in with `az login`)

Set the following environment variables:

```powershell
$env:FOUNDRY_PROJECT_ENDPOINT="https://your-foundry-service.services.ai.azure.com/api/projects/your-foundry-project"
$env:FOUNDRY_MODEL="gpt-5.4-mini"
```

## Run the sample

```powershell
cd dotnet/samples/02-agents/AgentProviders/foundry
dotnet run --project .\Agent_Step08_DependencyInjection
```

