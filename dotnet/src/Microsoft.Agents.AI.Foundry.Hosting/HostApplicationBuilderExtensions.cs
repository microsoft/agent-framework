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
    /// <param name="agentSessionStore">
    /// The session store for this agent. It is registered under the agent's name and is not used by other
    /// agents. If null, the agent uses the store registered for all agents with
    /// <see cref="AddFoundryAgentSessionStore(IHostApplicationBuilder, AgentSessionStore, string?)"/>, or the default store.
    /// </param>
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
        ServiceCollectionExtensions.RegisterAgentInstance(host.Services, agent, agentSessionStore);
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
    /// Use this overload when the agent depends on services that are not singletons, for example a
    /// database context, or when it should not live for the whole process. The agent is registered only
    /// under <paramref name="agentName"/>. When no default agent is registered yet, requests without a
    /// matching agent name are also routed to this agent. An existing registration under
    /// <paramref name="agentName"/> is kept, the same as for <c>AddFoundryResponses(agent)</c>.
    /// </para>
    /// <para>
    /// Every response run (streaming, non-streaming, background, or a run resumed after a restart) gets
    /// its own DI scope, created when the run starts and disposed when its event stream ends. That is
    /// later than the end of the HTTP request for a background run. The lifetime applies to the agent:
    /// <list type="bullet">
    /// <item><description><see cref="ServiceLifetime.Singleton"/>: one instance for the process, disposed at shutdown.</description></item>
    /// <item><description><see cref="ServiceLifetime.Scoped"/>: one instance per response run, disposed when the run ends.</description></item>
    /// <item><description><see cref="ServiceLifetime.Transient"/>: a new instance on every lookup, disposed when the run ends.</description></item>
    /// </list>
    /// This scope is not the ASP.NET Core request scope, so scoped services that middleware fills in for an
    /// HTTP request are new, empty instances here. Do not derive the caller's identity from such services in
    /// the factory; the per-request user identity is supplied by the platform and applied by the response
    /// handler when it loads and saves sessions.
    /// </para>
    /// <para>
    /// The session store is registered separately with
    /// <see cref="AddFoundryAgentSessionStore(IHostApplicationBuilder, Func{IServiceProvider, AgentSessionStore}, ServiceLifetime, string?)"/>,
    /// with its own lifetime. Without such a registration the agent uses the default store. Sessions are
    /// stored in the same location <c>AddFoundryResponses(agent)</c> uses for an agent with that name
    /// registered in the same order, whatever the lifetime, so switching between the two overloads or
    /// between lifetimes keeps existing sessions readable.
    /// </para>
    /// <code>
    /// builder.AddFoundryResponses(
    ///     "my-agent",
    ///     sp => new MyAgent(sp.GetRequiredService&lt;MyDbContext&gt;()),
    ///     ServiceLifetime.Scoped);
    /// </code>
    /// </remarks>
    /// <param name="host">The host application builder.</param>
    /// <param name="agentName">The name the agent is registered under and the name requests use to select it.</param>
    /// <param name="agentFactory">Creates the agent from the service provider of the current DI scope.</param>
    /// <param name="lifetime">The DI lifetime of the agent. Defaults to <see cref="ServiceLifetime.Singleton"/>.</param>
    /// <param name="options">Optional hosting behavior. Required inputs belong on the extension method parameters.</param>
    /// <returns>The host application builder for chaining.</returns>
    public static IHostApplicationBuilder AddFoundryResponses(
        this IHostApplicationBuilder host,
        string agentName,
        Func<IServiceProvider, AIAgent> agentFactory,
        ServiceLifetime lifetime = ServiceLifetime.Singleton,
        FoundryResponsesServerOptions? options = null)
    {
        _ = Throw.IfNull(host);
        ServiceCollectionExtensions.RegisterAgentFactory(host.Services, agentName, agentFactory, lifetime);
        return host.AddFoundryResponses(options);
    }

    /// <summary>
    /// Registers the <see cref="AgentSessionStore"/> that Foundry Responses hosting uses for one agent, or for
    /// every agent that has no store of its own, on a host application builder.
    /// </summary>
    /// <remarks>
    /// The response handler uses the store registered under the agent's name, then the store registered for
    /// all agents, then the default store. The DI container never disposes <paramref name="agentSessionStore"/>.
    /// Calling this method again for the same <paramref name="agentName"/>, or again for all agents, replaces
    /// the earlier store, in whatever order it is called relative to <c>AddFoundryResponses</c>.
    /// <code>
    /// builder.AddFoundryAgentSessionStore(mySessionStore);
    /// </code>
    /// </remarks>
    /// <param name="host">The host application builder.</param>
    /// <param name="agentSessionStore">The session store to use.</param>
    /// <param name="agentName">
    /// The name of the agent the store is for, or <see langword="null"/> to use it for every agent that has no
    /// store of its own.
    /// </param>
    /// <returns>The host application builder for chaining.</returns>
    public static IHostApplicationBuilder AddFoundryAgentSessionStore(
        this IHostApplicationBuilder host,
        AgentSessionStore agentSessionStore,
        string? agentName = null)
    {
        _ = Throw.IfNull(host);
        host.Services.AddFoundryAgentSessionStore(agentSessionStore, agentName);
        return host;
    }

    /// <summary>
    /// Registers a factory for the <see cref="AgentSessionStore"/> that Foundry Responses hosting uses for one
    /// agent, or for every agent that has no store of its own, with the specified DI lifetime on a host
    /// application builder.
    /// </summary>
    /// <remarks>
    /// The response handler looks the store up once per response run, from the DI scope of that run. The
    /// store's lifetime is independent of the agent's lifetime. Calling this method again for the same
    /// <paramref name="agentName"/>, or again for all agents, replaces the earlier store, in whatever order it
    /// is called relative to <c>AddFoundryResponses</c>.
    /// <code>
    /// builder.AddFoundryAgentSessionStore(
    ///     sp => new MySessionStore(sp.GetRequiredService&lt;MyDbContext&gt;()),
    ///     ServiceLifetime.Scoped);
    /// </code>
    /// </remarks>
    /// <param name="host">The host application builder.</param>
    /// <param name="agentSessionStoreFactory">Creates the session store from the service provider of the current DI scope.</param>
    /// <param name="lifetime">The DI lifetime of the session store. Defaults to <see cref="ServiceLifetime.Singleton"/>.</param>
    /// <param name="agentName">
    /// The name of the agent the store is for, or <see langword="null"/> to use it for every agent that has no
    /// store of its own.
    /// </param>
    /// <returns>The host application builder for chaining.</returns>
    public static IHostApplicationBuilder AddFoundryAgentSessionStore(
        this IHostApplicationBuilder host,
        Func<IServiceProvider, AgentSessionStore> agentSessionStoreFactory,
        ServiceLifetime lifetime = ServiceLifetime.Singleton,
        string? agentName = null)
    {
        _ = Throw.IfNull(host);
        host.Services.AddFoundryAgentSessionStore(agentSessionStoreFactory, lifetime, agentName);
        return host;
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
