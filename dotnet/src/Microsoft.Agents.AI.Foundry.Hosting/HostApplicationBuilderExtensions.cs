// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
using Microsoft.Extensions.Hosting;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Foundry.Hosting;

/// <summary>
/// Extension methods for registering Foundry Responses hosting on an <see cref="IHostApplicationBuilder"/>.
/// </summary>
public static class HostApplicationBuilderExtensions
{
    /// <summary>
    /// Registers the Azure AI Responses Server SDK and the Agent Framework response handler
    /// on a host application builder.
    /// </summary>
    /// <remarks>
    /// Use this overload for applications that can access their host builder. In a Foundry hosted
    /// environment it binds the response-storage and resilient-task-storage identity and endpoint
    /// from the same <c>ResponsesServer</c> configuration section, as required by AgentServer.
    /// Keyed agent registrations may use any DI lifetime. Each response run resolves its agent and
    /// session store from a DI scope that is disposed when the run's event stream ends, so scoped and
    /// transient agents are created per run, including background runs that outlive the HTTP request.
    /// <code>
    /// builder.Services.AddKeyedSingleton&lt;AIAgent&gt;("my-agent", myAgent);
    /// builder.AddFoundryResponses();
    /// </code>
    /// </remarks>
    /// <param name="host">The host application builder.</param>
    /// <param name="options">Optional hosting behavior. Required inputs belong on the extension method parameters.</param>
    /// <returns>The host application builder for chaining.</returns>
    public static IHostApplicationBuilder AddFoundryResponses(
        this IHostApplicationBuilder host,
        FoundryResponsesServerOptions? options = null)
    {
        _ = Throw.IfNull(host);
        FoundryResponsesServerOptions configuredOptions = ResolveFoundryResponsesServerOptions(host, options);
        bool serverAdded = ServiceCollectionExtensions.AddResponsesServerOnce(
            host.Services,
            host,
            configuredOptions,
            options is not null);
        host.Services.AddHealthChecks();
        ServiceCollectionExtensions.ConfigureFoundryListenPort(host.Services);
        ServiceCollectionExtensions.ConfigureFoundryResponsesServerOptions(
            host.Services,
            configuredOptions,
            includeServerOptions: serverAdded,
            applyOptions: serverAdded || options is not null);
        host.Services.TryAddSingleton<AgentSessionStore>(_ => ServiceCollectionExtensions.CreateDefaultAgentSessionStore());
        ServiceCollectionExtensions.RegisterResponseHandler(host.Services);
        ServiceCollectionExtensions.MarkFeatureUsed();
        return host;
    }

    /// <summary>
    /// Registers the Azure AI Responses Server SDK and a specific <see cref="AIAgent"/> on a host
    /// application builder.
    /// </summary>
    /// <remarks>
    /// <code>
    /// builder.AddFoundryResponses(myAgent);
    /// </code>
    /// </remarks>
    /// <param name="host">The host application builder.</param>
    /// <param name="agent">The agent instance to register.</param>
    /// <param name="agentSessionStore">The agent session store to use, or <see langword="null"/> for the default.</param>
    /// <param name="options">Optional hosting behavior. Required inputs belong on the extension method parameters.</param>
    /// <returns>The host application builder for chaining.</returns>
    public static IHostApplicationBuilder AddFoundryResponses(
        this IHostApplicationBuilder host,
        AIAgent agent,
        AgentSessionStore? agentSessionStore = null,
        FoundryResponsesServerOptions? options = null)
    {
        _ = Throw.IfNull(host);
        _ = Throw.IfNull(agent);

        FoundryResponsesServerOptions configuredOptions = ResolveFoundryResponsesServerOptions(host, options);
        bool serverAdded = ServiceCollectionExtensions.AddResponsesServerOnce(
            host.Services,
            host,
            configuredOptions,
            options is not null);
        host.Services.AddHealthChecks();
        ServiceCollectionExtensions.ConfigureFoundryListenPort(host.Services);
        ServiceCollectionExtensions.ConfigureFoundryResponsesServerOptions(
            host.Services,
            configuredOptions,
            includeServerOptions: serverAdded,
            applyOptions: serverAdded || options is not null);
        agentSessionStore ??= ServiceCollectionExtensions.CreateDefaultAgentSessionStore();

        if (!string.IsNullOrWhiteSpace(agent.Name))
        {
            host.Services.TryAddKeyedSingleton(agent.Name, agent);
            host.Services.TryAddKeyedSingleton(agent.Name, agentSessionStore);
        }

        host.Services.TryAddSingleton(agent);
        host.Services.TryAddSingleton(agentSessionStore);

        ServiceCollectionExtensions.RegisterResponseHandler(host.Services);
        ServiceCollectionExtensions.MarkFeatureUsed();
        return host;
    }

