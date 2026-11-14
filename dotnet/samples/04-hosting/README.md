# Hosting agents for multiple callers

The .NET hosting packages expose agents through several protocols. Authentication, endpoint authorization, and caller isolation are separate responsibilities; enabling one does not enable the others.

## Choose the appropriate hosting model

| Hosting surface | Endpoint access | Caller-scoped resources |
| --- | --- | --- |
| AG-UI | Protect the endpoints returned by `MapAGUIServer`. | Persisted agent sessions, including continuation and approval state. Without a session store, sessions are ephemeral. |
| A2A | Protect both HTTP+JSON and JSON-RPC endpoints when both are exposed. | Sessions and tasks. The built-in task store retains tasks even when session persistence is disabled. |
| OpenAI Responses / Conversations | Protect every mapped Responses and Conversations route group. | Responses, conversations, conversation listings, and configured agent sessions. Response/conversation storage does not depend on explicitly registering an `AgentSessionStore`. The mapping does not wrap a configured agent session store; register it with an isolation-enabled helper or wrap it explicitly. |
| OpenAI Chat Completions | Protect the endpoints returned by `MapOpenAIChatCompletions`. | This adapter does not itself persist conversations across requests. Any additional application-owned state needs its own isolation. |
| Core Hosting / AzureStorage | These libraries do not expose HTTP endpoints. The host owns access control. | Session-store helpers can wrap stores with caller isolation; storage credentials alone do not identify the caller. |
| DevUI / Aspire DevUI | Development only; protect both the UI/proxy and the backend services. | Backend Responses/Conversations endpoints still require their own caller isolation. See [Development tools](#development-tools). |

## Authentication, authorization, and isolation

- **Authentication** establishes who is calling. Configure an authentication scheme that validates the credentials sent to your application. `DefaultAzureCredential` and `az login` authenticate the server to Azure services; they do not authenticate incoming application requests.
- **Authorization** determines whether that caller may access an endpoint or perform an operation. Apply `RequireAuthorization()` with an appropriate policy, protect a route group, or configure a fallback policy. Tool implementations must also enforce any resource-specific permissions they require.
- **Isolation** determines which stored resources that caller can access. A `threadId`, `contextId`, `taskId`, response ID, or conversation ID is a continuation or lookup identifier, not proof of ownership.

Requiring login alone does not isolate stored state. Conversely, an isolation provider does not authenticate callers or authorize access to agents and tools. A multi-user host needs both endpoint access control and isolation of retained caller data, including data held only in memory.

## Configure claims-based isolation in an ASP.NET Core host

This configuration applies to the built-in AG-UI, A2A, and OpenAI Responses/Conversations hosting paths. Reference `Microsoft.Agents.AI.Hosting.AspNetCore` for the claims-based provider.

First configure a real [ASP.NET Core authentication scheme](https://learn.microsoft.com/aspnet/core/security/authentication/) with `AddAuthentication(...).Add...(...)`. The following additions assume that scheme already exists; they do not validate credentials on their own.

Before `builder.Build()`:

```csharp
using Microsoft.Agents.AI.Hosting;

builder.Services.AddAuthorization();
builder.Services.AddHttpContextAccessor();
builder.Services.UseClaimsBasedAgentIsolation();
```

Register the agent and protocol services as required by the selected sample. After `builder.Build()`, enable the middleware:

```csharp
app.UseAuthentication();
app.UseAuthorization();
```

Apply authorization to each protocol endpoint you expose. For example, select the mappings relevant to your application; these are not a complete application:

```csharp
app.MapAGUIServer("/ag-ui", agent).RequireAuthorization();

app.MapA2AHttpJson(agent, "/a2a").RequireAuthorization();
app.MapA2AJsonRpc(agent, "/a2a-rpc").RequireAuthorization();

app.MapOpenAIResponses(agent).RequireAuthorization();
app.MapOpenAIConversations().RequireAuthorization();

app.MapOpenAIChatCompletions(agent).RequireAuthorization();
```

Use application-specific policies when not every authenticated caller should have access. Decide separately whether discovery endpoints, such as A2A agent cards, should be public. Do not assume that protecting one route also protects another protocol mapped by the same application.

### Choose the isolation boundary

`UseClaimsBasedAgentIsolation()` uses `ClaimTypes.NameIdentifier` by default. The authentication scheme must populate that claim with a stable identifier unique across the population served by the host. If the scheme uses an unmapped `sub` claim, configure that claim type instead:

```csharp
builder.Services.UseClaimsBasedAgentIsolation(new() { ClaimType = "sub" });
```

Use one provider registration, not both examples. Subjects and object IDs may only be unique within one issuer or tenant. A custom `AgentIsolationKeyProvider` may be needed to combine validated issuer/tenant and subject values. Do not derive identity from display names, client-supplied user IDs, or continuation identifiers. A tenant-only key intentionally shares a partition within that tenant; use a per-user key when users must be separated.

Custom providers can resolve trusted identity without ASP.NET Core claims or `IHttpContextAccessor`. The claims-based registration above is one supported approach, not a requirement for every hosting environment.

### Understand store defaults

The built-in AG-UI and A2A wiring adds isolation decorators where absent. With a provider registered, the added decorators require an isolation key. Without a provider, they allow unscoped access; that shared mode is not appropriate for retained data belonging to different callers. A2A also wraps its task store, independently of session persistence.

OpenAI Responses/Conversations use the registered provider to scope their own storage and lookup operations. This protection is needed even if no agent session store is configured. Unlike the AG-UI and A2A wiring, the Responses mapping does not add an isolation decorator to a configured agent session store. Register that store with one of the isolation-enabled helpers below, or wrap it in `IsolationKeyScopedAgentSessionStore`, so session and approval state is also scoped to the caller; a store registered directly as a keyed `AgentSessionStore` is used as-is.

The generic `WithSessionStore(...)`, `WithInMemorySessionStore(...)`, and `WithAzureBlobSessionStore(...)` helpers enable isolation by default. Their default strict wrapper requires a key, including when no provider is registered. Existing decorators retain their configured behavior. Do not disable strict isolation merely to make an authenticated multi-user application accept requests with missing identity claims.

### Authenticate every client request

Clients must send credentials on every operation, including streaming requests, continuations, approval responses, task retrieval/cancellation, and conversation management. Sample clients do not necessarily acquire or send tokens.

A web frontend signing in a user does not automatically authenticate its outbound calls to an agent backend. Forward an appropriate per-user credential through the supported authentication flow. One shared service credential would identify every caller as the same principal unless the backend has a separate, trusted delegated-identity mechanism.

## Application-owned routes and storage

The [bring-your-own-route samples](af-hosting/README.md) use `OpenAIResponses` conversion helpers rather than the built-in endpoint/storage wiring. Registering an isolation provider alone does not make arbitrary dictionaries, workflow checkpoints, or manually created stores caller-aware.

The application must authenticate and authorize the request, bind continuation identifiers to the trusted caller, and partition every application-owned store or wrap it explicitly. The same applies to memory, retrieval data, files, and caches outside the hosting stores.

## Development tools

[DevUI](../../src/Microsoft.Agents.AI.DevUI/README.md#security) and [Aspire DevUI](../../src/Aspire.Hosting.AgentFramework.DevUI/README.md) are development tools, not production authentication gateways. Keep them accessible only to trusted developers.

Do not assume that protecting the UI, the Aspire dashboard, or a reverse proxy also protects independently reachable backend endpoints. Apply the backend protocol's authorization and isolation requirements separately. A shared development token is not a per-user identity, and enabling backend authorization also requires a client/proxy credential flow compatible with it.

## Related samples

- [AG-UI configuration and client requirements](../02-agents/AGUI/README.md#security-considerations)
- [A2A client and server](../05-end-to-end/A2AClientServer/README.md)
- [Application-owned Responses routes](af-hosting/README.md)
- [Agent and tool authorization](../05-end-to-end/AspNetAgentAuthorization/README.md)
