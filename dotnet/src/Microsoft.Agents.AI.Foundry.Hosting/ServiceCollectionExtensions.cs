// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ClientModel.Primitives;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Globalization;
using System.Linq;
using System.Runtime.CompilerServices;
using Azure.AI.AgentServer.Responses;
using Azure.Core;
using Azure.Identity;
using Microsoft.Agents.AI.Workflows;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Routing;
using Microsoft.AspNetCore.Server.Kestrel.Core;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
using Microsoft.Extensions.Diagnostics.HealthChecks;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;

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
    /// <param name="configure">
    /// Optional callback to configure <see cref="FoundryResponsesOptions"/>, for example to allow the
    /// agent's own service to store the responses it produces.
    /// </param>
    /// <returns>The service collection for chaining.</returns>
    public static IServiceCollection AddFoundryResponses(this IServiceCollection services, Action<FoundryResponsesOptions>? configure = null)
    {
        _ = Throw.IfNull(services);
        AddResponsesServerOnce(services);
        services.AddHealthChecks();
        ConfigureFoundryListenPort(services);
        ConfigureFoundryResponsesOptions(services, configure);
        services.TryAddSingleton<AgentSessionStore>(_ => CreateDefaultAgentSessionStore());
        services.TryAddSingleton<ResponseHandler, AgentFrameworkResponseHandler>();
        MarkFeatureUsed();
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
    /// <param name="agentSessionStore">The agent session store to use for managing agent sessions server-side. If null, <see cref="FoundryAgentSessionStore"/> is used: the Foundry durable state store when hosted, and the AgentServer SDK's local state-store fallback otherwise.</param>
    /// <param name="configure">
    /// Optional callback to configure <see cref="FoundryResponsesOptions"/>, for example to allow the
    /// agent's own service to store the responses it produces.
    /// </param>
    /// <returns>The service collection for chaining.</returns>
    public static IServiceCollection AddFoundryResponses(
        this IServiceCollection services,
        AIAgent agent,
        AgentSessionStore? agentSessionStore = null,
        Action<FoundryResponsesOptions>? configure = null)
    {
        _ = Throw.IfNull(services);
        _ = Throw.IfNull(agent);

        AddResponsesServerOnce(services);
        services.AddHealthChecks();
        ConfigureFoundryListenPort(services);
        ConfigureFoundryResponsesOptions(services, configure);
        agentSessionStore ??= CreateDefaultAgentSessionStore();

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
        MarkFeatureUsed();
        return services;
    }

    /// <summary>
    /// Applies the caller's <see cref="FoundryResponsesOptions"/> and registers the readiness checks
    /// that report a misconfigured agent: one having its own service store the responses it produces,
    /// and a workflow agent writing its checkpoints somewhere hosting does not manage.
    /// </summary>
    /// <remarks>
    /// The checks are registered on the same <c>/readiness</c> pipeline that <see cref="MapFoundryResponses"/>
    /// maps, so such a container never takes traffic.
    /// <c>AddCheck</c> does not dedupe by name, so a repeated registration is guarded here.
    /// </remarks>
    private static void ConfigureFoundryResponsesOptions(IServiceCollection services, Action<FoundryResponsesOptions>? configure)
    {
        if (configure is not null)
        {
            services.Configure(configure);
        }

        AddReadinessCheckOnce(services, "foundry-stored-output", sp => ActivatorUtilities.CreateInstance<HostedStoredOutputHealthCheck>(sp));
        AddReadinessCheckOnce(services, "foundry-workflow-checkpointing", sp => ActivatorUtilities.CreateInstance<HostedWorkflowCheckpointingHealthCheck>(sp));
    }

    /// <summary>
    /// Registers a readiness check under a name, skipping the registration when that name is already
    /// taken, because <c>AddCheck</c> does not dedupe and both <c>AddFoundryResponses</c> overloads
    /// are documented as safe to call more than once.
    /// </summary>
    private static void AddReadinessCheckOnce(IServiceCollection services, string name, Func<IServiceProvider, IHealthCheck> factory) =>
        services.Configure<HealthCheckServiceOptions>(opts =>
        {
            foreach (var existing in opts.Registrations)
            {
                if (string.Equals(existing.Name, name, StringComparison.Ordinal))
                {
                    return;
                }
            }

            opts.Registrations.Add(new HealthCheckRegistration(
                name: name,
                factory: factory,
                failureStatus: HealthStatus.Unhealthy,
                tags: ["foundry", "responses", "readiness"]));
        });

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
        _ = Throw.IfNull(services);
        _ = Throw.IfNull(credential);

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
        _ = Throw.IfNull(endpoints);
        RouteGroupBuilder responsesEndpoints = endpoints.MapGroup(string.Empty);
        responsesEndpoints.AddEndpointFilter(new HostedProtocolCompatibilityFilter(
            endpoints.ServiceProvider.GetRequiredService<IConfiguration>(),
            endpoints.ServiceProvider.GetRequiredService<ILogger<HostedProtocolCompatibilityFilter>>()));
        responsesEndpoints.MapResponsesServer(prefix);
        MapReadinessIfMissing(endpoints);
        MarkFeatureUsed();
        return endpoints;
    }

    private static void MarkFeatureUsed()
    {
#pragma warning disable MAAI001
        FeatureUsage.MarkUsed((int)FeatureIndex.FoundryHosting);
#pragma warning restore MAAI001
    }

    /// <summary>
    /// Configuration key the Foundry hosting platform populates with a non-empty value inside a
    /// hosted container. It is the documented way for container code to detect a Foundry context.
    /// </summary>
    internal const string FoundryHostingEnvironmentKey = "FOUNDRY_HOSTING_ENVIRONMENT";

    /// <summary>
    /// Configuration key holding the HTTP listen port, matching the Agent Server SDK.
    /// </summary>
    internal const string ListenPortKey = "PORT";

    /// <summary>
    /// Port the Foundry hosted runtime probes and routes to when <see cref="ListenPortKey"/> is
    /// not set, matching <see cref="FoundryEnvironment.Port"/>.
    /// </summary>
    internal const int DefaultListenPort = 8088;

    /// <summary>
    /// Registers the Responses Server SDK exactly once per service collection.
    /// </summary>
    /// <remarks>
    /// <c>AddResponsesServer</c> registers a resilient task under a fixed name and throws when that
    /// name is already taken, so calling it a second time on the same service collection fails.
    /// Both <c>AddFoundryResponses</c> overloads are documented as safe to call more than once, and
    /// a host that registers several agents naturally does, so the second and later calls are
    /// skipped here.
    /// </remarks>
    private static void AddResponsesServerOnce(IServiceCollection services)
    {
        if (services.Any(static d => d.ServiceType == typeof(FoundryResponsesServerMarker)))
        {
            return;
        }

        services.AddSingleton<FoundryResponsesServerMarker>();
        services.AddResponsesServer();
    }

    /// <summary>
    /// Creates the <see cref="AgentSessionStore"/> used when the caller did not supply one.
    /// </summary>
    /// <remarks>
    /// The AgentServer SDK selects the backend. Inside a Foundry container it uses the platform's
    /// durable state store, which survives replacement and is readable by every instance. Anywhere
    /// else it uses the SDK's local state-store fallback under <c>~/.agentserver/state_stores</c>.
    /// </remarks>
    private static FoundryAgentSessionStore CreateDefaultAgentSessionStore() =>
        new(credential: CreateStateStoreCredential());

    /// <summary>
    /// Every agent a container can serve: the ones registered under a name, plus the default.
    /// </summary>
    /// <param name="serviceProvider">The provider the agents were registered with.</param>
    /// <returns>The registered agents, without duplicates.</returns>
    internal static List<AIAgent> ResolveRegisteredAgents(IServiceProvider serviceProvider)
    {
        var agents = new List<AIAgent>(serviceProvider.GetKeyedServices<AIAgent>(KeyedService.AnyKey));

        if (serviceProvider.GetService<AIAgent>() is { } defaultAgent && !agents.Contains(defaultAgent))
        {
            agents.Add(defaultAgent);
        }

        return agents;
    }

    /// <summary>
    /// Marker registered once per <see cref="IServiceCollection"/> so the Foundry listen-port
    /// configuration is applied at most once, even across multiple <c>AddFoundryResponses</c> calls.
    /// </summary>
    private sealed class FoundryListenPortMarker;

    /// <summary>
    /// Marker registered once per <see cref="IServiceCollection"/> so the Responses Server SDK is
    /// registered at most once, even across multiple <c>AddFoundryResponses</c> calls.
    /// </summary>
    private sealed class FoundryResponsesServerMarker;

    /// <summary>
    /// Binds Kestrel to the port the Foundry hosted runtime probes and routes to, so a plain
    /// <c>WebApplication.CreateBuilder</c> host (Tier 3) works with no Dockerfile. Mirrors
    /// <c>AgentHostBuilder</c>, which listens on the <c>PORT</c> value (default 8088).
    /// </summary>
    /// <remarks>
    /// <para>
    /// The listener is added only when configuration reports a Foundry container through
    /// <see cref="FoundryHostingEnvironmentKey"/>. A listener configured in code overrides the
    /// addresses a host resolves from configuration, so adding it everywhere would silently move
    /// any non-Foundry app off its configured address.
    /// </para>
    /// <para>
    /// Both values come from <see cref="IConfiguration"/> rather than from
    /// <see cref="FoundryEnvironment"/>, which caches every value in a static constructor. Reading
    /// through configuration keeps the decision observable when the host is built, honours the
    /// host's configuration sources, and lets tests supply values without mutating the process
    /// environment.
    /// </para>
    /// <para>
    /// Inside a Foundry container the listener cannot be skipped based on <c>ASPNETCORE_URLS</c>:
    /// the .NET base image always sets it to port 80, so such a guard would always trip and leave
    /// the container failing the readiness probe with HTTP 424. It cannot key off the presence of
    /// <c>PORT</c> either, because the platform sets that value only when it needs a port other
    /// than the default.
    /// </para>
    /// <para>
    /// Idempotent, and harmless when no Kestrel server is present (for example under
    /// <c>TestServer</c>): the <see cref="KestrelServerOptions"/> callback only runs when Kestrel
    /// is resolved.
    /// </para>
    /// </remarks>
    private static void ConfigureFoundryListenPort(IServiceCollection services)
    {
        if (services.Any(static d => d.ServiceType == typeof(FoundryListenPortMarker)))
        {
            return;
        }

        services.AddSingleton<FoundryListenPortMarker>();
        services.AddOptions<KestrelServerOptions>()
            .Configure<IConfiguration>(static (options, configuration) =>
            {
                if (string.IsNullOrEmpty(configuration[FoundryHostingEnvironmentKey]))
                {
                    return;
                }

                options.ListenAnyIP(ResolveListenPort(configuration));
            });
    }

    /// <summary>
    /// Reads the listen port from configuration, applying the same contract as
    /// <see cref="FoundryEnvironment.Port"/>: <see cref="DefaultListenPort"/> when unset, otherwise
    /// a port number in the range 1-65535.
    /// </summary>
    /// <exception cref="InvalidOperationException">The configured value is not a valid port.</exception>
    private static int ResolveListenPort(IConfiguration configuration)
    {
        var value = configuration[ListenPortKey];
        if (string.IsNullOrEmpty(value))
        {
            return DefaultListenPort;
        }

        if (!int.TryParse(value, NumberStyles.Integer, CultureInfo.InvariantCulture, out var port) || port is < 1 or > 65535)
        {
            throw new InvalidOperationException(
                $"The {ListenPortKey} environment variable value '{value}' is not a valid port number (1-65535).");
        }

        return port;
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
    /// Points a workflow-hosting agent at the Foundry durable state store for its checkpoints,
    /// when running inside a Foundry container.
    /// </summary>
    /// <remarks>
    /// <para>
    /// This runs when the agent is resolved for a request rather than when it is registered,
    /// because a host can register agents as factories that are only built later, and because a
    /// registered agent is a finished object whose checkpoint storage is fixed at construction.
    /// </para>
    /// <para>
    /// Without this, a hosted workflow keeps every checkpoint of a session inside the saved session
    /// record, and the platform limits a single record to 1 MB, so a long workflow eventually stops
    /// being able to save. With it, each checkpoint becomes its own record and the session keeps
    /// only the pointer to the last one.
    /// </para>
    /// <para>
    /// The method is a no-op when the agent does not host a workflow or when the workflow was built
    /// with an explicit checkpoint manager. The AgentServer SDK selects the hosted or local
    /// state-store backend. The redirected agent is cached against the agent it came from, so the
    /// substitution happens once rather than on every request.
    /// </para>
    /// </remarks>
    /// <param name="agent">The resolved agent.</param>
    /// <param name="loggerFactory">Creates the logger the checkpoint store reports through.</param>
    /// <returns>The agent to serve the request with.</returns>
    internal static AIAgent ApplyWorkflowCheckpointing(AIAgent agent, ILoggerFactory? loggerFactory = null)
    {
        return s_workflowCheckpointingAgents.GetValue(
            agent,
            source => source.WithCheckpointing(GetFoundryWorkflowCheckpointManager(loggerFactory)));
    }

    /// <summary>
    /// The single checkpoint manager shared by every hosted workflow in this process. It is created
    /// on first use so that no credential is built and no platform call is made when the process is
    /// not running on the platform, which also means the first caller supplies its logger.
    /// </summary>
    private static CheckpointManager GetFoundryWorkflowCheckpointManager(ILoggerFactory? loggerFactory)
    {
        lock (s_checkpointManagerGate)
        {
            return s_foundryWorkflowCheckpointManager ??= CheckpointManager.CreateJson(
                new FoundryJsonCheckpointStore(
                    credential: CreateStateStoreCredential(),
                    loggerFactory: loggerFactory));
        }
    }

    /// <summary>
    /// Creates the credential required by the hosted state-store backend. The beta.29 SDK requires
    /// no credential for its local fallback, so local development does not construct one.
    /// </summary>
    private static DefaultAzureCredential? CreateStateStoreCredential() =>
        FoundryEnvironment.IsHosted ? new DefaultAzureCredential() : null;

    private static readonly object s_checkpointManagerGate = new();
    private static CheckpointManager? s_foundryWorkflowCheckpointManager;

    /// <summary>
    /// Caches the redirected copy of each agent. Rebuilding it per request would restart the
    /// agent's protocol validation and throw away the session identifiers it tracks, so the copy
    /// has to live as long as the agent it was made from.
    /// </summary>
    private static readonly ConditionalWeakTable<AIAgent, AIAgent> s_workflowCheckpointingAgents = new();

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
