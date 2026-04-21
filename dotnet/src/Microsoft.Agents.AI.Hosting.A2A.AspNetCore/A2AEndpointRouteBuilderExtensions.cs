// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics.CodeAnalysis;
using A2A;
using A2A.AspNetCore;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Hosting;
using Microsoft.Agents.AI.Hosting.A2A;
using Microsoft.AspNetCore.Routing;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.AspNetCore.Builder;

/// <summary>
/// Provides extension methods for configuring A2A endpoints for AI agents.
/// </summary>
[Experimental(DiagnosticIds.Experiments.AIResponseContinuations)]
public static class A2AEndpointRouteBuilderExtensions
{
    /// <summary>
    /// Maps A2A endpoints for the specified agent to the given path.
    /// </summary>
    /// <param name="endpoints">The <see cref="IEndpointRouteBuilder"/> to add the A2A endpoints to.</param>
    /// <param name="agentBuilder">The configuration builder for <see cref="AIAgent"/>.</param>
    /// <param name="path">The route path prefix for A2A endpoints.</param>
    /// <param name="protocolBindings">The A2A protocol binding(s) to expose. When <see langword="null"/>, defaults to <see cref="A2AProtocolBinding.HttpJson"/>.</param>
    /// <param name="agentRunMode">The agent run mode that controls how the agent responds to A2A requests. When <see langword="null"/>, defaults to <see cref="AgentRunMode.DisallowBackground"/>.</param>
    /// <returns>An <see cref="IEndpointConventionBuilder"/> for further endpoint configuration.</returns>
    public static IEndpointConventionBuilder MapA2A(this IEndpointRouteBuilder endpoints, IHostedAgentBuilder agentBuilder, string path, A2AProtocolBinding? protocolBindings, AgentRunMode? agentRunMode = null)
    {
        ArgumentNullException.ThrowIfNull(agentBuilder);

        return endpoints.MapA2A(agentBuilder.Name, path, protocolBindings, agentRunMode);
    }

    /// <summary>
    /// Maps A2A endpoints for the specified agent to the given path.
    /// </summary>
    /// <param name="endpoints">The <see cref="IEndpointRouteBuilder"/> to add the A2A endpoints to.</param>
    /// <param name="agentBuilder">The configuration builder for <see cref="AIAgent"/>.</param>
    /// <param name="path">The route path prefix for A2A endpoints.</param>
    /// <param name="configureOptions">An optional callback to configure <see cref="A2AHostingOptions"/>.</param>
    /// <returns>An <see cref="IEndpointConventionBuilder"/> for further endpoint configuration.</returns>
    public static IEndpointConventionBuilder MapA2A(this IEndpointRouteBuilder endpoints, IHostedAgentBuilder agentBuilder, string path, Action<A2AHostingOptions>? configureOptions = null)
    {
        ArgumentNullException.ThrowIfNull(agentBuilder);

        return endpoints.MapA2A(agentBuilder.Name, path, configureOptions);
    }

    /// <summary>
    /// Maps A2A endpoints for the agent with the specified name to the given path.
    /// </summary>
    /// <param name="endpoints">The <see cref="IEndpointRouteBuilder"/> to add the A2A endpoints to.</param>
    /// <param name="agentName">The name of the agent to use for A2A protocol integration.</param>
    /// <param name="path">The route path prefix for A2A endpoints.</param>
    /// <param name="protocolBindings">The A2A protocol binding(s) to expose. When <see langword="null"/>, defaults to <see cref="A2AProtocolBinding.HttpJson"/>.</param>
    /// <param name="agentRunMode">The agent run mode that controls how the agent responds to A2A requests. When <see langword="null"/>, defaults to <see cref="AgentRunMode.DisallowBackground"/>.</param>
    /// <returns>An <see cref="IEndpointConventionBuilder"/> for further endpoint configuration.</returns>
    public static IEndpointConventionBuilder MapA2A(this IEndpointRouteBuilder endpoints, string agentName, string path, A2AProtocolBinding? protocolBindings, AgentRunMode? agentRunMode = null)
    {
        ArgumentNullException.ThrowIfNull(endpoints);
        ArgumentException.ThrowIfNullOrEmpty(agentName);

        var agent = endpoints.ServiceProvider.GetRequiredKeyedService<AIAgent>(agentName);

        return endpoints.MapA2A(agent, path, protocolBindings, agentRunMode);
    }

    /// <summary>
    /// Maps A2A endpoints for the agent with the specified name to the given path.
    /// </summary>
    /// <param name="endpoints">The <see cref="IEndpointRouteBuilder"/> to add the A2A endpoints to.</param>
    /// <param name="agentName">The name of the agent to use for A2A protocol integration.</param>
    /// <param name="path">The route path prefix for A2A endpoints.</param>
    /// <param name="configureOptions">An optional callback to configure <see cref="A2AHostingOptions"/>.</param>
    /// <returns>An <see cref="IEndpointConventionBuilder"/> for further endpoint configuration.</returns>
    public static IEndpointConventionBuilder MapA2A(this IEndpointRouteBuilder endpoints, string agentName, string path, Action<A2AHostingOptions>? configureOptions = null)
    {
        ArgumentNullException.ThrowIfNull(endpoints);
        ArgumentException.ThrowIfNullOrEmpty(agentName);

        var agent = endpoints.ServiceProvider.GetRequiredKeyedService<AIAgent>(agentName);

        return endpoints.MapA2A(agent, path, configureOptions);
    }

