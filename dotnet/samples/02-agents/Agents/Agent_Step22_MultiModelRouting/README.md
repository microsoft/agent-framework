# Multi-Model Routing

This sample demonstrates how to back a single agent with multiple chat clients that use different models, using `RoutingChatClient`, and how to switch the active model at runtime.

## What This Sample Shows

`RoutingChatClient` is an `IChatClient` decorator that holds several named inner clients and, for each request, routes to one of them based on the *active destination* stored in the session. It also accepts an optional **fallback factory** that builds a client on the fly for any key that is not a registered inner client.

In this sample the destination key is the **model name**:

- Two inner clients are registered, keyed by model name (models A and B).
- A fallback factory constructs a Foundry client for whatever model name (key) is requested but not pre-registered (model C). The created client serves the single request and is disposed afterwards by default.
- The active model is changed between runs with `SetActiveDestinationKey`, and `GetActiveDestinationKey` reports the current model. A single conversation is served by three different models in turn.
- The `RoutingChatClient` is retrieved back from the agent with `agent.GetService<RoutingChatClient>()` — useful when you don't hold a direct reference (for example when the agent is created elsewhere or resolved from a DI container).

No custom `Router` is supplied, so routing simply follows the per-session active destination — exactly what `SetActiveDestinationKey` controls.

## Chat History Storage

Every client is created with `AsIChatClientWithStoredOutputDisabled(...)`, which sets the Responses API `store` flag to `false` so chat history is kept **client-side** by the agent's session.

This matters when routing across clients:

- **Service-stored chat history** is tied to the **service** that created the conversation, so it is only available when every turn is served by that same service. If your destinations all share one service, you can enable service-stored history (`AsIChatClient(...)`) and let the service persist the conversation.
- **Client-side chat history** (used here) carries the conversation in the agent's session and replays it to whichever model handles the next turn. This is required when routing may send different turns to different clients (and potentially different services), as this sample does.

## Reasoning Content

Every client is also created with `includeReasoningEncryptedContent: false`. Encrypted reasoning content is **model-specific** — one model cannot necessarily interpret another model's encrypted reasoning — so it must not be echoed back in requests when a single conversation is routed across multiple models. If you route to only a single model, you can leave this enabled (the default) to preserve reasoning across turns.

## Prerequisites

- .NET 10 SDK or later
- Microsoft Foundry project endpoint with the models below deployed
- Azure CLI installed and authenticated

**Note**: This sample uses `DefaultAzureCredential`. Sign in with `az login` before running. For production, prefer a specific credential such as `ManagedIdentityCredential`. For more information, see the [Azure CLI authentication documentation](https://learn.microsoft.com/cli/azure/authenticate-azure-cli-interactively).

## Environment Variables

```powershell
$env:FOUNDRY_PROJECT_ENDPOINT="https://your-project.services.ai.azure.com/api/projects/your-project"  # Required
$env:FOUNDRY_MODEL="gpt-5.4"                # Optional, model A (default: gpt-5.4)
$env:FOUNDRY_MODEL_ALT1="gpt-5.4-mini"      # Optional, model B (default: gpt-5.4-mini)
$env:FOUNDRY_MODEL_ALT2="Deepseek-V4-Pro"   # Optional, model C, resolved via the fallback factory (default: Deepseek-V4-Pro)
```

Update the model names to match models deployed in your Foundry project.

## Running the Sample

```powershell
cd dotnet/samples/02-agents/Agents/Agent_Step22_MultiModelRouting
dotnet run
```

## Expected Behavior

The sample runs three turns of one conversation:

1. **First turn** — routed to the default destination (model A, the first registered inner client).
2. **Second turn** — `SetActiveDestinationKey` switches to model B (the second registered inner client).
3. **Third turn** — `SetActiveDestinationKey` switches to model C, which is not registered as an inner client, so the fallback factory builds a client for it.

Each response starts by stating which model produced it, and the conversation context carries across all three models because chat history is stored client-side.
