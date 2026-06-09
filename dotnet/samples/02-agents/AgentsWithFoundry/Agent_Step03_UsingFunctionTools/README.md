# Using Function Tools with the Responses API

This sample demonstrates how to use function tools with the `ChatClientAgent`, allowing the agent to call custom functions to retrieve information.

## What this sample demonstrates

- Creating function tools using `AIFunctionFactory`
- Passing function tools to a `ChatClientAgent`
- Running agents with function tools (text output)
- Running agents with function tools (streaming output)
- No server-side agent creation or cleanup required

## Prerequisites

Before you begin, ensure you have the following prerequisites:

- .NET 10 SDK or later
- Microsoft Foundry service endpoint and deployment configured
- An authenticated Azure identity (for example, sign in with `az login`)

**Note**: This sample uses `DefaultAzureCredential`. `az login` is the easiest local development path, but Visual Studio, VS Code, and managed identity credentials also work when available.

Set the following environment variables:

```powershell
$env:FOUNDRY_PROJECT_ENDPOINT="https://your-foundry-service.services.ai.azure.com/api/projects/your-foundry-project"
$env:FOUNDRY_MODEL="gpt-5.4-mini"
```

## Run the sample

Navigate to the AgentsWithFoundry sample directory and run:

```powershell
cd dotnet/samples/02-agents/AgentsWithFoundry
dotnet run --project .\Agent_Step03_UsingFunctionTools
```
