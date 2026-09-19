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
    options.MapInboundClaims = false;
    options.Authority = builder.Configuration["Auth:Authority"]
        ?? throw new InvalidOperationException("Auth:Authority is required.");
    options.Audience = builder.Configuration["Auth:Audience"]
        ?? throw new InvalidOperationException("Auth:Audience is required.");
});
builder.Services.AddAuthorizationBuilder()
    .AddPolicy("InvokeAgent", policy => policy
        .RequireAuthenticatedUser()
        .RequireClaim("roles", "Agent.Invoke"));
```

After building the app, replace the two protocol mappings with protected mappings:

```csharp
app.UseAuthentication();
app.UseAuthorization();
app.MapA2AHttpJson(policyAgent, "/").RequireAuthorization("InvokeAgent");
app.MapA2AJsonRpc(policyAgent, "/").RequireAuthorization("InvokeAgent");
```

The `MapInboundClaims = false` setting keeps the `roles` claim's token name.
Configure your identity provider to issue the
`Agent.Invoke` application role to authorized callers. If your provider uses a
different role claim or delegated scopes, adapt the named policy to that contract;
space-delimited scope claims require checking individual scope values.
Keep issuer, audience, signature, and lifetime validation enabled. The invocation
policy does not grant permission to perform every business operation. See the
[expense authorization sample](../AspNetAgentAuthorization/README.md) for endpoint
policies and authorization inside tools.

Decide separately whether the well-known agent card should be public. Publishing
a card does not authorize invocation. If discovery is protected, its HTTP requests
need authentication too. Advertise the actual security requirements in the agent
card; card metadata does not configure ASP.NET Core enforcement. To protect the
card with the same policy, replace its mapping with:

```csharp
app.MapWellKnownAgentCard(policyAgentCard).RequireAuthorization("InvokeAgent");
```

For persisted sessions and tasks, also configure caller isolation as described in
[the server setup](./A2AServer/Program.cs). Register the required HTTP context
accessor before building the app:

```csharp
builder.Services.AddHttpContextAccessor();
```

With inbound claim mapping disabled, choose the actual token claim (for example,
`sub`) in the isolation provider instead of a mapped `ClaimTypes.NameIdentifier`.
Use a validated identity claim with an
appropriate issuer/tenant boundary, not a caller-supplied context or task ID.

## Authenticate the calling agent

For protected discovery and invocation, supply an authenticated `HttpClient` to
both the resolver and `GetAIAgentAsync` in `A2AClient/Program.cs`:

```csharp
using var handler = new HttpClientHandler { AllowAutoRedirect = false };
using var httpClient = new HttpClient(handler);
httpClient.DefaultRequestHeaders.Authorization =
    new System.Net.Http.Headers.AuthenticationHeaderValue(
        "Bearer",
        Environment.GetEnvironmentVariable("A2A_ACCESS_TOKEN")
            ?? throw new InvalidOperationException("A2A_ACCESS_TOKEN is required."));

var agentCardResolver = new A2ACardResolver(new Uri(agentUrl), httpClient);
AIAgent policyAgent = await agentCardResolver.GetAIAgentAsync(httpClient: httpClient);
```

This replaces both the existing resolver construction and `GetAIAgentAsync()`
call. Define `agentUrl` from `A2A_AGENT_URL` as in the sample. The token must be issued for
the A2A host's audience. Use HTTPS and a trusted, configured agent-card origin;
verify advertised service URLs before sending credentials to them. This example
uses one token for one console user. It does not acquire or refresh tokens.

The resolver fetches the card before constructing the agent. Passing the client
to both the resolver constructor and `GetAIAgentAsync` authenticates discovery
and invocation. Supplying it only to `GetAIAgentAsync` leaves discovery unauthenticated.

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
