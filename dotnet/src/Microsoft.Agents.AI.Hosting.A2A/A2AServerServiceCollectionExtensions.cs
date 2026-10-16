// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics.CodeAnalysis;
using A2A;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Hosting;
using Microsoft.Agents.AI.Hosting.A2A;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Extensions.DependencyInjection;

/// <summary>
/// Provides extension methods for registering A2A server instances in the dependency injection container.
/// </summary>
[Experimental(DiagnosticIds.Experiments.AIResponseContinuations)]
public static class A2AServerServiceCollectionExtensions
{
    /// <summary>
    /// Registers an <see cref="A2AServer"/> in the dependency injection container, keyed by the agent name
    /// specified in the <paramref name="agentBuilder"/>. This method only registers the server; to expose it
    /// as an HTTP endpoint, call one of the <c>MapA2AHttpJson</c> or <c>MapA2AJsonRpc</c> endpoint mapping
    /// methods during application startup.
    /// </summary>
    /// <param name="agentBuilder">The agent builder whose name identifies the agent.</param>
    /// <param name="configureOptions">An optional callback to configure <see cref="A2AServerRegistrationOptions"/>.</param>
    /// <returns>The <paramref name="agentBuilder"/> for chaining.</returns>
    /// <remarks>
    /// <para>
    /// Singleton agent registrations are resolved once when the server is created. Scoped and transient registrations
    /// are resolved for each A2A operation as described in
    /// <see cref="AddA2AServer(IServiceCollection, string, Action{A2AServerRegistrationOptions}?)"/>.
    /// </para>
    /// <para>
    /// <strong>Trust model.</strong> The A2A <c>contextId</c> and <c>taskId</c> arrive
    /// from the wire and are treated as chain-resume identifiers — <em>not</em> as
    /// authorization tokens. <see cref="AgentSessionStore"/> accepts an explicit user partition,
    /// while <see cref="ITaskStore"/> has no principal or owner dimension.
    /// Hosts that serve more than one user must supply both dimensions from a trusted identity,
    /// typically by calling <c>UseClaimsBasedAgentIsolation(...)</c> from
    /// <c>Microsoft.Agents.AI.Hosting.AspNetCore</c> (or by registering a custom
    /// <see cref="AgentIsolationKeyProvider"/>). When an <see cref="AgentIsolationKeyProvider"/>
    /// is registered, both the session store and the task store are automatically wrapped
    /// with tenant-scoped isolation. When no isolation provider is registered, behavior
    /// is unchanged — the bare identifiers are used directly, which is appropriate for
    /// first-run / single-user / prototyping scenarios but unsafe for multi-user hosts.
    /// </para>
    /// <para>
    /// Isolation does not configure authentication or endpoint authorization. HTTP hosts must configure
    /// an authentication scheme and enforce authorization on each mapped A2A binding, for example with
    /// <c>RequireAuthorization()</c>. Claims-based isolation also requires <c>AddHttpContextAccessor()</c>
    /// and a claim that uniquely identifies the caller. Task isolation is required for multi-user hosts
    /// even when agent sessions are not persisted, because the task store retains its own state.
    /// </para>
    /// </remarks>
    public static IHostedAgentBuilder AddA2AServer(this IHostedAgentBuilder agentBuilder, Action<A2AServerRegistrationOptions>? configureOptions = null)
    {
        ArgumentNullException.ThrowIfNull(agentBuilder);

        AddA2AServer(agentBuilder.ServiceCollection, agentBuilder.Name, agentBuilder.Lifetime, configureOptions);

        return agentBuilder;
    }

