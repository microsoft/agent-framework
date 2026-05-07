// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics.CodeAnalysis;
using A2A;
using A2A.AspNetCore;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Hosting;
using Microsoft.AspNetCore.Routing;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.AspNetCore.Builder;

/// <summary>
/// Provides extension methods for mapping A2A protocol endpoints for AI agents.
/// </summary>
[Experimental(DiagnosticIds.Experiments.AIResponseContinuations)]
public static class A2AEndpointRouteBuilderExtensions
{
    /// <summary>
    /// Maps A2A HTTP+JSON endpoints for the specified agent to the given path.
    /// An <see cref="A2AServer"/> for the agent must be registered first by calling
    /// <c>AddA2AServer</c> during service registration.
    /// </summary>
    /// <param name="endpoints">The <see cref="IEndpointRouteBuilder"/> to add the A2A endpoints to.</param>
    /// <param name="agentBuilder">The configuration builder for the agent.</param>
    /// <param name="path">The route path prefix for A2A endpoints.</param>
    /// <returns>An <see cref="IEndpointConventionBuilder"/> for further endpoint configuration.</returns>
    public static IEndpointConventionBuilder MapA2AHttpJson(this IEndpointRouteBuilder endpoints, IHostedAgentBuilder agentBuilder, string path)
    {
        ArgumentNullException.ThrowIfNull(agentBuilder);

        return endpoints.MapA2AHttpJson(agentBuilder.Name, path);
    }

    /// <summary>
    /// Maps A2A HTTP+JSON endpoints for the specified agent to the given path.
    /// An <see cref="A2AServer"/> for the agent must be registered first by calling
    /// <c>AddA2AServer</c> during service registration.
    /// </summary>
    /// <param name="endpoints">The <see cref="IEndpointRouteBuilder"/> to add the A2A endpoints to.</param>
    /// <param name="agent">The agent whose name identifies the registered A2A server.</param>
    /// <param name="path">The route path prefix for A2A endpoints.</param>
    /// <returns>An <see cref="IEndpointConventionBuilder"/> for further endpoint configuration.</returns>
    public static IEndpointConventionBuilder MapA2AHttpJson(this IEndpointRouteBuilder endpoints, AIAgent agent, string path)
    {
        ArgumentNullException.ThrowIfNull(agent);
        ArgumentException.ThrowIfNullOrWhiteSpace(agent.Name, nameof(agent) + "." + nameof(agent.Name));

        return endpoints.MapA2AHttpJson(agent.Name, path);
    }

    /// <summary>
    /// Maps A2A HTTP+JSON endpoints for the agent with the specified name to the given path.
    /// An <see cref="A2AServer"/> for the agent must be registered first by calling
    /// <c>AddA2AServer</c> during service registration.
    /// </summary>
    /// <param name="endpoints">The <see cref="IEndpointRouteBuilder"/> to add the A2A endpoints to.</param>
    /// <param name="agentName">The name of the agent to use for A2A protocol integration.</param>
    /// <param name="path">The route path prefix for A2A endpoints.</param>
    /// <returns>An <see cref="IEndpointConventionBuilder"/> for further endpoint configuration.</returns>
    public static IEndpointConventionBuilder MapA2AHttpJson(this IEndpointRouteBuilder endpoints, string agentName, string path)
    {
        ArgumentNullException.ThrowIfNull(endpoints);
        ArgumentException.ThrowIfNullOrWhiteSpace(agentName);
        ArgumentException.ThrowIfNullOrWhiteSpace(path);

        var a2aServer = endpoints.ServiceProvider.GetKeyedService<A2AServer>(agentName)
            ?? throw new InvalidOperationException(
                $"No A2AServer is registered for agent '{agentName}'. " +
                $"Call services.AddA2AServer(\"{agentName}\") or agentBuilder.AddA2AServer() during service registration to register one.");

        // TODO: The stub AgentCard is temporary and will be removed once the A2A SDK either removes the
        // agentCard parameter of MapHttpA2A or makes it optional. MapHttpA2A exposes the agent card via a
        // GET {path}/card endpoint that is not part of the A2A spec, so it is not expected to be consumed
        // by any agent - returning a stub agent card here is safe.
        var stubAgentCard = new AgentCard { Name = "A2A Agent" };

        return endpoints.MapHttpA2A(a2aServer, stubAgentCard, path);
    }

