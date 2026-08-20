# Multi-Model Routing

This sample demonstrates how to use the `RoutePersistingRoutingChatClient` to route each agent turn to
one of several named chat clients (routes), and to switch the active route mid-conversation without
losing the conversation history.

The `RoutePersistingRoutingChatClient` derives from the `RoutingChatClient` in `Microsoft.Extensions.AI`
and stores the route that is active for a session in the session's state bag. The selection
therefore survives for the lifetime of the session and across session serialization.

Because the conversation history is kept client side by the agent's chat history provider, the full
history is replayed to whichever model handles the next turn, so switching route preserves the
conversation.

> [!WARNING]
> Ensure that none of the chat clients registered as routes use service-stored chat history.
> Routing relies on the agent keeping history client side so it can share the complete conversation
> with whichever client handles the next turn. Service-stored history is isolated to its originating
> service and cannot be shared across routes, so switching routes would lose conversation context.

## What it demonstrates

- Registering multiple named routes, each backed by an ordinary `IChatClient`.
- Adding, replacing, or removing routes after constructing the routing client.
- Choosing the route a new session starts on with `RoutePersistingRoutingChatClientOptions.DefaultRoute`.
- Reading the active route for a session with `GetActiveRoute`.
- Changing the active route for a session with `SetActiveRoute`.
- Preserving the conversation across a route change by keeping chat history client side.

## Commands

| Command | Description |
|---|---|
| `/route` | Show the route that is currently active for the session |
| `/route <name>` | Switch the session to the named route |
| `/exit` | Quit (an empty line also exits) |

## Configuration

| Environment variable | Required | Description |
|---|---|---|
| `FOUNDRY_PROJECT_ENDPOINT` | Yes | The Foundry project endpoint. |
| `FOUNDRY_MODEL` | No | The primary model deployment name. Defaults to `gpt-5.4-mini`. |
| `FOUNDRY_MODEL_ALTERNATE` | No | The secondary model deployment name. Defaults to `gpt-5.4`. |

## Running the sample

```bash
export FOUNDRY_PROJECT_ENDPOINT="<your-foundry-project-endpoint>"
dotnet run
```

## Notes

- The routing client resolves the session from the ambient agent run context, so it must be invoked
  as part of an `AIAgent.RunAsync` or `AIAgent.RunStreamingAsync` call.
- The `Routes` dictionary is mutable but is not thread-safe. Modify it only while no requests are in
  flight. Route entries are validated only when selected, so an unused incomplete entry does not
  prevent other routes from operating.
- For routing policies that are not persisted per session, such as content-based or failover
  routing, use the routing clients provided by `Microsoft.Extensions.AI` directly.
