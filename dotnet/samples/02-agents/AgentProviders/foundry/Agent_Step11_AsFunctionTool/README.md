# Agent as a Function Tool with the Responses API

This sample demonstrates how to use one agent as a function tool for another agent.

Function tools expose operations through structured inputs, making them useful for scenarios such as API integrations with validation and transformations, database operations, or payment processing. Using `.AsAIFunction()` exposes an agent as a function tool, enabling agent composition and advanced workflows. Because the wrapped agent remains model-driven, this does not make its behavior deterministic. Agents exposed through `.AsAIFunction()` are intended for background and non-interactive workflows, and are not suited for workflows that require human-in-the-loop approval.

## What this sample demonstrates

- Creating a specialized agent (weather) with function tools
- Exposing an agent as a function tool using `.AsAIFunction()`
- Composing agents where one agent delegates to another
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
dotnet run --project .\Agent_Step11_AsFunctionTool
```

