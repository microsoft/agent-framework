// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ClientModel.Primitives;
using System.Diagnostics.CodeAnalysis;
using System.Linq;
using System.Runtime.CompilerServices;
using Azure.AI.AgentServer.Responses;
using Azure.Core;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Routing;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
using Microsoft.Extensions.Diagnostics.HealthChecks;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI.Foundry.Hosting;

/// <summary>
/// Extension methods for registering agent-framework agents as Foundry Hosted Agents
/// using the Azure AI Responses Server SDK.
/// </summary>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public static class FoundryHostingExtensions
{
    /// <summary>
    /// Registers the Azure AI Responses Server SDK and <see cref="AgentFrameworkResponseHandler"/>
    /// as the <see cref="ResponseHandler"/>. Agents are resolved from keyed DI services
    /// using the <c>agent.name</c> or <c>metadata["entity_id"]</c> from incoming requests.
    /// </summary>
    /// <remarks>
    /// <para>
    /// This method calls <c>AddResponsesServer()</c> internally, so you do not need to
    /// call it separately. Register your <see cref="AIAgent"/> instances before calling this.
    /// </para>
    /// <para>
    /// Example:
    /// <code>
    /// builder.Services.AddKeyedSingleton&lt;AIAgent&gt;("my-agent", myAgent);
    /// builder.Services.AddFoundryResponses();
    ///
    /// var app = builder.Build();
    /// app.MapFoundryResponses();
    /// </code>
    /// </para>
    /// </remarks>
    /// <param name="services">The service collection.</param>
    /// <returns>The service collection for chaining.</returns>
    public static IServiceCollection AddFoundryResponses(this IServiceCollection services)
    {
        ArgumentNullException.ThrowIfNull(services);
        services.AddResponsesServer();
        services.AddHealthChecks();
        services.TryAddSingleton<AgentSessionStore>(_ => FileSystemAgentSessionStore.CreateDefault());
        services.TryAddSingleton<ResponseHandler, AgentFrameworkResponseHandler>();
        return services;
    }

    /// <summary>
    /// Registers the Azure AI Responses Server SDK and a specific <see cref="AIAgent"/>
    /// as the handler for all incoming requests, regardless of the <c>agent.name</c> in the request.
    /// </summary>
    /// <remarks>
    /// <para>
    /// Use this overload when hosting a single agent. The provided agent instance is
    /// registered as both a keyed service and the default <see cref="AIAgent"/>.
    /// This method calls <c>AddResponsesServer()</c> internally.
    /// </para>
    /// <para>
    /// Example:
    /// <code>
    /// builder.Services.AddFoundryResponses(myAgent);
    ///
    /// var app = builder.Build();
    /// app.MapFoundryResponses();
    /// </code>
    /// </para>
    /// </remarks>
    /// <param name="services">The service collection.</param>
    /// <param name="agent">The agent instance to register.</param>
    /// <param name="agentSessionStore">The agent session store to use for managing agent sessions server-side. If null, a file-system session store is used, rooted at <c>/.checkpoints</c> when running in a Foundry hosted environment and <c>{cwd}/.checkpoints</c> locally.</param>
    /// <returns>The service collection for chaining.</returns>
    public static IServiceCollection AddFoundryResponses(this IServiceCollection services, AIAgent agent, AgentSessionStore? agentSessionStore = null)
    {
        ArgumentNullException.ThrowIfNull(services);
        ArgumentNullException.ThrowIfNull(agent);

        services.AddResponsesServer();
        services.AddHealthChecks();
        agentSessionStore ??= FileSystemAgentSessionStore.CreateDefault();

        if (!string.IsNullOrWhiteSpace(agent.Name))
        {
            services.TryAddKeyedSingleton(agent.Name, agent);
            services.TryAddKeyedSingleton(agent.Name, agentSessionStore);
        }

        // Also register as the default (non-keyed) agent so requests
        // without an agent name can resolve it (e.g., local dev tooling).
        services.TryAddSingleton(agent);
        services.TryAddSingleton(agentSessionStore);

        services.TryAddSingleton<ResponseHandler, AgentFrameworkResponseHandler>();
        return services;
    }

    /// <summary>
    /// Registers the Foundry Toolbox service, which eagerly connects to the Foundry Toolboxes
    /// MCP proxy at startup and provides MCP tools to <see cref="AgentFrameworkResponseHandler"/>.
    /// </summary>
    /// <remarks>
    /// <para>
    /// Each string in <paramref name="toolboxNames"/> is a toolbox name registered in the Foundry
    /// project. The proxy URL per toolbox is constructed as:
    /// <c>{FOUNDRY_PROJECT_ENDPOINT}/toolboxes/{toolboxName}/mcp?api-version=v1</c>
    /// </para>
    /// <para>
    /// When <c>FOUNDRY_PROJECT_ENDPOINT</c> is absent, startup succeeds without error and
    /// no tools are loaded (the container remains healthy per spec §2).
    /// </para>
    /// <para>
    /// Example:
    /// <code>
    /// builder.Services.AddFoundryToolboxes(credential, "my-toolbox", "another-toolbox");
    /// </code>
    /// </para>
    /// </remarks>
    /// <param name="services">The service collection.</param>
    /// <param name="credential">The <see cref="TokenCredential"/> used to authenticate with the Foundry Toolboxes MCP proxy.</param>
    /// <param name="toolboxNames">Names of the Foundry toolboxes to connect to.</param>
    /// <returns>The service collection for chaining.</returns>
    public static IServiceCollection AddFoundryToolboxes(
        this IServiceCollection services,
        TokenCredential credential,
        params string[] toolboxNames)
        => services.AddFoundryToolboxes(credential, configureOptions: null, toolboxNames);

    /// <summary>
    /// Registers the Foundry Toolbox service with additional options configuration.
    /// </summary>
    /// <param name="services">The service collection.</param>
    /// <param name="credential">The <see cref="TokenCredential"/> used to authenticate with the Foundry Toolboxes MCP proxy.</param>
    /// <param name="configureOptions">Callback to further configure <see cref="FoundryToolboxOptions"/> (e.g. set <see cref="FoundryToolboxOptions.StrictMode"/>).</param>
    /// <param name="toolboxNames">Names of the Foundry toolboxes to pre-register at startup.</param>
    /// <returns>The service collection for chaining.</returns>
    public static IServiceCollection AddFoundryToolboxes(
        this IServiceCollection services,
        TokenCredential credential,
        Action<FoundryToolboxOptions>? configureOptions,
        params string[] toolboxNames)
    {
        ArgumentNullException.ThrowIfNull(services);
        ArgumentNullException.ThrowIfNull(credential);

        if (services.Any(d => d.ServiceType == typeof(FoundryToolboxService)))
        {
            throw new InvalidOperationException(
                $"{nameof(FoundryToolboxService)} is already registered. " +
                $"Call {nameof(AddFoundryToolboxes)} only once per service collection.");
        }

        services.Configure<FoundryToolboxOptions>(opt =>
        {
            foreach (var name in toolboxNames)
            {
                if (!string.IsNullOrWhiteSpace(name))
                {
                    opt.ToolboxNames.Add(name);
                }
            }

            configureOptions?.Invoke(opt);
        });

        // Register FoundryToolboxService as a singleton, injecting the caller-provided credential
        // directly rather than resolving TokenCredential from DI.
        services.AddSingleton(sp => new FoundryToolboxService(
            sp.GetRequiredService<IOptions<FoundryToolboxOptions>>(),
            credential: credential,
            sp.GetService<ILogger<FoundryToolboxService>>()));
        services.AddHostedService(sp => sp.GetRequiredService<FoundryToolboxService>());

        // Register the toolbox health check on the same /readiness pipeline that
        // MapFoundryResponses maps. This gates the Foundry hosted runtime's readiness
        // probe (per container-image-spec.md §3.1) on the outcome of the pre-registered
        // toolbox connections opened in FoundryToolboxService.StartAsync.
        // AddCheck<T>(name, ...) does NOT dedupe by name, so guard against a host that
        // already registered a health check with this name.
        const string HealthCheckName = "foundry-toolbox";
        services.AddHealthChecks();
        services.Configure<HealthCheckServiceOptions>(opts =>
        {
            foreach (var existing in opts.Registrations)
            {
                if (string.Equals(existing.Name, HealthCheckName, StringComparison.Ordinal))
                {
                    return;
                }
            }

            opts.Registrations.Add(new HealthCheckRegistration(
                name: HealthCheckName,
                factory: sp => ActivatorUtilities.CreateInstance<FoundryToolboxHealthCheck>(sp),
                failureStatus: HealthStatus.Unhealthy,
                tags: ["foundry", "toolbox", "readiness"]));
        });

        return services;
    }

    /// <summary>
    /// Maps the Responses API routes for the agent-framework handler to the endpoint routing pipeline.
    /// </summary>
    /// <remarks>
    /// <para>
    /// Also maps the Foundry-required <c>GET /readiness</c> health probe to
    /// <see cref="HealthCheckEndpointRouteBuilderExtensions.MapHealthChecks(IEndpointRouteBuilder, string)"/>
    /// when no <c>/readiness</c> route is already registered. This makes the package
    /// spec-compliant in the Foundry hosted runtime (which probes <c>/readiness</c>
    /// before accepting any invocation per <c>container-image-spec.md</c> §2; without
    /// it every request fails with HTTP 424 <c>session_not_ready</c>) regardless of the
    /// host spine the developer chose:
    /// </para>
    /// <list type="bullet">
    ///   <item><description><b>Tier 1/2</b> (<c>AgentHost.CreateBuilder</c>) — the Core SDK
    ///         already maps <c>/readiness</c>. The duplicate-route guard below skips
    ///         re-mapping it.</description></item>
    ///   <item><description><b>Tier 3</b> (<c>WebApplication.CreateBuilder</c> +
    ///         <c>AddFoundryResponses</c> + <c>MapFoundryResponses</c>) — the Core SDK
    ///         does NOT map it. This call covers the gap automatically.</description></item>
    /// </list>
    /// <para>
    /// Developers can still opt out by registering their own <c>/readiness</c> route
    /// before calling <c>MapFoundryResponses</c>; the existing route is detected and
    /// preserved.
    /// </para>
    /// </remarks>
    /// <param name="endpoints">The endpoint route builder.</param>
    /// <param name="prefix">Optional route prefix (e.g., "/openai/v1"). Default: empty (routes at /responses).</param>
    /// <returns>The endpoint route builder for chaining.</returns>
    public static IEndpointRouteBuilder MapFoundryResponses(this IEndpointRouteBuilder endpoints, string prefix = "")
    {
        ArgumentNullException.ThrowIfNull(endpoints);
        endpoints.MapResponsesServer(prefix);
        MapReadinessIfMissing(endpoints);
        return endpoints;
    }

    /// <summary>
    /// Maps <c>GET /readiness</c> to the AspNetCore HealthChecks pipeline only when no
    /// route already serves that path. The duplicate guard scans
    /// <see cref="EndpointDataSource"/> entries by route pattern, which catches both the
    /// SDK-mapped <c>MapHealthChecks("/readiness")</c> path used by
    /// <c>AgentHostBuilder</c> and any user-registered <c>app.MapGet("/readiness", ...)</c>
    /// route. Idempotent across multiple <c>MapFoundryResponses</c> invocations.
    /// </summary>
    private static void MapReadinessIfMissing(IEndpointRouteBuilder endpoints)
    {
        const string ReadinessPath = "/readiness";

        foreach (var dataSource in endpoints.DataSources)
        {
            foreach (var endpoint in dataSource.Endpoints)
            {
                if (endpoint is RouteEndpoint route &&
                    string.Equals(route.RoutePattern.RawText, ReadinessPath, StringComparison.OrdinalIgnoreCase))
                {
                    return;
                }
            }
        }

        endpoints.MapHealthChecks(ReadinessPath);
    }

    /// <summary>
    /// The ActivitySource name for the Responses hosting pipeline.
    /// </summary>
    private const string ResponsesSourceName = "Azure.AI.AgentServer.Responses";

    /// <summary>
    /// Wraps <paramref name="agent"/> with <see cref="OpenTelemetryAgent"/> instrumentation
    /// so that agent invocations emit spans into the pipeline registered by
    /// <c>Azure.AI.AgentServer.Core</c>'s <c>AddAgentHostTelemetry()</c>.
    /// If the agent is already instrumented the original instance is returned unchanged.
    /// </summary>
    internal static AIAgent ApplyOpenTelemetry(AIAgent agent)
    {
        if (agent.GetService<OpenTelemetryAgent>() is not null)
        {
            return agent;
        }

        return agent.AsBuilder()
                    .UseOpenTelemetry(sourceName: ResponsesSourceName)
                    .Build();
    }

    /// <summary>
    /// Registers the hosted-agent <c>User-Agent</c> supplement policy
    /// (<see cref="HostedAgentUserAgentPolicy"/>) on the agent's underlying chat client via the
    /// MEAI 10.5.1 <see cref="OpenAIRequestPolicies"/> hook so every outgoing OpenAI Responses
    /// request carries the segment <c>foundry-hosting/agent-framework-dotnet/{version}</c>.
    /// </summary>
    /// <remarks>
    /// <para>
    /// Best-effort and idempotent. The method is a no-op when:
    /// <list type="bullet">
    /// <item><description><paramref name="agent"/> exposes no <see cref="IChatClient"/>;</description></item>
    /// <item><description>the chat client is not OpenAI-backed (the <see cref="OpenAIRequestPolicies"/> service lookup returns <see langword="null"/>);</description></item>
    /// <item><description>the policy was already registered on this client by a prior invocation (deduped via reflection on <c>OpenAIRequestPolicies._entries</c>).</description></item>
    /// </list>
    /// </para>
    /// <para>
    /// Returns the same <paramref name="agent"/> instance unchanged. The policy is installed
    /// on the chat client; the agent itself is not wrapped.
    /// </para>
    /// </remarks>
    internal static AIAgent TryApplyUserAgent(AIAgent agent)
    {
        var chatClient = agent.GetService<IChatClient>();
        if (chatClient?.GetService<OpenAIRequestPolicies>() is { } policies)
        {
            // Hosted agents are typically singletons resolved per request, so AddPolicy must be
            // called at most once per OpenAIRequestPolicies instance to avoid unbounded growth of
            // the policy list (each entry adds per-request CPU work even though the User-Agent
            // value stays stable). Track which instances we have already wired with a
            // ConditionalWeakTable keyed on the OpenAIRequestPolicies reference; the table holds
            // weak references so it does not extend the lifetime of the chat client.
            if (s_userAgentRegistrations.TryAdd(policies, s_boxedTrue))
            {
                policies.AddPolicy(HostedAgentUserAgentPolicy.Instance, PipelinePosition.PerCall);
            }
        }

        return agent;
    }

    private static readonly object s_boxedTrue = new();
    private static readonly ConditionalWeakTable<OpenAIRequestPolicies, object> s_userAgentRegistrations = new();
}