    /// <summary>
    /// Registers an <see cref="A2AServer"/> in the dependency injection container, keyed by the specified
    /// agent name. This method only registers the server; to expose it as an HTTP endpoint, call one of the
    /// <c>MapA2AHttpJson</c> or <c>MapA2AJsonRpc</c> endpoint mapping methods during application startup.
    /// </summary>
    /// <param name="builder">The host application builder to configure.</param>
    /// <param name="agentName">The name of the agent to create an A2A server for.</param>
    /// <param name="configureOptions">An optional callback to configure <see cref="A2AServerRegistrationOptions"/>.</param>
    /// <returns>The <paramref name="builder"/> for chaining.</returns>
    /// <remarks>
    /// See the trust-model remarks on <see cref="AddA2AServer(IHostedAgentBuilder, Action{A2AServerRegistrationOptions}?)"/>
    /// for guidance on multi-user hosts (the wire <c>contextId</c> and <c>taskId</c>
    /// are chain-resume identifiers, not authorization tokens; multi-user hosts must
    /// supply a trusted user partition via <c>UseClaimsBasedAgentIsolation(...)</c> or
    /// a custom <see cref="AgentIsolationKeyProvider"/>).
    /// </remarks>
    public static IHostApplicationBuilder AddA2AServer(this IHostApplicationBuilder builder, string agentName, Action<A2AServerRegistrationOptions>? configureOptions = null)
    {
        ArgumentNullException.ThrowIfNull(builder);

        builder.Services.AddA2AServer(agentName, configureOptions);

        return builder;
    }

    /// <summary>
    /// Registers an <see cref="A2AServer"/> in the dependency injection container for the specified
    /// <see cref="AIAgent"/> instance, keyed by the agent's <see cref="AIAgent.Name"/>. This method only
    /// registers the server; to expose it as an HTTP endpoint, call one of the <c>MapA2AHttpJson</c> or
    /// <c>MapA2AJsonRpc</c> endpoint mapping methods during application startup.
    /// </summary>
    /// <param name="builder">The host application builder to configure.</param>
    /// <param name="agent">The agent instance to create an A2A server for.</param>
    /// <param name="configureOptions">An optional callback to configure <see cref="A2AServerRegistrationOptions"/>.</param>
    /// <returns>The <paramref name="builder"/> for chaining.</returns>
    /// <remarks>
    /// See the trust-model remarks on <see cref="AddA2AServer(IHostedAgentBuilder, Action{A2AServerRegistrationOptions}?)"/>
    /// for guidance on multi-user hosts (the wire <c>contextId</c> and <c>taskId</c>
    /// are chain-resume identifiers, not authorization tokens; multi-user hosts must
    /// supply a trusted user partition via <c>UseClaimsBasedAgentIsolation(...)</c> or
    /// a custom <see cref="AgentIsolationKeyProvider"/>).
    /// </remarks>
    public static IHostApplicationBuilder AddA2AServer(this IHostApplicationBuilder builder, AIAgent agent, Action<A2AServerRegistrationOptions>? configureOptions = null)
    {
        ArgumentNullException.ThrowIfNull(builder);

        builder.Services.AddA2AServer(agent, configureOptions);

        return builder;
    }

    /// <summary>
    /// Registers an <see cref="A2AServer"/> in the dependency injection container, keyed by the specified
    /// agent name. This method only registers the server; to expose it as an HTTP endpoint, call one of the
    /// <c>MapA2AHttpJson</c> or <c>MapA2AJsonRpc</c> endpoint mapping methods during application startup.
    /// </summary>
    /// <param name="services">The service collection to add the A2A server to.</param>
    /// <param name="agentName">The name of the agent to create an A2A server for.</param>
    /// <param name="configureOptions">An optional callback to configure <see cref="A2AServerRegistrationOptions"/>.</param>
    /// <returns>The <paramref name="services"/> for chaining.</returns>
    /// <remarks>
    /// <para>
    /// The server and its task store are singletons shared by all requests. The keyed <see cref="AIAgent"/>, its keyed
    /// <see cref="AgentSessionStore"/>, and an optional keyed <see cref="IAgentHandler"/> are resolved from a new
    /// service scope for each A2A operation, so the configured DI lifetimes of these registrations are honored and
    /// operations that continue in the background keep their services alive until they complete. Persisted sessions
    /// are partitioned by <paramref name="agentName"/>, which remains stable across scoped or transient agent instances.
    /// </para>
    /// <para>
    /// See the trust-model remarks on <see cref="AddA2AServer(IHostedAgentBuilder, Action{A2AServerRegistrationOptions}?)"/>
    /// for guidance on multi-user hosts (the wire <c>contextId</c> and <c>taskId</c>
    /// are chain-resume identifiers, not authorization tokens; multi-user hosts must
    /// supply a trusted user partition via <c>UseClaimsBasedAgentIsolation(...)</c> or
    /// a custom <see cref="AgentIsolationKeyProvider"/>).
    /// </para>
    /// </remarks>
    public static IServiceCollection AddA2AServer(this IServiceCollection services, string agentName, Action<A2AServerRegistrationOptions>? configureOptions = null)
        => AddA2AServer(services, agentName, agentLifetime: null, configureOptions);