    /// <summary>
    /// Registers the Azure AI Responses Server SDK and an <see cref="AIAgent"/> created by a factory
    /// with the specified DI lifetime on a host application builder.
    /// </summary>
    /// <remarks>
    /// <para>
    /// Use this overload when the agent or its session store depends on services that are not
    /// singletons, for example a database context, or when they should not live for the whole process.
    /// The agent and its session store are registered under <paramref name="agentName"/> and as the
    /// default <see cref="AIAgent"/> and <see cref="AgentSessionStore"/>, so requests without an agent
    /// name also reach them.
    /// </para>
    /// <para>
    /// Every response run (streaming, non-streaming, background, or a run resumed after a restart) gets
    /// its own DI scope, created when the run starts and disposed when its event stream ends. That is
    /// later than the end of the HTTP request for a background run. The lifetime applies to the agent
    /// and, when <paramref name="agentSessionStoreFactory"/> is supplied, to the session store:
    /// <list type="bullet">
    /// <item><description><see cref="ServiceLifetime.Singleton"/>: one instance for the process, disposed at shutdown.</description></item>
    /// <item><description><see cref="ServiceLifetime.Scoped"/>: one instance per response run, disposed when the run ends.</description></item>
    /// <item><description><see cref="ServiceLifetime.Transient"/>: a new instance on every lookup, disposed when the run ends.</description></item>
    /// </list>
    /// Conversation state is not kept on the agent or store object: each turn loads the saved session
    /// from the store's backing storage. Sessions are stored under <paramref name="agentName"/>, the same
    /// location <c>AddFoundryResponses(agent)</c> uses for an agent with that name, so switching between
    /// the two overloads or between lifetimes keeps existing sessions readable.
    /// </para>
    /// <code>
    /// builder.AddFoundryResponses(
    ///     "my-agent",
    ///     sp => new MyAgent(sp.GetRequiredService&lt;MyDbContext&gt;()),
    ///     ServiceLifetime.Scoped,
    ///     sp => new MySessionStore(sp.GetRequiredService&lt;MyDbContext&gt;()));
    /// </code>
    /// </remarks>
    /// <param name="host">The host application builder.</param>
    /// <param name="agentName">The name the agent is registered under and the name requests use to select it.</param>
    /// <param name="agentFactory">Creates the agent from the service provider of the current DI scope.</param>
    /// <param name="lifetime">
    /// The DI lifetime of the agent and of the session store created by <paramref name="agentSessionStoreFactory"/>.
    /// Defaults to <see cref="ServiceLifetime.Singleton"/>.
    /// </param>
    /// <param name="agentSessionStoreFactory">
    /// Creates the agent session store from the service provider of the current DI scope, with the same
    /// <paramref name="lifetime"/> as the agent. If null, the default singleton store is used. When the
    /// factory returns an object created elsewhere with a scoped or transient lifetime, the DI container
    /// still disposes it at the end of each response run if it is disposable.
    /// </param>
    /// <param name="options">Optional hosting behavior. Required inputs belong on the extension method parameters.</param>
    /// <returns>The host application builder for chaining.</returns>
    public static IHostApplicationBuilder AddFoundryResponses(
        this IHostApplicationBuilder host,
        string agentName,
        Func<IServiceProvider, AIAgent> agentFactory,
        ServiceLifetime lifetime = ServiceLifetime.Singleton,
        Func<IServiceProvider, AgentSessionStore>? agentSessionStoreFactory = null,
        FoundryResponsesServerOptions? options = null)
    {
        _ = Throw.IfNull(host);
        ServiceCollectionExtensions.RegisterAgentFactory(host.Services, agentName, agentFactory, lifetime, agentSessionStoreFactory);
        return host.AddFoundryResponses(options);
    }

    private static FoundryResponsesServerOptions ResolveFoundryResponsesServerOptions(
        IHostApplicationBuilder host,
        FoundryResponsesServerOptions? suppliedOptions)
    {
        if (suppliedOptions is not null)
        {
            // AgentServer applies code configuration after host configuration. A supplied options
            // object follows the same contract, including its inherited AgentServer defaults.
            return ServiceCollectionExtensions.CopyFoundryResponsesServerOptions(suppliedOptions);
        }

        FoundryResponsesServerOptions options = new();
        IConfigurationSection section =
            host.Configuration.GetSection(ServiceCollectionExtensions.ResponsesServerSettingsSectionName);
        options.DefaultModel = section[nameof(FoundryResponsesServerOptions.DefaultModel)];
        if (int.TryParse(
            section[nameof(FoundryResponsesServerOptions.DefaultFetchHistoryCount)],
            out int defaultFetchHistoryCount))
        {
            options.DefaultFetchHistoryCount = defaultFetchHistoryCount;
        }

        if (bool.TryParse(section[nameof(FoundryResponsesServerOptions.ResilientBackground)], out bool resilientBackground))
        {
            options.ResilientBackground = resilientBackground;
        }

        if (bool.TryParse(section[nameof(FoundryResponsesServerOptions.SteerableConversations)], out bool steerableConversations))
        {
            options.SteerableConversations = steerableConversations;
        }

        return options;
    }
}
