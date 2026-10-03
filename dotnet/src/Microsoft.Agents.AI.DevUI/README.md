# Microsoft.Agents.AI.DevUI

This package provides a web interface for testing and debugging AI agents during development.

> [!WARNING]
> DevUI is intended for development only. Its endpoints surface agent system instructions, tool definitions, model identifiers, and workflow structure. Do not expose DevUI to untrusted callers. By default, DevUI rejects any request whose remote endpoint is not a loopback address; see [Security](#security) below for the available options.

## Installation

```bash
dotnet add package Microsoft.Agents.AI.DevUI
dotnet add package Microsoft.Agents.AI.Hosting
dotnet add package Microsoft.Agents.AI.Hosting.OpenAI
```

## Usage

Add DevUI services and map the endpoint in your ASP.NET Core application:

```csharp
using Microsoft.Agents.AI.DevUI;
using Microsoft.Agents.AI.Hosting;
using Microsoft.Agents.AI.Hosting.OpenAI;

var builder = WebApplication.CreateBuilder(args);

// Register your agents
builder.AddAIAgent("assistant", "You are a helpful assistant.")
    .WithInMemorySessionStore(withIsolation: false); // Single-user local development only.

// Register DevUI services
if (builder.Environment.IsDevelopment())
{
    builder.AddDevUI();
}

// Register services for OpenAI responses and conversations (also required for DevUI)
builder.AddOpenAIResponses();
builder.AddOpenAIConversations();

var app = builder.Build();

// Map endpoints for OpenAI responses and conversations (also required for DevUI)
app.MapOpenAIResponses();
app.MapOpenAIConversations();

if (builder.Environment.IsDevelopment())
{
    // Map DevUI endpoint to /devui
    app.MapDevUI();
}

app.Run();
```

## Sessions across conversation turns

DevUI sends each turn as a separate HTTP request. The conversation ID identifies
the conversation, but preserving an agent's `AgentSession.StateBag` between those
requests also requires a session store on that agent's registration. The usage
example enables this with `WithInMemorySessionStore(withIsolation: false)` for
single-user local development. The default `withIsolation: true` requires an
`AgentIsolationKeyProvider`; configure that provider and endpoint authorization
when serving multiple callers, as shown in the shared hosting guide below.

This is separate from a `ChatHistoryProvider`: that provider reads and writes
messages for the session it receives. Registering a custom history provider does
not itself persist the enclosing session. Without an `AgentSessionStore`, the
host creates a new agent session for the request, so a `ProviderSessionState<T>`
initializer can run again even while DevUI is displaying the same conversation.
`AddOpenAIConversations()` supplies the protocol's conversation storage; it does
not replace the agent session store.

Configure the store on the `IHostedAgentBuilder` returned by `AddAIAgent(...)`,
including when that call uses a factory to create an agent with a custom
`ChatHistoryProvider`. Keep using the same conversation in DevUI for follow-up
turns; starting a new conversation should create separate session state.

The in-memory store is useful for local development and loses state on restart.
Use `WithSessionStore(...)` with a persistent implementation when sessions must
survive restarts or be shared across service instances. Authorize access to stored
sessions and configure caller isolation as described in the
[shared hosting guide](../../samples/04-hosting/README.md); a conversation ID alone
does not establish ownership.

## Function approvals

Function approval requires an agent session store. The approval request and the user's
decision arrive in separate HTTP requests. The store preserves the server-recorded
request so the decision can be matched to the exact function call shown in DevUI,
rather than trusting function details supplied by the caller.

Configure a session store on every agent that exposes an
`ApprovalRequiredAIFunction`:

```csharp
builder.AddAIAgent("assistant", "You are a helpful assistant.")
    .WithInMemorySessionStore(withIsolation: false); // Single-user local development only.
```

`WithInMemorySessionStore()` preserves approvals between requests but loses them
when the application restarts. Use `WithSessionStore(...)` with persistent storage
when approvals must survive restarts or move between service instances.

If a client sends `function_approval_response` for an agent without a configured
session store, the Responses endpoint returns HTTP 400:

```text
Approval-required function calling is not supported because no AgentSessionStore is configured.
```

The endpoint also returns HTTP 400 when `request_id` is unknown or belongs to a
different stored session. This prevents an approval issued in one conversation
from authorizing a function call in another.

For a streaming response, wait for its terminal event before sending the
`function_approval_response`. The server persists the approval checkpoint before
publishing `response.completed`. A decision sent while the originating stream is
still in progress is rejected with HTTP 400 because that approval is not yet
available for continuation.

## Security

DevUI exposes `/v1/entities` and `/v1/entities/{id}/info`, which return agent metadata including the system prompt (`ChatClientAgent.Instructions`). To prevent accidental disclosure, the DevUI route group is wrapped in a small endpoint filter that:

- Rejects requests from any non-loopback `RemoteIpAddress` with HTTP 403 by default.
- Optionally requires a shared bearer token on every request.

Configure via `DevUIOptions`:

```csharp
builder.AddDevUI(options =>
{
    // Allow non-loopback callers. Set this only when the host fronts DevUI with
    // its own authentication or network policy.
    options.AllowRemoteAccess = true;

    // Optional: require Authorization: Bearer <token> on every request.
    // Falls back to the DEVUI_AUTH_TOKEN environment variable when null.
    options.AuthToken = builder.Configuration["DevUI:AuthToken"];

    // Optional: attach a real authorization policy or rate limiting.
    options.ConfigureEndpoints = group => group.RequireAuthorization("DevUIPolicy");
});
```

The bundled bearer-token check uses constant-time comparison and is intended as a convenience for development scenarios. Production hosts should prefer a real ASP.NET Core authentication scheme via `ConfigureEndpoints`.

The DevUI route filter is not a substitute for authorization and caller isolation on separately mapped OpenAI Responses/Conversations endpoints. Protect each backend route group independently, and supply credentials compatible with that configuration. A shared DevUI token is not a per-user identity. See the [shared hosting guide](../../samples/04-hosting/README.md#development-tools).
