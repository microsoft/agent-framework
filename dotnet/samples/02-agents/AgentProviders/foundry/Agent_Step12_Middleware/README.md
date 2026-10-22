# Middleware with the Responses API

This sample demonstrates multiple middleware layers working together: PII filtering, guardrails, function invocation logging, and human-in-the-loop approval.

## What this sample demonstrates

- Agent-level run middleware (PII filtering, guardrail enforcement)
- Function-level middleware (logging, result overrides)
- Human-in-the-loop approval workflows for sensitive function calls
- Using `.AsBuilder().Use()` to compose middleware
- No server-side agent creation or cleanup required

> **Note:** Function invocation middleware applies to tools registered on the agent. This
> includes tools passed to the `ChatClientAgent` constructor, passed to `AsAIAgent`, configured
> through `ChatClientAgentOptions.ChatOptions.Tools`, or supplied for an individual run. These
> tools are passed through `ChatOptions.Tools`. Functions added directly to
> `FunctionInvokingChatClient.AdditionalTools` bypass this middleware entirely, so don't rely on
> the middleware to enforce checks for those functions.

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
dotnet run --project .\Agent_Step12_Middleware
```