    private static IServiceCollection AddA2AServer(IServiceCollection services, string agentName, ServiceLifetime? agentLifetime, Action<A2AServerRegistrationOptions>? configureOptions)
    {
        ArgumentNullException.ThrowIfNull(services);
        ArgumentException.ThrowIfNullOrWhiteSpace(agentName);

        A2AServerRegistrationOptions? options = null;
        if (configureOptions is not null)
        {
            options = new A2AServerRegistrationOptions();
            configureOptions(options);
        }

        services.AddKeyedSingleton(agentName, (sp, _) =>
        {
            // Custom handlers replace the agent, so the agent registration is only required without one.
            bool hasCustomHandler = sp.GetService<IServiceProviderIsKeyedService>()?.IsKeyedService(typeof(IAgentHandler), agentName) ?? false;
            AIAgent? agent = null;
            if (!hasCustomHandler)
            {
                HostedAgentResolution.EnsureAgentRegistered(sp, agentName);
                if (agentLifetime == ServiceLifetime.Singleton)
                {
                    agent = sp.GetRequiredKeyedService<AIAgent>(agentName);
                }
            }

            return CreateA2AServer(sp, agentName, agent, sessionStorageIdentity: agentName, options);
        });

        return services;
    }

    /// <summary>
    /// Registers an <see cref="A2AServer"/> in the dependency injection container for the specified
    /// <see cref="AIAgent"/> instance, keyed by the agent's <see cref="AIAgent.Name"/>. This method only
    /// registers the server; to expose it as an HTTP endpoint, call one of the <c>MapA2AHttpJson</c> or
    /// <c>MapA2AJsonRpc</c> endpoint mapping methods during application startup.
    /// </summary>
    /// <param name="services">The service collection to add the A2A server to.</param>
    /// <param name="agent">The agent instance to create an A2A server for.</param>
    /// <param name="configureOptions">An optional callback to configure <see cref="A2AServerRegistrationOptions"/>.</param>
    /// <returns>The <paramref name="services"/> for chaining.</returns>
    /// <remarks>
    /// See the trust-model remarks on <see cref="AddA2AServer(IHostedAgentBuilder, Action{A2AServerRegistrationOptions}?)"/>
    /// for guidance on multi-user hosts (the wire <c>contextId</c> and <c>taskId</c>
    /// are chain-resume identifiers, not authorization tokens; multi-user hosts must
    /// supply a trusted user partition via <c>UseClaimsBasedAgentIsolation(...)</c> or
    /// a custom <see cref="AgentIsolationKeyProvider"/>).
    /// </remarks>
    public static IServiceCollection AddA2AServer(this IServiceCollection services, AIAgent agent, Action<A2AServerRegistrationOptions>? configureOptions = null)
    {
        ArgumentNullException.ThrowIfNull(services);
        ArgumentNullException.ThrowIfNull(agent);
        ArgumentException.ThrowIfNullOrWhiteSpace(agent.Name, nameof(agent) + "." + nameof(agent.Name));

        A2AServerRegistrationOptions? options = null;
        if (configureOptions is not null)
        {
            options = new A2AServerRegistrationOptions();
            configureOptions(options);
        }

        services.AddKeyedSingleton(agent.Name, (sp, _) => CreateA2AServer(sp, agent.Name, agent, sessionStorageIdentity: null, options));

        return services;
    }

