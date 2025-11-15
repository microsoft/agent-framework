# Agent Middleware

This sample demonstrates how to add middleware to intercept agent runs and function calls to implement cross-cutting concerns like logging, validation, and guardrails.

## What This Sample Shows

1. Azure Foundry Agents integration via `AIProjectClient` and `AzureCliCredential`
2. Agent run middleware (logging and monitoring)
3. Function invocation middleware (logging and overriding tool results)
4. Per-request agent run middleware
5. Per-request function pipeline with approval
6. Combining agent-level and per-request middleware

## Function Invocation Middleware

Not all agents support function invocation middleware.

Attempting to use function middleware on agents that do not wrap a ChatClientAgent or derives from it will throw an InvalidOperationException.

## Prerequisites

Before you begin, ensure you have the following prerequisites:

- .NET 8.0 SDK or later
- Azure Foundry service endpoint and deployment configured
- Azure CLI installed and authenticated (for Azure credential authentication)

**Note**: This demo uses Azure CLI credentials for authentication. Make sure you're logged in with `az login` and have access to the Azure Foundry resource. For more information, see the [Azure CLI documentation](https://learn.microsoft.com/cli/azure/authenticate-azure-cli-interactively).

Set the following environment variables:

```powershell
$env:AZURE_FOUNDRY_PROJECT_ENDPOINT="https://your-foundry-service.services.ai.azure.com/api/projects/your-foundry-project" # Replace with your Azure Foundry resource endpoint
$env:AZURE_FOUNDRY_PROJECT_DEPLOYMENT_NAME="gpt-4o-mini"  # Optional, defaults to gpt-4o-mini
```

## Running the Sample

Navigate to the FoundryAgents sample directory and run:

```powershell
cd dotnet/samples/GettingStarted/FoundryAgents
dotnet run --project .\FoundryAgents_Step12_Middleware
```

## Expected Behavior

When you run this sample, you will see the following demonstrations:

1. **Example 1: Wording Guardrail** - The agent receives a request for harmful content. The guardrail middleware intercepts the request and prevents the agent from responding to harmful prompts, returning a safe response instead.

2. **Example 2: PII Detection** - The agent receives a message containing personally identifiable information (name, phone number, email). The PII middleware detects and filters this sensitive information before processing.

3. **Example 3: Agent Function Middleware** - The agent uses function tools (GetDateTime and GetWeather) to answer a question about the current time and weather in Seattle. The function middleware logs the function calls and can override results if needed.

4. **Example 4: Human-in-the-Loop Function Approval** - The agent attempts to call a weather function, but the approval middleware intercepts the call and prompts the user to approve or deny the function invocation before it executes. The user can respond with "Y" to approve or any other input to deny.

Each example demonstrates how middleware can be used to implement cross-cutting concerns and control agent behavior at different levels (agent-level and per-request).
