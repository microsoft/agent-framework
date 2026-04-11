# What this sample demonstrates

This sample demonstrates Human-in-the-Loop (HITL) capabilities with thread persistence. The agent wraps function tools with `ApprovalRequiredAIFunction` so that every tool invocation requires explicit user approval before execution. Thread state is maintained across requests using `InMemoryAgentThreadRepository`.

Key features:
- Requiring human approval before executing function calls
- Persisting conversation threads across multiple requests
- Approving or rejecting tool invocations at runtime

> For common prerequisites and setup instructions, see the [Hosted Agent Samples README](../README.md).

## Prerequisites

Before running this sample, ensure you have:

1. .NET 10 SDK installed
2. An Azure OpenAI endpoint configured
3. A deployment of a chat model (e.g., gpt-4o-mini)
4. Azure CLI installed and authenticated (`az login`)

## Environment Variables

Set the following environment variables:

```powershell
# Replace with your Azure OpenAI endpoint
$env:AZURE_OPENAI_ENDPOINT="https://your-openai-resource.openai.azure.com/"

# Optional, defaults to gpt-4o-mini
$env:AZURE_OPENAI_DEPLOYMENT_NAME="gpt-4o-mini"
```

## How It Works

The sample uses `ApprovalRequiredAIFunction` to wrap standard AI function tools. When the model decides to call a tool, the wrapper intercepts the invocation and returns a HITL approval request to the caller instead of executing the function immediately.

1. The user sends a message (e.g., "What is the weather in Vancouver?")
2. The model determines a function call is needed and selects the `GetWeather` tool
3. `ApprovalRequiredAIFunction` intercepts the call and returns an approval request containing the function name and arguments
4. The user responds with `approve` or `reject`
5. If approved, the function executes and the model generates a response using the result
6. If rejected, the model generates a response without the function result

Thread persistence is handled by `InMemoryAgentThreadRepository`, which stores conversation history keyed by `conversation.id`. This means the HITL flow works across multiple HTTP requests as long as each request includes the same `conversation.id`.

> **Note:** HITL requires a stable `conversation.id` in every request so the agent can correlate the approval response with the original function call. Use the `run-requests.http` file in this directory to test the full approval flow.