    /// <summary>
    /// Maps A2A endpoints for the specified agent to the given path.
    /// </summary>
    /// <param name="endpoints">The <see cref="IEndpointRouteBuilder"/> to add the A2A endpoints to.</param>
    /// <param name="agent">The agent to use for A2A protocol integration.</param>
    /// <param name="path">The route path prefix for A2A endpoints.</param>
    /// <param name="protocolBindings">The A2A protocol binding(s) to expose. When <see langword="null"/>, defaults to <see cref="A2AProtocolBinding.HttpJson"/>.</param>
    /// <param name="agentRunMode">The agent run mode that controls how the agent responds to A2A requests. When <see langword="null"/>, defaults to <see cref="AgentRunMode.DisallowBackground"/>.</param>
    /// <returns>An <see cref="IEndpointConventionBuilder"/> for further endpoint configuration.</returns>
    public static IEndpointConventionBuilder MapA2A(this IEndpointRouteBuilder endpoints, AIAgent agent, string path, A2AProtocolBinding? protocolBindings, AgentRunMode? agentRunMode = null)
    {
        Action<A2AHostingOptions>? configureOptions = null;

        if (protocolBindings is not null || agentRunMode is not null)
        {
            configureOptions = options =>
            {
                options.ProtocolBindings = protocolBindings;
                options.AgentRunMode = agentRunMode;
            };
        }

        return endpoints.MapA2A(agent, path, configureOptions);
    }

    /// <summary>
    /// Maps A2A endpoints for the specified agent to the given path.
    /// </summary>
    /// <param name="endpoints">The <see cref="IEndpointRouteBuilder"/> to add the A2A endpoints to.</param>
    /// <param name="agent">The agent to use for A2A protocol integration.</param>
    /// <param name="path">The route path prefix for A2A endpoints.</param>
    /// <param name="configureOptions">An optional callback to configure <see cref="A2AHostingOptions"/>.</param>
    /// <returns>An <see cref="IEndpointConventionBuilder"/> for further endpoint configuration.</returns>
    public static IEndpointConventionBuilder MapA2A(this IEndpointRouteBuilder endpoints, AIAgent agent, string path, Action<A2AHostingOptions>? configureOptions = null)
    {
        ArgumentNullException.ThrowIfNull(endpoints);
        ArgumentNullException.ThrowIfNull(agent);
        ArgumentException.ThrowIfNullOrWhiteSpace(path);
        ArgumentException.ThrowIfNullOrWhiteSpace(agent.Name, nameof(agent) + "." + nameof(agent.Name));

        A2AHostingOptions? options = null;
        if (configureOptions is not null)
        {
            options = new A2AHostingOptions();
            configureOptions(options);
        }

        var a2aServer = CreateA2AServer(endpoints, agent, options);

        return MapA2AEndpoints(endpoints, a2aServer, path, options?.ProtocolBindings);
    }

    private static A2AServer CreateA2AServer(IEndpointRouteBuilder endpoints, AIAgent agent, A2AHostingOptions? options)
    {
        var agentHandler = endpoints.ServiceProvider.GetKeyedService<IAgentHandler>(agent.Name);
        if (agentHandler is null)
        {
            var agentSessionStore = endpoints.ServiceProvider.GetKeyedService<AgentSessionStore>(agent.Name);
            agentHandler = agent.MapA2A(agentSessionStore: agentSessionStore, runMode: options?.AgentRunMode);
        }

        var loggerFactory = endpoints.ServiceProvider.GetService<ILoggerFactory>() ?? NullLoggerFactory.Instance;
        var taskStore = endpoints.ServiceProvider.GetKeyedService<ITaskStore>(agent.Name) ?? new InMemoryTaskStore();

        return new A2AServer(
            agentHandler,
            taskStore,
            new ChannelEventNotifier(),
            loggerFactory.CreateLogger<A2AServer>(),
            options?.ServerOptions);
    }

    private static IEndpointConventionBuilder MapA2AEndpoints(IEndpointRouteBuilder endpoints, A2AServer a2aServer, string path, A2AProtocolBinding? protocolBindings)
    {
        protocolBindings ??= A2AProtocolBinding.HttpJson;

        IEndpointConventionBuilder? result = null;

        if (protocolBindings.Value.HasFlag(A2AProtocolBinding.JsonRpc))
        {
            result = endpoints.MapA2A(a2aServer, path);
        }

        if (protocolBindings.Value.HasFlag(A2AProtocolBinding.HttpJson))
        {
            // TODO: The stub AgentCard is temporary and will be removed once the A2A SDK either removes the
            // agentCard parameter of MapHttpA2A or makes it optional. MapHttpA2A exposes the agent card via a
            // GET {path}/card endpoint that is not part of the A2A spec, so it is not expected to be consumed
            // by any agent - returning a stub agent card here is safe.
            var stubAgentCard = new AgentCard { Name = "A2A Agent" };

            result = endpoints.MapHttpA2A(a2aServer, stubAgentCard, path);
        }

        return result ?? throw new InvalidOperationException("At least one A2A protocol binding must be specified.");
    }
}
