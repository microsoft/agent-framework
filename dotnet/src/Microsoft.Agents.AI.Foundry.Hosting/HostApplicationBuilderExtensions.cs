// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Foundry.Hosting;

/// <summary>
/// Extension methods for registering Foundry Responses hosting on an <see cref="IHostApplicationBuilder"/>.
/// </summary>
public static class HostApplicationBuilderExtensions
{
    /// <summary>
    /// Registers the Azure AI Responses Server SDK and the Agent Framework response handler that answers
    /// every request with <paramref name="agent"/>, on a host application builder.
    /// </summary>
    /// <remarks>
    /// <para>
    /// Use this overload for applications that can access their host builder. In a Foundry hosted
    /// environment it binds the response-storage and resilient-task-storage identity and endpoint
    /// from the same <c>ResponsesServer</c> configuration section, as required by AgentServer.
    /// </para>
    /// <para>
    /// Foundry publishes a dedicated endpoint for each hosted agent, so a container serves exactly one agent.
    /// Every request is answered by <paramref name="agent"/>: the request's <c>agent.name</c>, <c>model</c>, and
    /// <c>metadata["entity_id"]</c> do not select it, and no <see cref="AIAgent"/> registered in dependency
    /// injection is used. Call one <c>AddFoundryResponses</c> overload once per host; a second call throws.
    /// The agent is reused for every request and is never disposed by hosting, because the caller created it.
    /// </para>
    /// <para>
    /// A store passed in <paramref name="agentSessionStore"/> is registered the same way
    /// <see cref="AddFoundryAgentSessionStore(IHostApplicationBuilder, AgentSessionStore)"/> registers it, and the
    /// store registered last is used. Without one, the agent uses a store registered earlier, or otherwise the
    /// default store. Each store keeps its own sessions, so changing the store means sessions saved in the
    /// previous store are no longer found.
    /// </para>
    /// <code>
    /// builder.AddFoundryResponses(myAgent);
    /// </code>
    /// </remarks>
    /// <param name="host">The host application builder.</param>
    /// <param name="agent">The agent that answers every request.</param>
    /// <param name="agentSessionStore">
    /// The session store for the agent. If null, the agent uses a store registered earlier, or otherwise the
    /// default store.
    /// </param>
    /// <param name="options">Optional hosting behavior. Required inputs belong on the extension method parameters.</param>
    /// <returns>The host application builder for chaining.</returns>
    /// <exception cref="InvalidOperationException"><c>AddFoundryResponses</c> was already called for <paramref name="host"/>.</exception>
    public static IHostApplicationBuilder AddFoundryResponses(
        this IHostApplicationBuilder host,
        AIAgent agent,
        AgentSessionStore? agentSessionStore = null,
        FoundryResponsesServerOptions? options = null)
    {
        _ = Throw.IfNull(host);
        _ = Throw.IfNull(agent);

        ServiceCollectionExtensions.AddFoundryResponsesCore(
            host.Services,
            host,
            ServiceCollectionExtensions.DescribeAgentSource(agent),
            agentSessionStore,
            ResolveFoundryResponsesServerOptions(host, options),
            optionsSupplied: options is not null);
        return host;
    }

