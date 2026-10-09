# Agent as a Function Tool with the Responses API

This sample demonstrates how to use one agent as a function tool for another agent.

Function tools expose operations through structured inputs and outputs making them useful for many different integration scenarios. 

Using `yourAIAgent.AsAIFunction()` exposes the agent as a function that other agents can use as a tool, enabling agent-composition scenarios.

> [!NOTE]
> Wrapping an AI-model-driven agent as an `AIFunction` doesn't make the agent deterministic. The function returns the agent response's text, so determinism still depends entirely on how the agent is configured.

> [!IMPORTANT]
> Agents exposed through `.AsAIFunction()` are intended for background and non-interactive workflows, and are not suited for workflows that require human-in-the-loop approval. 
> For interactive, human-in-the-loop workflows, use the [Agent Framework workflow samples](https://github.com/microsoft/agent-framework/tree/main/dotnet/samples/03-workflows).

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

