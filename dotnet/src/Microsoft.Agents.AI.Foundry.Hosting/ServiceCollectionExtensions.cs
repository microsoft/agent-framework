// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ClientModel.Primitives;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Runtime.CompilerServices;
using Azure.AI.AgentServer.Core.Tasks;
using Azure.AI.AgentServer.Responses;
using Azure.Core;
using Azure.Identity;
using Microsoft.Agents.AI.Workflows;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
using Microsoft.Extensions.Diagnostics.HealthChecks;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Foundry.Hosting;

/// <summary>
/// Extension methods for registering agent-framework agents as Foundry Hosted Agents
/// using the Azure AI Responses Server SDK.
/// </summary>
public static class ServiceCollectionExtensions
{
    internal const string ResponsesServerSettingsSectionName = "ResponsesServer";

    /// <summary>
    /// Registers the Azure AI Responses Server SDK and the Agent Framework response handler
    /// as the <see cref="ResponseHandler"/>. Agents are resolved from keyed DI services
    /// using the <c>agent.name</c> or <c>metadata["entity_id"]</c> from incoming requests.
    /// </summary>
    /// <remarks>
    /// <para>
    /// This overload is for local or non-hosted scenarios. Foundry hosted applications must call
    /// <see cref="HostApplicationBuilderExtensions.AddFoundryResponses(IHostApplicationBuilder, FoundryResponsesServerOptions)"/>
    /// so AgentServer can bind response and task storage from the host configuration.
    /// </para>
    /// <para>
    /// A non-hosted production platform owns caller authentication. It must remove any
    /// client-supplied <c>x-agent-user-id</c> header before injecting a verified identity.
    /// This package treats <c>ResponseContext.PlatformContext.UserIdKey</c> as trusted platform
    /// context; it does not authenticate that value. Directly exposing the endpoint while accepting
    /// a caller-provided identity for session isolation is unsupported.
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
    /// <param name="options">
    /// Optional <see cref="FoundryResponsesServerOptions"/>, for example to allow the
    /// agent's own service to store the responses it produces, or to opt in to durable long-running
    /// (resilient) background responses via <see cref="ResponsesServerOptions.ResilientBackground"/>.
    /// </param>
    /// <returns>The service collection for chaining.</returns>
    public static IServiceCollection AddFoundryResponses(this IServiceCollection services, FoundryResponsesServerOptions? options = null)
    {
        _ = Throw.IfNull(services);
        FoundryResponsesServerOptions configuredOptions = CopyFoundryResponsesServerOptions(options);
        bool serverAdded = AddResponsesServerOnce(
            services,
            host: null,
            configuredOptions,
            options is not null);
        services.AddHealthChecks();
        ConfigureFoundryListenPort(services);
        ConfigureFoundryResponsesServerOptions(
            services,
            configuredOptions,
            includeServerOptions: serverAdded,
            applyOptions: serverAdded || options is not null);
        services.TryAddSingleton<AgentSessionStore>(_ => CreateDefaultAgentSessionStore());
        RegisterResponseHandler(services);
        MarkFeatureUsed();
        return services;
    }