    /// <summary>
    /// Registers the Azure AI Responses Server SDK and the Agent Framework response handler that answers
    /// every request with an <see cref="AIAgent"/> created by <paramref name="agentFactory"/>, with the
    /// specified lifetime, on a host application builder.
    /// </summary>
    /// <remarks>
    /// <para>
    /// Use this overload when the agent depends on services that are not singletons, for example a
    /// database context, or when it should not live for the whole process. The agent is never registered in
    /// dependency injection, but <paramref name="agentFactory"/> receives a service provider to resolve the
    /// agent's own dependencies from.
    /// </para>
    /// <para>
    /// Every response run (streaming, non-streaming, background, or a run resumed after a restart) gets
    /// its own DI scope, created when the run starts and disposed when its event stream ends. That is
    /// later than the end of the HTTP request for a background run. The lifetime applies to the agent:
    /// <list type="bullet">
    /// <item><description><see cref="ServiceLifetime.Singleton"/>: created on first use from the root service provider, reused for the process, and disposed at shutdown.</description></item>
    /// <item><description><see cref="ServiceLifetime.Scoped"/>: created from the run's scope once per response run, and disposed when the run ends.</description></item>
    /// <item><description><see cref="ServiceLifetime.Transient"/>: the same as <see cref="ServiceLifetime.Scoped"/>, because hosting is the only caller that gets the agent, once per run.</description></item>
    /// </list>
    /// Hosting disposes what the factory returns according to that lifetime. The run's scope is not the
    /// ASP.NET Core request scope, so scoped services that middleware fills in for an HTTP request are new,
    /// empty instances here. Do not derive the caller's identity from such services in the factory; the
    /// per-request user identity is supplied by the platform and applied by the response handler when it
    /// loads and saves sessions.
    /// </para>
    /// <para>
    /// Hosting adds an <see cref="OpenTelemetryAgent"/> to a singleton agent, unless it already has one, and
    /// disposes that wrapper at shutdown. For a scoped or transient agent, hosting adds and disposes a separate
    /// wrapper for every response after applying Foundry workflow checkpointing. A factory that supplies its own
    /// <see cref="OpenTelemetryAgent"/> must arrange the inner agent's lifetime independently. See
    /// <see cref="FoundryResponsesServerOptions.RequireOpenTelemetryAgent"/>.
    /// </para>
    /// <para>
    /// The session store is registered separately with
    /// <see cref="AddFoundryAgentSessionStore(IHostApplicationBuilder, Func{IServiceProvider, AgentSessionStore}, ServiceLifetime)"/>,
    /// with its own lifetime. Without such a registration the agent uses the default store. Sessions are saved
    /// under the created agent's <see cref="AIAgent.Name"/>, the same location
    /// <see cref="AddFoundryResponses(IHostApplicationBuilder, AIAgent, AgentSessionStore?, FoundryResponsesServerOptions?)"/>
    /// uses, so the factory must give every agent it creates the same name, and switching between the two
    /// overloads or between lifetimes keeps existing sessions readable.
    /// </para>
    /// <code>
    /// builder.AddFoundryResponses(
    ///     sp => new MyAgent(sp.GetRequiredService&lt;MyDbContext&gt;()),
    ///     ServiceLifetime.Scoped);
    /// </code>
    /// </remarks>
    /// <param name="host">The host application builder.</param>
    /// <param name="agentFactory">Creates the agent from the service provider of the root or of the current response run.</param>
    /// <param name="lifetime">How long a created agent is reused. Defaults to <see cref="ServiceLifetime.Singleton"/>.</param>
    /// <param name="options">Optional hosting behavior. Required inputs belong on the extension method parameters.</param>
    /// <returns>The host application builder for chaining.</returns>
    /// <exception cref="InvalidOperationException"><c>AddFoundryResponses</c> was already called for <paramref name="host"/>.</exception>
    public static IHostApplicationBuilder AddFoundryResponses(
        this IHostApplicationBuilder host,
        Func<IServiceProvider, AIAgent> agentFactory,
        ServiceLifetime lifetime = ServiceLifetime.Singleton,
        FoundryResponsesServerOptions? options = null)
    {
        _ = Throw.IfNull(host);

        ServiceCollectionExtensions.AddFoundryResponsesCore(
            host.Services,
            host,
            ServiceCollectionExtensions.DescribeAgentSource(agentFactory, lifetime),
            agentSessionStore: null,
            ResolveFoundryResponsesServerOptions(host, options),
            optionsSupplied: options is not null);
        return host;
    }

    /// <summary>
    /// Registers the <see cref="AgentSessionStore"/> that Foundry Responses hosting uses to load and save the
    /// hosted agent's sessions, on a host application builder.
    /// </summary>
    /// <remarks>
    /// The store registered last is used, as described for
    /// <see cref="ServiceCollectionExtensions.AddFoundryAgentSessionStore(IServiceCollection, AgentSessionStore)"/>.
    /// The DI container never disposes <paramref name="agentSessionStore"/>. Each store keeps its own
    /// sessions, so changing the store means sessions saved in the previous store are no longer found.
    /// <code>
    /// builder.AddFoundryAgentSessionStore(mySessionStore);
    /// </code>
    /// </remarks>
    /// <param name="host">The host application builder.</param>
    /// <param name="agentSessionStore">The session store to use.</param>
    /// <returns>The host application builder for chaining.</returns>
    public static IHostApplicationBuilder AddFoundryAgentSessionStore(
        this IHostApplicationBuilder host,
        AgentSessionStore agentSessionStore)
    {
        _ = Throw.IfNull(host);
        host.Services.AddFoundryAgentSessionStore(agentSessionStore);
        return host;
    }

    /// <summary>
    /// Registers a factory for the <see cref="AgentSessionStore"/> that Foundry Responses hosting uses to load
    /// and save the hosted agent's sessions, with the specified DI lifetime, on a host application builder.
    /// </summary>
    /// <remarks>
    /// The response handler looks the store up once per response run, from the DI scope of that run. The
    /// store's lifetime is independent of the agent's lifetime. The store registered last is used, as
    /// described for
    /// <see cref="ServiceCollectionExtensions.AddFoundryAgentSessionStore(IServiceCollection, Func{IServiceProvider, AgentSessionStore}, ServiceLifetime)"/>.
    /// <code>
    /// builder.AddFoundryAgentSessionStore(
    ///     sp => new MySessionStore(sp.GetRequiredService&lt;MyDbContext&gt;()),
    ///     ServiceLifetime.Scoped);
    /// </code>
    /// </remarks>
    /// <param name="host">The host application builder.</param>
    /// <param name="agentSessionStoreFactory">Creates the session store from the service provider of the current DI scope.</param>
    /// <param name="lifetime">The DI lifetime of the session store. Defaults to <see cref="ServiceLifetime.Singleton"/>.</param>
    /// <returns>The host application builder for chaining.</returns>
    public static IHostApplicationBuilder AddFoundryAgentSessionStore(
        this IHostApplicationBuilder host,
        Func<IServiceProvider, AgentSessionStore> agentSessionStoreFactory,
        ServiceLifetime lifetime = ServiceLifetime.Singleton)
    {
        _ = Throw.IfNull(host);
        host.Services.AddFoundryAgentSessionStore(agentSessionStoreFactory, lifetime);
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
