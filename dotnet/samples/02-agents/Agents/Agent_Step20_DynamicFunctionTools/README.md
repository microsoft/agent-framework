# Dynamic Function Tools

This sample demonstrates how to dynamically expand the set of function tools available to an agent during a function-calling loop.

## What it demonstrates

- The agent starts with only a single `RequestTools` function
- When the model needs capabilities it doesn't have, it calls `RequestTools` with a description of the functionality needed
- The `RequestTools` function uses the ambient `FunctionInvokingChatClient.CurrentContext` to access `ChatOptions.Tools` and add new tools at runtime
- The agent then uses the newly added tools in subsequent iterations of the same function-calling loop

## How it works

1. A tool catalog maps keywords (e.g. "weather", "time", "temperature") to pre-built `AIFunction` instances
2. The `RequestTools` function matches the description against catalog keywords and adds matching tools to `ChatOptions.Tools`
3. `FunctionInvokingChatClient` automatically picks up the new tools on the next iteration of its loop

## Prerequisites

- .NET 10 SDK or later
- Azure OpenAI service endpoint and deployment configured
- Azure CLI installed and authenticated (for Azure credential authentication)
- User has the `Cognitive Services OpenAI Contributor` role for the Azure OpenAI resource

## Running the sample

Set the required environment variables:

```powershell
$env:AZURE_OPENAI_ENDPOINT="https://your-resource.openai.azure.com/"
$env:AZURE_OPENAI_DEPLOYMENT_NAME="gpt-5.4-mini"  # Optional, defaults to gpt-5.4-mini
```

Run the sample:

```powershell
dotnet run
```
