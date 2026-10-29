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

Configure caller isolation for retained sessions and tasks, including tasks kept
in memory when session persistence is disabled. Reference
`Microsoft.Agents.AI.Hosting.AspNetCore` and register the provider before
`builder.Build()`:

```csharp
using Microsoft.Agents.AI.Hosting;

builder.Services.AddHttpContextAccessor();
builder.Services.UseClaimsBasedAgentIsolation(new() { ClaimType = "sub" });
```

With `MapInboundClaims = false`, `sub` is the token's unmapped subject claim.
This example assumes a single trusted issuer and tenant. For multiple issuers or
tenants, choose a validated identity boundary that prevents subject collisions;
see [Choose the isolation boundary](../../04-hosting/README.md#choose-the-isolation-boundary)
in the shared hosting guide. Never use a caller-supplied context or task ID as
proof of ownership. Authentication and endpoint authorization do not replace
isolation of retained caller data.

## Authenticate the calling agent

For an interactive console caller using Microsoft Entra ID, reference
`Microsoft.Identity.Client` in the client project and use
[MSAL device-code flow](https://learn.microsoft.com/en-us/entra/identity-platform/scenario-desktop-acquire-token-device-code-flow).
Register the console app as a public client and enable public client flows.
Expose a delegated permission on the A2A host app registration and grant the
console app that permission with the required consent. Configure:

- `A2A_AGENT_URL`: the trusted HTTPS agent-card base URL.
- `AZURE_TENANT_ID`: the tenant serving the A2A host.
- `AZURE_CLIENT_ID`: the console app registration's client ID.
- `A2A_SCOPE`: the A2A host's delegated scope, such as `api://<host-app-id>/access_as_user`.

The host policy above additionally requires `roles: Agent.Invoke`. To retain
that policy for this delegated example, enable the app role for users/groups and
assign it to the signed-in user in the host's enterprise application. Granting a
delegated scope alone does not satisfy the role policy. If using scope-based
endpoint authorization instead, replace the named policy with one that checks the
required individual value in the space-delimited `scp` claim. The token audience
must match the host's configured `Auth:Audience`, not the console application's
client ID.

Replace the existing resolver construction and `GetAIAgentAsync()` call in
`A2AClient/Program.cs` with the following. It authenticates discovery, validates
all advertised service origins, and only then constructs the calling agent:

```csharp
using Microsoft.Identity.Client;

var trustedOrigin = new Uri(Environment.GetEnvironmentVariable("A2A_AGENT_URL")
    ?? throw new InvalidOperationException("A2A_AGENT_URL is required."), UriKind.Absolute);
if (trustedOrigin.Scheme != Uri.UriSchemeHttps || !string.IsNullOrEmpty(trustedOrigin.UserInfo))
{
    throw new InvalidOperationException("Configure a trusted HTTPS agent URL without user information.");
}

var identityClient = PublicClientApplicationBuilder
    .Create(Environment.GetEnvironmentVariable("AZURE_CLIENT_ID")
        ?? throw new InvalidOperationException("AZURE_CLIENT_ID is required."))
    .WithAuthority(AzureCloudInstance.AzurePublic,
        Environment.GetEnvironmentVariable("AZURE_TENANT_ID")
            ?? throw new InvalidOperationException("AZURE_TENANT_ID is required."))
    .Build();
string[] scopes = [Environment.GetEnvironmentVariable("A2A_SCOPE")
    ?? throw new InvalidOperationException("A2A_SCOPE is required.")];
var authentication = await identityClient.AcquireTokenWithDeviceCode(scopes, deviceCode =>
{
    Console.WriteLine(deviceCode.Message);
    return Task.CompletedTask;
}).ExecuteAsync();

using var handler = new HttpClientHandler { AllowAutoRedirect = false };
using var httpClient = new HttpClient(handler);
httpClient.DefaultRequestHeaders.Authorization =
    new System.Net.Http.Headers.AuthenticationHeaderValue("Bearer", authentication.AccessToken);

var agentCardResolver = new A2ACardResolver(trustedOrigin, httpClient);
var card = await agentCardResolver.GetAgentCardAsync();
if (card.SupportedInterfaces is not { Count: > 0 })
{
    throw new InvalidOperationException("The agent card advertises no service interfaces.");
}

foreach (var service in card.SupportedInterfaces)
{
    if (!Uri.TryCreate(service.Url, UriKind.Absolute, out var serviceUri)
        || serviceUri.Scheme != trustedOrigin.Scheme
        || !string.Equals(serviceUri.IdnHost, trustedOrigin.IdnHost, StringComparison.OrdinalIgnoreCase)
        || serviceUri.Port != trustedOrigin.Port
        || !string.IsNullOrEmpty(serviceUri.UserInfo))
    {
        throw new InvalidOperationException("The agent card advertises an untrusted service URL.");
    }
}

AIAgent policyAgent = card.AsAIAgent(httpClient);
```

The configured discovery origin must be trusted before sending it a token.
The service checks require the same HTTPS scheme, hostname, and effective port;
redirects are disabled for both discovery and invocation. A card advertising a
different origin is rejected, even if it also lists a trusted interface.

This example acquires a token for one console user. For subsequent calls in a
long-running client, reuse the MSAL application and use `AcquireTokenSilent`
with the selected account, falling back to an interactive flow when required.
Acquire a valid token before sending each request rather than retaining an
expired authorization header. For unattended callers, use
[client credentials flow](https://learn.microsoft.com/en-us/entra/identity-platform/scenario-daemon-acquire-token)
with the host's `/.default` scope and an application-assigned `Agent.Invoke` role;
that identity represents the application rather than an interactive user.

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
