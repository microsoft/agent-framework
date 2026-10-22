# Microsoft.Agents.AI.DevUI

This package provides a web interface for testing and debugging AI agents during development.

> [!WARNING]
> DevUI is intended for development only. Its endpoints surface agent system instructions, tool definitions, model identifiers, and workflow structure. Do not expose DevUI to untrusted callers. By default, DevUI requires a loopback network peer and loopback Host, and rejects cross-site state-changing browser requests; see [Security](#security) below for the available options.

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
builder.AddAIAgent("assistant", "You are a helpful assistant.");

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

## Function approvals

Function approval requires an agent session store. The approval request and the user's
decision arrive in separate HTTP requests. The store preserves the server-recorded
request so the decision can be matched to the exact function call shown in DevUI,
rather than trusting function details supplied by the caller.

Configure a session store on every agent that exposes an
`ApprovalRequiredAIFunction`:

```csharp
builder.AddAIAgent("assistant", "You are a helpful assistant.")
    .WithInMemorySessionStore();
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

DevUI exposes `/v1/entities` and `/v1/entities/{id}/info`, which return agent metadata including the system prompt (`ChatClientAgent.Instructions`). `AddDevUI()` also automatically applies the local peer, Host, and browser-origin checks to the standard `/v1/responses` and `/v1/conversations` paths and their descendants, regardless of where those endpoints are mapped in the application. A configured DevUI token protects the UI and entity endpoints mapped by `MapDevUI()`; it is not automatically imposed on those separately mapped standard backend routes.

In the default local mode, DevUI:

- Requires a loopback `RemoteIpAddress`.
- Requires the `Host` header to be `localhost` or a loopback IPv4 or IPv6 address.
- Rejects state-changing requests when `Origin` is invalid or does not match the request origin.
- Rejects state-changing requests with `Sec-Fetch-Site: cross-site`.
- Allows non-browser clients that send neither `Origin` nor `Sec-Fetch-Site`.
- Optionally requires a shared bearer token on the endpoints mapped by `MapDevUI()`.

Local-access and browser-request failures return HTTP 403. Missing or invalid configured tokens return HTTP 401 with `WWW-Authenticate: Bearer`. The `/meta` endpoint remains unauthenticated so the frontend can discover whether a token is required.

Configure via `DevUIOptions`:

```csharp
builder.AddDevUI(options =>
{
    // Skip the built-in peer, Host, and browser-origin restrictions. Set this
    // only when the host supplies its own network and browser-request policy.
    options.AllowRemoteAccess = true;

    // Optional: require a bearer token on the UI and entity endpoints mapped
    // by MapDevUI(). Separately mapped standard backend routes do not inherit it.
    // Falls back to the DEVUI_AUTH_TOKEN environment variable when null.
    options.AuthToken = builder.Configuration["DevUI:AuthToken"];

    // Optional: attach a real authorization policy or rate limiting.
    options.ConfigureEndpoints = group => group.RequireAuthorization("DevUIPolicy");
});
```

`AllowRemoteAccess=true` skips the built-in peer, Host, and browser-origin restrictions, but it does not skip a configured bearer token on the endpoints mapped by `MapDevUI()`. The bundled token check uses constant-time comparison and is intended as a convenience for development scenarios.

Automatic local backend checks are intentionally limited to the standard `/v1/responses` and `/v1/conversations` paths and their descendants. Custom OpenAI endpoint paths are not detected or protected. Neither `AuthToken` nor `ConfigureEndpoints` is automatically applied to separately mapped backend endpoints; attach host-supplied authorization directly when needed. A shared DevUI token is not a per-user identity.

The built-in local checks reduce direct local-development risks; they are not a production authentication boundary and cannot authenticate the original caller when a public reverse proxy makes requests appear local. Reverse-proxied exposure requires host-owned authentication and network policy, normally with `AllowRemoteAccess=true` so the proxy traffic is evaluated by those host controls rather than DevUI's direct-loopback assumptions. See the [shared hosting guide](../../samples/04-hosting/README.md#development-tools).