    /// <summary>
    /// Maps A2A JSON-RPC endpoints for the specified agent to the given path.
    /// An <see cref="A2AServer"/> for the agent must be registered first by calling
    /// <c>AddA2AServer</c> during service registration.
    /// </summary>
    /// <param name="endpoints">The <see cref="IEndpointRouteBuilder"/> to add the A2A endpoints to.</param>
    /// <param name="agentBuilder">The configuration builder for the agent.</param>
    /// <param name="path">The route path prefix for A2A endpoints.</param>
    /// <returns>An <see cref="IEndpointConventionBuilder"/> for further endpoint configuration.</returns>
    public static IEndpointConventionBuilder MapA2AJsonRpc(this IEndpointRouteBuilder endpoints, IHostedAgentBuilder agentBuilder, string path)
    {
        ArgumentNullException.ThrowIfNull(agentBuilder);

        return endpoints.MapA2AJsonRpc(agentBuilder.Name, path);
    }

    /// <summary>
    /// Maps A2A JSON-RPC endpoints for the specified agent to the given path.
    /// An <see cref="A2AServer"/> for the agent must be registered first by calling
    /// <c>AddA2AServer</c> during service registration.
    /// </summary>
    /// <param name="endpoints">The <see cref="IEndpointRouteBuilder"/> to add the A2A endpoints to.</param>
    /// <param name="agent">The agent whose name identifies the registered A2A server.</param>
    /// <param name="path">The route path prefix for A2A endpoints.</param>
    /// <returns>An <see cref="IEndpointConventionBuilder"/> for further endpoint configuration.</returns>
    public static IEndpointConventionBuilder MapA2AJsonRpc(this IEndpointRouteBuilder endpoints, AIAgent agent, string path)
    {
        ArgumentNullException.ThrowIfNull(agent);
        ArgumentException.ThrowIfNullOrWhiteSpace(agent.Name, nameof(agent) + "." + nameof(agent.Name));

        return endpoints.MapA2AJsonRpc(agent.Name, path);
    }

    /// <summary>
    /// Maps A2A JSON-RPC endpoints for the agent with the specified name to the given path.
    /// An <see cref="A2AServer"/> for the agent must be registered first by calling
    /// <c>AddA2AServer</c> during service registration.
    /// </summary>
    /// <param name="endpoints">The <see cref="IEndpointRouteBuilder"/> to add the A2A endpoints to.</param>
    /// <param name="agentName">The name of the agent to use for A2A protocol integration.</param>
    /// <param name="path">The route path prefix for A2A endpoints.</param>
    /// <returns>An <see cref="IEndpointConventionBuilder"/> for further endpoint configuration.</returns>
    public static IEndpointConventionBuilder MapA2AJsonRpc(this IEndpointRouteBuilder endpoints, string agentName, string path)
    {
        ArgumentNullException.ThrowIfNull(endpoints);
        ArgumentException.ThrowIfNullOrWhiteSpace(agentName);
        ArgumentException.ThrowIfNullOrWhiteSpace(path);

        var a2aServer = endpoints.ServiceProvider.GetKeyedService<A2AServer>(agentName)
            ?? throw new InvalidOperationException(
                $"No A2AServer is registered for agent '{agentName}'. " +
                $"Call services.AddA2AServer(\"{agentName}\") or agentBuilder.AddA2AServer() during service registration to register one.");

        return endpoints.MapA2A(a2aServer, path);
    }
}