    private static A2AServer CreateA2AServer(
        IServiceProvider serviceProvider,
        string agentName,
        AIAgent? agent,
        string? sessionStorageIdentity,
        A2AServerRegistrationOptions? options)
    {
        // The server owns task state shared across requests, while the agent and its session services are
        // resolved for each operation so that scoped and transient registrations keep their lifetimes.
        var agentHandler = new ScopedA2AAgentHandler(
            serviceProvider.GetRequiredService<IServiceScopeFactory>(),
            agentName,
            agent,
            sessionStorageIdentity,
            options?.AgentRunMode ?? AgentRunMode.ReturnMessage);

        return CreateA2AServer(serviceProvider, agentName, agentHandler, options);
    }

    /// <summary>
    /// Creates an <see cref="A2AServer"/> for the specified agent name with its keyed or default task store.
    /// </summary>
    /// <param name="serviceProvider">The application service provider.</param>
    /// <param name="agentName">The name that keys the agent's hosted services.</param>
    /// <param name="agentHandler">The handler that executes A2A operations.</param>
    /// <param name="options">The optional registration options.</param>
    /// <returns>The created server.</returns>
    internal static A2AServer CreateA2AServer(IServiceProvider serviceProvider, string agentName, IAgentHandler agentHandler, A2AServerRegistrationOptions? options)
    {
        var isolationKeyProvider = serviceProvider.GetService<AgentIsolationKeyProvider>();
        var loggerFactory = serviceProvider.GetService<ILoggerFactory>() ?? NullLoggerFactory.Instance;
        ITaskStore taskStore = serviceProvider.GetKeyedService<ITaskStore>(agentName) ?? new InMemoryTaskStore();

        // Wrap the task store with isolation key scoping, same as the session store.
        if (taskStore is not IsolationKeyScopedTaskStore)
        {
            taskStore = new IsolationKeyScopedTaskStore(taskStore, isolationKeyProvider, strict: isolationKeyProvider != null);
        }

        return new A2AServer(
            agentHandler,
            taskStore,
            new ChannelEventNotifier(),
            loggerFactory.CreateLogger<A2AServer>(),
            options?.ServerOptions);
    }

    /// <summary>
    /// Creates the hosting wrapper that persists the sessions of an agent served over A2A.
    /// </summary>
    /// <param name="services">The service provider that owns the agent's session services.</param>
    /// <param name="agent">The agent to host.</param>
    /// <param name="agentName">The name that keys the agent's session store.</param>
    /// <param name="sessionStorageIdentity">
    /// The stable logical identity that partitions persisted sessions, or <see langword="null"/> to use the agent instance identity.
    /// </param>
    /// <returns>The hosting wrapper for <paramref name="agent"/>.</returns>
    internal static AIHostAgent CreateHostAgent(IServiceProvider services, AIAgent agent, string agentName, string? sessionStorageIdentity)
    {
        var isolationKeyProvider = services.GetService<AgentIsolationKeyProvider>();
        var agentSessionStore = services.GetKeyedService<AgentSessionStore>(agentName);

        // Ensure that we have an IsolationKeyScopedAgentSessionStore registered.
        if (agentSessionStore?.GetService<IsolationKeyScopedAgentSessionStore>() is null)
        {
            agentSessionStore ??= new NoopAgentSessionStore();
            agentSessionStore = new IsolationKeyScopedAgentSessionStore(agentSessionStore, isolationKeyProvider, new() { Strict = isolationKeyProvider != null });
        }

        return new AIHostAgent(agent, agentSessionStore, sessionStorageIdentity);
    }
}