    /// <summary>
    /// Registers the Azure AI Responses Server SDK and a specific <see cref="AIAgent"/>
    /// as the handler for all incoming requests, regardless of the <c>agent.name</c> in the request.
    /// </summary>
    /// <remarks>
    /// <para>
    /// This overload is for local or non-hosted scenarios. Foundry hosted applications must use
    /// the <see cref="IHostApplicationBuilder"/> overload. When used locally, the provided agent is
    /// registered as both a keyed service and the default <see cref="AIAgent"/>.
    /// </para>
    /// <para>
    /// A non-hosted production platform owns caller authentication. It must remove any
    /// client-supplied <c>x-agent-user-id</c> header before injecting a verified identity.
    /// This package treats <c>ResponseContext.PlatformContext.UserIdKey</c> as trusted platform
    /// context; it does not authenticate that value. Directly exposing the endpoint while accepting
    /// a caller-provided identity for session isolation is unsupported.
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
    /// <param name="agentSessionStore">The agent session store to use for managing agent sessions server-side. If null, the default store uses the AgentServer SDK's local state-store fallback.</param>
    /// <param name="options">
    /// Optional <see cref="FoundryResponsesServerOptions"/>, for example to allow the
    /// agent's own service to store the responses it produces, or to opt in to durable long-running
    /// (resilient) background responses via <see cref="ResponsesServerOptions.ResilientBackground"/>.
    /// </param>
    /// <returns>The service collection for chaining.</returns>
    public static IServiceCollection AddFoundryResponses(
        this IServiceCollection services,
        AIAgent agent,
        AgentSessionStore? agentSessionStore = null,
        FoundryResponsesServerOptions? options = null)
    {
        _ = Throw.IfNull(services);
        _ = Throw.IfNull(agent);

        FoundryResponsesServerOptions configuredOptions = CopyFoundryResponsesServerOptions(options);
        bool serverAdded = AddResponsesServerOnce(
            services,
            host: null,
            configuredOptions,
            options is not null);
        services.AddHealthChecks();
        ConfigureFoundryListenPort(services);
        ConfigureFoundryResponsesServerOptions(
            services,
            configuredOptions,
            includeServerOptions: serverAdded,
            applyOptions: serverAdded || options is not null);
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

        RegisterResponseHandler(services);
        MarkFeatureUsed();
        return services;
    }

    /// <summary>
    /// Applies the caller's <see cref="FoundryResponsesServerOptions"/> and registers the readiness checks
    /// that report a misconfigured agent: one having its own service store the responses it produces,
    /// and a workflow agent writing its checkpoints somewhere hosting does not manage.
    /// </summary>
    /// <remarks>
    /// The checks are registered on the same <c>/readiness</c> pipeline that
    /// <see cref="EndpointRouteBuilderExtensions.MapFoundryResponses"/>
    /// maps, so such a container never takes traffic.
    /// <c>AddCheck</c> does not dedupe by name, so a repeated registration is guarded here.
    /// Resilience flags on <see cref="FoundryResponsesServerOptions"/> are forwarded to
    /// <see cref="ResponsesServerOptions"/> so the AgentServer SDK enables recovery for the same host.
    /// </remarks>
    internal static FoundryResponsesServerOptions CopyFoundryResponsesServerOptions(FoundryResponsesServerOptions? source)
    {
        if (source is null)
        {
            return new();
        }

        return new FoundryResponsesServerOptions
        {
            InferenceStoredOutputAllowed = source.InferenceStoredOutputAllowed,
            OAuthConsentInterruptedToolResult = source.OAuthConsentInterruptedToolResult,
            ExcludeReasoningEncryptedContent = source.ExcludeReasoningEncryptedContent,
            DefaultModel = source.DefaultModel,
            DefaultFetchHistoryCount = source.DefaultFetchHistoryCount,
            ResilientBackground = source.ResilientBackground,
            SteerableConversations = source.SteerableConversations,
            ResponseAcceptor = source.ResponseAcceptor,
        };
    }

    internal static void RegisterResponseHandler(IServiceCollection services)
    {
        services.TryAddSingleton<ResponseHandler>(serviceProvider =>
            new AgentFrameworkResponseHandler(
                serviceProvider,
                serviceProvider.GetRequiredService<ILogger<AgentFrameworkResponseHandler>>(),
                serviceProvider.GetRequiredService<IOptions<FoundryResponsesServerOptions>>().Value,
                serviceProvider.GetService<FoundryToolboxService>()));
    }

