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
    public static IHostedAgentBuilder AddA2AServer(this IHostedAgentBuilder agentBuilder, Action<A2AServerRegistrationOptions>? configureOptions = null)
    {
        ArgumentNullException.ThrowIfNull(agentBuilder);

        agentBuilder.ServiceCollection.AddA2AServer(agentBuilder.Name, configureOptions);

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
    public static IServiceCollection AddA2AServer(this IServiceCollection services, string agentName, Action<A2AServerRegistrationOptions>? configureOptions = null)
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
            var agent = sp.GetRequiredKeyedService<AIAgent>(agentName);
            return CreateA2AServer(sp, agent, options);
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

        services.AddKeyedSingleton(agent.Name, (sp, _) => CreateA2AServer(sp, agent, options));

        return services;
    }

    private static A2AServer CreateA2AServer(IServiceProvider serviceProvider, AIAgent agent, A2AServerRegistrationOptions? options)
    {
        var agentHandler = serviceProvider.GetKeyedService<IAgentHandler>(agent.Name);
        if (agentHandler is null)
        {
            var agentSessionStore = serviceProvider.GetKeyedService<AgentSessionStore>(agent.Name);
            var runMode = options?.AgentRunMode ?? AgentRunMode.DisallowBackground;

            var hostAgent = new AIHostAgent(
                innerAgent: agent,
                sessionStore: agentSessionStore ?? new InMemoryAgentSessionStore());

            agentHandler = new A2AAgentHandler(hostAgent, runMode);
        }

        var loggerFactory = serviceProvider.GetService<ILoggerFactory>() ?? NullLoggerFactory.Instance;
        var taskStore = serviceProvider.GetKeyedService<ITaskStore>(agent.Name) ?? new InMemoryTaskStore();

        return new A2AServer(
            agentHandler,
            taskStore,
            new ChannelEventNotifier(),
            loggerFactory.CreateLogger<A2AServer>(),
            options?.ServerOptions);
    }
}
