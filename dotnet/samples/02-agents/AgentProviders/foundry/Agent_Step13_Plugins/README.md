# Using Plugins with the Responses API

This sample shows how to use plugins with a `ChatClientAgent` using the Responses API directly, with dependency injection for plugin services.

## What this sample demonstrates

- Creating plugin classes with injected dependencies
- Registering services and building a service provider
- Passing `services` to the `ChatClientAgent` via the options-based constructor
- Using `AIFunctionFactory` to expose plugin methods as AI tools

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
dotnet run
```