    internal static void ConfigureFoundryResponsesServerOptions(
        IServiceCollection services,
        FoundryResponsesServerOptions configuredOptions,
        bool includeServerOptions,
        bool applyOptions)
    {
        if (applyOptions)
        {
            services.Configure<FoundryResponsesServerOptions>(options =>
            {
                options.InferenceStoredOutputAllowed = configuredOptions.InferenceStoredOutputAllowed;
                options.OAuthConsentInterruptedToolResult = configuredOptions.OAuthConsentInterruptedToolResult;
                options.ExcludeReasoningEncryptedContent = configuredOptions.ExcludeReasoningEncryptedContent;
                if (includeServerOptions)
                {
                    options.DefaultModel = configuredOptions.DefaultModel;
                    options.DefaultFetchHistoryCount = configuredOptions.DefaultFetchHistoryCount;
                    options.ResilientBackground = configuredOptions.ResilientBackground;
                    options.SteerableConversations = configuredOptions.SteerableConversations;
                    options.ResponseAcceptor = configuredOptions.ResponseAcceptor;
                }
            });
        }

        AddReadinessCheckOnce(
            services,
            "foundry-stored-output",
            sp => ActivatorUtilities.CreateInstance<HostedStoredOutputHealthCheck>(
                sp,
                sp.GetRequiredService<IOptions<FoundryResponsesServerOptions>>().Value));
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
    /// Registers the Foundry Toolbox service, which opens the configured Foundry toolboxes through the
    /// Toolboxes MCP proxy for each response and provides their MCP tools to the registered response handler.
    /// </summary>
    /// <remarks>
    /// <para>
    /// Each string in <paramref name="toolboxNames"/> is a toolbox name registered in the Foundry
    /// project. The proxy URL per toolbox is constructed as:
    /// <c>{FOUNDRY_PROJECT_ENDPOINT}/toolboxes/{toolboxName}/mcp?api-version=v1</c>
    /// </para>
    /// <para>
    /// The endpoint can also come from a configured override or the
    /// <c>AZURE_AI_PROJECT_ENDPOINT</c> local-development fallback. If no endpoint is resolved,
    /// startup completes with toolbox support disabled.
    /// A toolbox name that would not resolve to a single path segment of the proxy URL fails startup.
    /// </para>
    /// <para>
    /// Startup opens no connection. Each response opens its own MCP session per toolbox under its platform
    /// call id, discovers the tools available to its caller, and ends every session when it completes. A
    /// toolbox that needs the caller's OAuth consent stops the turn with an <c>oauth_consent_request</c>; a
    /// toolbox that cannot be opened is skipped for that response.
    /// </para>
    /// <para>
    /// This method does not register a toolbox health check. Toolbox connectivity is evaluated
    /// when each response opens its connections, not by readiness probes.
    /// </para>
    /// <para>
    /// Example:
    /// <code>
    /// builder.Services.AddFoundryToolboxService(credential, "my-toolbox", "another-toolbox");
    /// </code>
    /// </para>
    /// </remarks>
    /// <param name="services">The service collection.</param>
    /// <param name="credential">The <see cref="TokenCredential"/> used to authenticate with the Foundry Toolboxes MCP proxy.</param>
    /// <param name="toolboxNames">Names of the Foundry toolboxes to connect to.</param>
    /// <returns>The service collection for chaining.</returns>
    public static IServiceCollection AddFoundryToolboxService(
        this IServiceCollection services,
        TokenCredential credential,
        params string[] toolboxNames)
        => services.AddFoundryToolboxService(credential, options: null, toolboxNames);

    /// <summary>
    /// Registers the Foundry Toolbox service with optional behavior configuration.
    /// </summary>
    /// <remarks>
    /// Toolbox startup and per-response connection behavior follow
    /// <see cref="AddFoundryToolboxService(IServiceCollection, TokenCredential, string[])"/>.
    /// </remarks>
    /// <param name="services">The service collection.</param>
    /// <param name="credential">The <see cref="TokenCredential"/> used to authenticate with the Foundry Toolboxes MCP proxy.</param>
    /// <param name="options">
    /// Optional <see cref="FoundryToolboxServiceOptions"/>, such as
    /// <see cref="FoundryToolboxServiceOptions.TokenScope"/>, or
    /// <see cref="FoundryToolboxServiceOptions.AllowedOAuthConsentOrigins"/>.
    /// </param>
    /// <param name="toolboxNames">Names of the Foundry toolboxes to open for each response.</param>
    /// <returns>The service collection for chaining.</returns>
    public static IServiceCollection AddFoundryToolboxService(
        this IServiceCollection services,
        TokenCredential credential,
        FoundryToolboxServiceOptions? options,
        params string[] toolboxNames)
    {
        _ = Throw.IfNull(services);
        _ = Throw.IfNull(credential);

        if (services.Any(d => d.ServiceType == typeof(FoundryToolboxService)))
        {
            throw new InvalidOperationException(
                $"{nameof(FoundryToolboxService)} is already registered. " +
                $"Call {nameof(AddFoundryToolboxService)} only once per service collection.");
        }

        FoundryToolboxServiceOptions configuredOptions = CopyFoundryToolboxServiceOptions(options, toolboxNames);
        // Register FoundryToolboxService as a singleton, injecting the caller-provided credential
        // directly rather than resolving TokenCredential from DI.
        services.AddSingleton(sp => new FoundryToolboxService(
            configuredOptions,
            credential: credential,
            sp.GetService<ILogger<FoundryToolboxService>>()));
        services.AddHostedService(sp => sp.GetRequiredService<FoundryToolboxService>());

        MarkFeatureUsed(FeatureIndex.FoundryToolbox);
        return services;
    }

    private static FoundryToolboxServiceOptions CopyFoundryToolboxServiceOptions(
        FoundryToolboxServiceOptions? source,
        string[] toolboxNames)
    {
        var copy = new FoundryToolboxServiceOptions();
        if (source is not null)
        {
            copy.TokenScope = source.TokenScope;
            copy.AllowedOAuthConsentOrigins = source.AllowedOAuthConsentOrigins is null
                ? null
                : new HashSet<Uri>(source.AllowedOAuthConsentOrigins);
        }

        foreach (string name in toolboxNames)
        {
            if (!string.IsNullOrWhiteSpace(name))
            {
                copy.ToolboxNames.Add(name);
            }
        }

        return copy;
    }

    internal static void MarkFeatureUsed(FeatureIndex feature = FeatureIndex.FoundryHosting)
    {
#pragma warning disable MAAI001
        FeatureUsage.MarkUsed((int)feature);
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
    internal static bool AddResponsesServerOnce(
        IServiceCollection services,
        IHostApplicationBuilder? host,
        FoundryResponsesServerOptions configuredOptions,
        bool hasConfigureCallback)
    {
        FoundryResponsesServerMarker? marker = services
            .LastOrDefault(static descriptor =>
                descriptor.ServiceType == typeof(FoundryResponsesServerMarker))
            ?.ImplementationInstance as FoundryResponsesServerMarker;
        if (marker is not null)
        {
            if (hasConfigureCallback
                && ((!marker.ResilientBackground && configuredOptions.ResilientBackground)
                    || (!marker.SteerableConversations && configuredOptions.SteerableConversations)))
            {
                throw new InvalidOperationException(
                    "ResilientBackground and SteerableConversations must be configured on the first AddFoundryResponses call because AgentServer registers its durable tasks during that call.");
            }

            return false;
        }

        bool resilientBackground = configuredOptions.ResilientBackground;
        bool steerableConversations = configuredOptions.SteerableConversations;
        services.AddSingleton(new FoundryResponsesServerMarker(
            resilientBackground,
            steerableConversations));
        if (host is not null)
        {
#pragma warning disable SCME0002
            host.AddResponsesServer(
                ResponsesServerSettingsSectionName,
                settings =>
                {
                    if (hasConfigureCallback)
                    {
                        settings.DefaultModel = configuredOptions.DefaultModel;
                        settings.DefaultFetchHistoryCount = configuredOptions.DefaultFetchHistoryCount;
                        settings.ResilientBackground = configuredOptions.ResilientBackground;
                        settings.SteerableConversations = configuredOptions.SteerableConversations;
                        settings.ResponseAcceptor = configuredOptions.ResponseAcceptor;
                    }
                });
#pragma warning restore SCME0002
        }
        else
        {
            services.AddResponsesServer(options =>
            {
                if (hasConfigureCallback)
                {
                    options.DefaultModel = configuredOptions.DefaultModel;
                    options.DefaultFetchHistoryCount = configuredOptions.DefaultFetchHistoryCount;
                    options.ResilientBackground = configuredOptions.ResilientBackground;
                    options.SteerableConversations = configuredOptions.SteerableConversations;
                    options.ResponseAcceptor = configuredOptions.ResponseAcceptor;
                }
            });
        }

        if (steerableConversations)
        {
            services.SetResilientTasksEnabled();
        }

        return true;
    }

    /// <summary>
    /// Creates the <see cref="AgentSessionStore"/> used when the caller did not supply one.
    /// </summary>
    /// <remarks>
    /// The AgentServer SDK selects the backend. Inside a Foundry container it uses the platform's
    /// durable state store, which survives replacement and is readable by every instance. Anywhere
    /// else it uses the SDK's local state-store fallback under <c>~/.agentserver/state_stores</c>.
    /// </remarks>
    internal static FoundryAgentSessionStore CreateDefaultAgentSessionStore() =>
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
    private sealed class FoundryResponsesServerMarker(
        bool resilientBackground,
        bool steerableConversations)
    {
        public bool ResilientBackground { get; } = resilientBackground;

        public bool SteerableConversations { get; } = steerableConversations;
    }

    /// <summary>
    /// Configures the URL used by a plain <c>WebApplication.CreateBuilder</c> host (Tier 3) so
    /// it listens on the port the Foundry hosted runtime probes and routes to.
    /// </summary>
    /// <remarks>
    /// <para>
    /// The URL is configured only when configuration reports a Foundry container through
    /// <see cref="FoundryHostingEnvironmentKey"/>. Outside Foundry the host keeps its configured
    /// addresses.
    /// </para>
    /// <para>
    /// Both values come from <see cref="IConfiguration"/> rather than from
    /// <see cref="FoundryEnvironment"/>, which caches every value in a static constructor. Reading
    /// through configuration keeps the decision observable when the host is built, honours the
    /// host's configuration sources, and lets tests supply values without mutating the process
    /// environment.
    /// </para>
    /// <para>
    /// Inside a Foundry container this replaces the URL inherited from the .NET base image. When
    /// <c>AgentHostBuilder</c> is used, its code-configured Kestrel listener takes precedence over
    /// this URL, so both hosting paths resolve to one listener without identifying the builder
    /// from its service registrations.
    /// </para>
    /// <para>
    /// The startup filter is resolved before ASP.NET reads the configured URLs and starts its
    /// server. Registration is idempotent across repeated <c>AddFoundryResponses</c> calls.
    /// </para>
    /// </remarks>
    internal static void ConfigureFoundryListenPort(IServiceCollection services)
    {
        if (services.Any(static d => d.ServiceType == typeof(FoundryListenPortMarker)))
        {
            return;
        }

        services.AddSingleton<FoundryListenPortMarker>();
        services.AddSingleton<IStartupFilter, FoundryListenPortStartupFilter>();
    }

    private sealed class FoundryListenPortStartupFilter : IStartupFilter
    {
        public FoundryListenPortStartupFilter(IConfiguration configuration)
        {
            // GenericWebHostService resolves startup filters before it reads this URL and starts
            // the server, while a code-configured AgentHost listener takes precedence over it.
            if (!string.IsNullOrEmpty(configuration[FoundryHostingEnvironmentKey]))
            {
                configuration[WebHostDefaults.ServerUrlsKey] =
                    $"http://+:{ResolveListenPort(configuration)}";
            }
        }

        public Action<IApplicationBuilder> Configure(Action<IApplicationBuilder> next) => next;
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
    /// MEAI 10.9.0 <see cref="OpenAIRequestPolicies"/> hook so every outgoing OpenAI Responses
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
