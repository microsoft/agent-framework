---
status: proposed
contact: Ashutosh0x
date: 2026-06-20
consulted: "@javiercn, @DeagleGross, @ReubenBond, @rogerbarreto, @westey-m, @TheEagleByte, @halllo, @Davidlmkh"
revised: 2026-06-20T16:40:00+05:30
---

# Unified Dynamic Agent Resolution Across AG-UI, OpenAI Responses, and A2A Endpoints

## Context and Problem Statement

All three hosting channel endpoint builders (`MapAGUI`, `MapOpenAIResponses`, `MapA2AHttpJson`) currently resolve the `AIAgent` instance and its `AgentSessionStore` **once at endpoint registration time** (app startup). This singleton-capture pattern prevents dynamic per-request agent resolution, which is required for multi-tenant agent platforms where route parameters (e.g., `/agents/{agentId}`) determine which agent handles each request.

Community contributors have proposed factory-delegate overloads for AG-UI (#3162, #2343), but the maintainers (@javiercn) correctly noted that this pattern must be applied consistently across all three channel types simultaneously — not just AG-UI.

### Current singleton-capture pattern (all three channels)

```csharp
// AG-UI — AGUIEndpointRouteBuilderExtensions.cs:105
var agentSessionStore = endpoints.ServiceProvider.GetKeyedService<AgentSessionStore>(aiAgent.Name);
var hostAgent = new AIHostAgent(aiAgent, agentSessionStore);

// Responses — EndpointRouteBuilderExtensions.Responses.cs:71
var executor = new AIAgentResponseExecutor(agent);

// A2A — A2AEndpointRouteBuilderExtensions.cs:69
var a2aServer = endpoints.ServiceProvider.GetKeyedService<A2AServer>(agentName);
```

### Pain points identified by the community

1. **No dynamic routing** — Cannot serve different agents based on route parameters (#2988, #3162)
2. **AgentSessionStore scoping broken** — Even scoped/transient session stores are captured as singletons at startup (@halllo, #3162 comment)
3. **HttpContextRoutingAgent workaround is brittle** — Requires overriding 5+ methods, couples agent logic to HTTP transport, `SerializeSession()` was not async (@halllo, @TheEagleByte)
4. **Forces per-agent infrastructure** — Without dynamic resolution, multi-agent hosts need separate endpoints per agent or fork the repo (@Davidlmkh)

## Decision Drivers

- **Consistency**: The same pattern must work across AG-UI, OpenAI Responses, and A2A
- **ASP.NET Core idiom**: Follow established patterns (`AddDbContext<T>()`, `AddAuthentication<THandler>()`, minimal API delegates)
- **Separation of concerns**: Agent resolution is a routing/infrastructure concern, not an agent behavior concern
- **Backward compatibility**: Existing single-agent `MapXxx(pattern, agent)` overloads must continue to work
- **Session store scoping**: Must support per-request session store resolution, not singleton capture

## Considered Options

### Option 1: HttpContextRoutingAgent (current workaround)

A delegating `AIAgent` subclass that uses `IHttpContextAccessor` to resolve the real agent at runtime.

**Pros**: Works today without framework changes
**Cons**: Couples agents to HTTP, requires overriding all virtual methods, session store still singleton-captured, reduces cohesion

### Option 2: Factory delegate overloads (PR #3162 approach)

Add `MapXxx` overloads accepting `Func<HttpContext, CancellationToken, ValueTask<AIAgent?>>`:

```csharp
app.MapAGUI("/agents/{agentId}", async (context, ct) =>
{
    var agentId = context.GetRouteValue("agentId")?.ToString();
    return await agentRepository.GetAgentByIdAsync(agentId, ct);
});
```

**Pros**: Familiar minimal API pattern, maximum flexibility
**Cons**: Channel-specific implementation needed for each `MapXxx`

### Option 4: Middleware pipeline with `Use(...)` + HttpContext on additional properties (@javiercn's suggestion)

Surface `HttpContext` on the agent options' additional properties, and use the existing ASP.NET Core middleware pipeline (`Use(...)`) for resolution logic:

```csharp
app.MapAGUI("/agents/{agentId}", defaultAgent)
    .Use(async (context, next) =>
    {
        var httpContext = context.HttpContext;
        var agentId = httpContext.GetRouteValue("agentId")?.ToString();

        // Resolve the actual agent from DI or a repository
        var resolver = httpContext.RequestServices.GetRequiredService<IAgentRepository>();
        var resolvedAgent = await resolver.GetAgentAsync(agentId);

        // Place the resolved agent on HttpContext.Items for downstream use
        httpContext.Items["ResolvedAgent"] = resolvedAgent;

        // Also resolve session store per-request (fixes singleton-capture)
        var sessionStore = httpContext.RequestServices
            .GetKeyedService<AgentSessionStore>(resolvedAgent?.Name);
        httpContext.Items["AgentSessionStore"] = sessionStore;

        await next(context);
    });
```

Alternatively, the framework could expose `HttpContext` on the options/additional properties directly, allowing resolution within a custom `DelegatingHandler` via `Use(...)`:

```csharp
// Framework-level change: expose HttpContext in agent options
public class AgentRequestOptions
{
    public HttpContext? HttpContext { get; set; }
    public IDictionary<string, object> AdditionalProperties { get; } = new Dictionary<string, object>();
}
```

**Pros**: No new abstractions needed, uses existing ASP.NET Core middleware pipeline, developers already know this pattern, `IHttpContextAccessor` is well-established
**Cons**: Initial `agent` parameter still required at registration (even if overridden at runtime), resolution logic duplicated unless wrapped in shared middleware

### Option 3: `IAgentResolver` interface with DI registration (recommended)

Define a shared `IAgentResolver` interface in the hosting core:

```csharp
public interface IAgentResolver
{
    ValueTask<AIAgent?> ResolveAgentAsync(HttpContext context, CancellationToken cancellationToken = default);
}
```

Registration:
```csharp
builder.Services.AddAgentResolver<RouteBasedAgentResolver>();
```

Endpoint mapping (no agent parameter):
```csharp
app.MapAGUI("/agents/{agentId}");
app.MapOpenAIResponses("/agents/{agentId}/v1/responses");
app.MapA2AHttpJson("/agents/{agentId}/a2a");
```

Each `MapXxx` overload resolves the agent per-request via `IAgentResolver` from DI.

**Pros**: Single interface for all channels, DI-native, testable, session stores resolved per-request
**Cons**: New abstraction to learn

## Maintainer Feedback

> **@javiercn** (June 20, 2026): "I don't feel strongly about what we do in this regard, provided we are consistent and that other folks like @DeagleGross and @ReubenBond @rogerbarreto or @westey-m are happy with the approach. That said, the IHttpContextAccessor pattern is not the end of the world, especially if the framework provided it. You can just wrap the agent, or the frameworks could simply put the HttpContext instance on the additional properties of the options, and you get to run your resolution logic within a delegating handler which you can already create with `Use(...)`"

Key takeaways from maintainer feedback:
1. **Consistency across channels** is the hard requirement — the specific mechanism is flexible
2. **`IHttpContextAccessor` + `Use(...)`** is an acceptable lightweight approach
3. **Exposing `HttpContext` on options/additional properties** would be a minimal framework change that unblocks dynamic resolution
4. Additional maintainer input requested from @DeagleGross (A2A hosting), @ReubenBond (Orleans/distributed), @rogerbarreto (.NET core), @westey-m (VectorData/Agent Framework)

## Decision Outcome

Revised recommendation: **Phased approach** incorporating @javiercn's feedback.

### Phase 1 (minimal, non-breaking) — Recommended immediate action

- Expose `HttpContext` on the options/additional properties for all three channels
- Document the `Use(...)` middleware pattern for per-request agent resolution
- Fix per-request `AgentSessionStore` resolution from `HttpContext.RequestServices`

This requires minimal framework changes and uses patterns ASP.NET Core developers already know.

### Phase 2 (convenience, if community demand warrants)

- Add factory delegate overloads for `MapXxx` (Option 2)
- Consider `IAgentResolver` as an optional DI-registered convenience layer (Option 3)

### Implementation plan

#### 1. Shared `IAgentResolver` interface (new, in `Microsoft.Agents.AI.Hosting`)

```csharp
namespace Microsoft.Agents.AI.Hosting;

/// <summary>
/// Resolves an <see cref="AIAgent"/> dynamically at request time.
/// Implementations can use route data, headers, claims, or any
/// request-scoped information to select the appropriate agent.
/// </summary>
public interface IAgentResolver
{
    /// <summary>
    /// Resolves an agent for the current request.
    /// Returns null if no agent matches, causing a 404 response.
    /// </summary>
    ValueTask<AIAgent?> ResolveAgentAsync(
        HttpContext context,
        CancellationToken cancellationToken = default);
}
```

#### 2. DI registration helper (new, in each hosting package)

```csharp
public static IServiceCollection AddAgentResolver<TResolver>(this IServiceCollection services)
    where TResolver : class, IAgentResolver
{
    services.AddHttpContextAccessor();
    services.AddScoped<IAgentResolver, TResolver>();
    return services;
}
```

#### 3. Per-request agent + session store resolution

The key fix: resolve `AgentSessionStore` per-request from `HttpContext.RequestServices` instead of capturing at startup:

```csharp
// Inside the endpoint delegate (per-request):
var agent = await resolver.ResolveAgentAsync(context, cancellationToken);
if (agent is null) return Results.NotFound();

// Resolve session store from the request's DI scope (not app-level)
var agentSessionStore = context.RequestServices.GetKeyedService<AgentSessionStore>(agent.Name)
    ?? new NoopAgentSessionStore();
```

#### 4. Factory delegate overloads (convenience API)

```csharp
// AG-UI
public static IEndpointConventionBuilder MapAGUI(
    this IEndpointRouteBuilder endpoints,
    string pattern,
    Func<HttpContext, CancellationToken, ValueTask<AIAgent?>> agentFactory);

// OpenAI Responses
public static IEndpointConventionBuilder MapOpenAIResponses(
    this IEndpointRouteBuilder endpoints,
    string? responsesPath,
    Func<HttpContext, CancellationToken, ValueTask<AIAgent?>> agentFactory);

// A2A
public static IEndpointConventionBuilder MapA2AHttpJson(
    this IEndpointRouteBuilder endpoints,
    string path,
    Func<HttpContext, CancellationToken, ValueTask<AIAgent?>> agentFactory);
```

#### 5. Error handling

| Scenario | Behavior |
|:---|:---|
| Factory/resolver returns `null` | 404 Not Found |
| Factory/resolver throws | 500 Internal Server Error + log |
| No resolver registered, no agent parameter | `InvalidOperationException` at startup |

### Usage examples

#### Route-based multi-tenant

```csharp
builder.Services.AddAgentResolver<RouteBasedAgentResolver>();

app.MapAGUI("/agents/{agentId}");
app.MapOpenAIResponses("/agents/{agentId}/v1/responses");
app.MapA2AHttpJson("/agents/{agentId}/a2a");

public class RouteBasedAgentResolver(IAgentRepository repo) : IAgentResolver
{
    public async ValueTask<AIAgent?> ResolveAgentAsync(HttpContext context, CancellationToken ct)
    {
        var agentId = context.GetRouteValue("agentId")?.ToString();
        return string.IsNullOrEmpty(agentId) ? null : await repo.GetAgentAsync(agentId, ct);
    }
}
```

#### Inline factory (quick prototyping)

```csharp
app.MapAGUI("/agents/{agentId}", async (context, ct) =>
{
    var agentId = context.GetRouteValue("agentId")?.ToString();
    return agentId switch
    {
        "weather" => weatherAgent,
        "search" => searchAgent,
        _ => null // 404
    };
});
```

## References

- #3162 — .NET: Support dynamic agent resolution in AG-UI endpoints (@TheEagleByte)
- #2343 — Earlier dynamic resolution PR (@halllo)
- #2988 — Original issue requesting dynamic agent selection
- @javiercn's [feedback on PR #6643](https://github.com/microsoft/agent-framework/pull/6643#issuecomment-4757378039): recommending `Use(...)` middleware + HttpContext on additional properties
- @javiercn's comment on #3162: "this needs to be applied not only to AG-UI but to Open AI responses and A2A"
- @halllo's `AgentSessionStore` scoping analysis (Feb 2026)
- @DeagleGross's A2A hosting task support (#3732) — relevant for A2A channel consistency
