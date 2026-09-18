# Authentication and tool authorization

The default sample is an anonymous local demonstration. An authenticated
deployment has three separate boundaries:

```text
User or calling agent -- token for A2A host --> A2A host
    --> local tool authorization
    --> downstream API -- token for that API --> business system
```

Agent instructions and tool descriptions do not enforce permissions. Enforce
authorization in the host and in the tool implementation.

## Protect the A2A host

Use ASP.NET Core authentication and authorization. With the
`Microsoft.AspNetCore.Authentication.JwtBearer` package referenced, register
JWT bearer validation before `builder.Build()` in `A2AServer/Program.cs`:

```csharp
builder.Services.AddAuthentication("Bearer").AddJwtBearer(options =>
{
    options.Authority = builder.Configuration["Auth:Authority"]
        ?? throw new InvalidOperationException("Auth:Authority is required.");
    options.Audience = builder.Configuration["Auth:Audience"]
        ?? throw new InvalidOperationException("Auth:Audience is required.");
});
builder.Services.AddAuthorization();
```

After building the app, replace the two protocol mappings with protected mappings:

```csharp
app.UseAuthentication();
app.UseAuthorization();
app.MapA2AHttpJson(policyAgent, "/").RequireAuthorization();
app.MapA2AJsonRpc(policyAgent, "/").RequireAuthorization();
```

Keep issuer, audience, signature, and lifetime validation enabled. Add authorization
policies for the scopes or roles your service requires; authentication alone does
not grant permission to perform every business operation. See the
[expense authorization sample](../AspNetAgentAuthorization/README.md) for endpoint
policies and authorization inside tools.

Decide separately whether the well-known agent card should be public. Publishing
a card does not authorize invocation. If discovery is protected, its HTTP requests
need authentication too. Advertise the actual security requirements in the agent
card; card metadata does not configure ASP.NET Core enforcement.

For persisted sessions and tasks, also configure caller isolation as described in
[the server setup](./A2AServer/Program.cs). Use a validated identity claim with an
appropriate issuer/tenant boundary, not a caller-supplied context or task ID.

## Authenticate the calling agent

For a public agent card and a protected invocation endpoint, supply an authenticated
`HttpClient` to `GetAIAgentAsync` in `A2AClient/Program.cs`:

```csharp
using var handler = new HttpClientHandler { AllowAutoRedirect = false };
using var httpClient = new HttpClient(handler);
httpClient.DefaultRequestHeaders.Authorization =
    new System.Net.Http.Headers.AuthenticationHeaderValue(
        "Bearer",
        Environment.GetEnvironmentVariable("A2A_ACCESS_TOKEN")
            ?? throw new InvalidOperationException("A2A_ACCESS_TOKEN is required."));

AIAgent policyAgent = await agentCardResolver.GetAIAgentAsync(httpClient: httpClient);
```

This replaces the existing `GetAIAgentAsync()` call. The token must be issued for
the A2A host's audience. Use HTTPS and a trusted, configured agent-card origin;
verify advertised service URLs before sending credentials to them. This example
uses one token for one console user. It does not acquire or refresh tokens.

The resolver fetches the card before constructing the agent. The `httpClient`
argument above configures agent invocation, not the resolver's discovery request.
For protected discovery, configure authentication on the resolver's HTTP client
as well, using the A2A SDK's resolver configuration.

In a multi-user host, acquire a token for the current caller and destination through
your identity library and attach it to each outgoing request. Do not mutate shared
`DefaultRequestHeaders` with different users' tokens or retain one user's token in
a singleton agent. Keep credentials out of prompts, messages, and tool arguments.

## Authorize tools and downstream calls

For an in-process tool, read the validated caller identity from the host's current
request context and check the required permission before reading or changing
business data. The expense sample's
[user context](../AspNetAgentAuthorization/Service/UserContext.cs) and
[tool implementation](../AspNetAgentAuthorization/Service/ExpenseService.cs)
demonstrate this boundary. Session isolation does not replace tool authorization.

For a tool that calls a separate API, obtain an access token intended for that API.
An incoming token whose audience is the A2A host is not automatically valid for the
downstream service. For delegated user access with Microsoft Entra ID, use the
[on-behalf-of flow](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-on-behalf-of-flow)
with the downstream delegated permissions and required consent. Application-only
credentials represent the application, not the user; choose that model explicitly
and enforce the corresponding business authorization.

A2A transport and `GetAIAgentAsync` do not perform this token exchange for you.
For background work, the originating HTTP request may no longer exist: establish
an explicit identity and credential strategy rather than assuming an ambient
`HttpContext` remains available.

## Verify the boundaries

Before deployment, verify both protocol bindings reject missing/invalid tokens,
reject insufficient permissions, and allow an appropriately authorized caller.
Test discovery according to its intended public/protected policy. Test that one
caller cannot access another caller's retained session/task, and that a caller
who can chat still cannot invoke a tool without its required permission. For
delegation, verify the downstream API receives a token for its own audience and
enforces the user's permissions.
