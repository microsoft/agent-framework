# Structured Output with the Responses API

This sample demonstrates how to configure an agent to produce structured output using JSON schema.

## What this sample demonstrates

- Using `RunAsync<T>()` to get typed structured output from the agent
- Deserializing streamed responses into structured types
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
dotnet run --project .\Agent_Step05_StructuredOutput
```

