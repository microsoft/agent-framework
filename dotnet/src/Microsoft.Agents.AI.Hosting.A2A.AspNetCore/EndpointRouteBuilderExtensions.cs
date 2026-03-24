// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics.CodeAnalysis;
using A2A;
using A2A.AspNetCore;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Hosting;
using Microsoft.Agents.AI.Hosting.A2A;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Routing;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.AspNetCore.Builder;

/// <summary>
/// Provides extension methods for configuring A2A (Agent2Agent) communication in a host application builder.
/// </summary>
[Experimental(DiagnosticIds.Experiments.AIResponseContinuations)]
public static class MicrosoftAgentAIHostingA2AEndpointRouteBuilderExtensions
{
    /// <summary>
    /// Attaches A2A (Agent2Agent) communication capabilities via Message processing to the specified web application.
    /// </summary>
    /// <param name="endpoints">The <see cref="IEndpointRouteBuilder"/> to add the A2A endpoints to.</param>
    /// <param name="agentBuilder">The configuration builder for <see cref="AIAgent"/>.</param>
    /// <param name="path">The route group to use for A2A endpoints.</param>
    /// <returns>An <see cref="IEndpointConventionBuilder"/> for further endpoint configuration.</returns>
    /// <remarks>
    /// This method can be used to access A2A agents that support the
    /// <see href="https://github.com/a2aproject/A2A/blob/main/docs/topics/agent-discovery.md#2-curated-registries-catalog-based-discovery">Curated Registries (Catalog-Based Discovery)</see>
    /// discovery mechanism.
    /// </remarks>
    public static IEndpointConventionBuilder MapA2A(this IEndpointRouteBuilder endpoints, IHostedAgentBuilder agentBuilder, string path)
    {
        ArgumentNullException.ThrowIfNull(agentBuilder);
        return endpoints.MapA2A(agentBuilder.Name, path);
    }

    /// <summary>
    /// Attaches A2A (Agent2Agent) communication capabilities via Message processing to the specified web application.
    /// </summary>
    /// <param name="endpoints">The <see cref="IEndpointRouteBuilder"/> to add the A2A endpoints to.</param>
    /// <param name="agentBuilder">The configuration builder for <see cref="AIAgent"/>.</param>
    /// <param name="path">The route group to use for A2A endpoints.</param>
    /// <param name="agentRunMode">Controls the response behavior of the agent run.</param>
    /// <returns>An <see cref="IEndpointConventionBuilder"/> for further endpoint configuration.</returns>
    public static IEndpointConventionBuilder MapA2A(this IEndpointRouteBuilder endpoints, IHostedAgentBuilder agentBuilder, string path, AgentRunMode agentRunMode)
    {
        ArgumentNullException.ThrowIfNull(agentBuilder);
        return endpoints.MapA2A(agentBuilder.Name, path, agentRunMode);
    }

    /// <summary>
    /// Attaches A2A (Agent2Agent) communication capabilities via Message processing to the specified web application.
    /// </summary>
    /// <param name="endpoints">The <see cref="IEndpointRouteBuilder"/> to add the A2A endpoints to.</param>
    /// <param name="agentName">The name of the agent to use for A2A protocol integration.</param>
    /// <param name="path">The route group to use for A2A endpoints.</param>
    /// <returns>An <see cref="IEndpointConventionBuilder"/> for further endpoint configuration.</returns>
    public static IEndpointConventionBuilder MapA2A(this IEndpointRouteBuilder endpoints, string agentName, string path)
    {
        ArgumentNullException.ThrowIfNull(endpoints);
        var agent = endpoints.ServiceProvider.GetRequiredKeyedService<AIAgent>(agentName);
        return endpoints.MapA2A(agent, path);
    }

    /// <summary>
    /// Attaches A2A (Agent2Agent) communication capabilities via Message processing to the specified web application.
    /// </summary>
    /// <param name="endpoints">The <see cref="IEndpointRouteBuilder"/> to add the A2A endpoints to.</param>
    /// <param name="agentName">The name of the agent to use for A2A protocol integration.</param>
    /// <param name="path">The route group to use for A2A endpoints.</param>
    /// <param name="agentRunMode">Controls the response behavior of the agent run.</param>
    /// <returns>An <see cref="IEndpointConventionBuilder"/> for further endpoint configuration.</returns>
    public static IEndpointConventionBuilder MapA2A(this IEndpointRouteBuilder endpoints, string agentName, string path, AgentRunMode agentRunMode)
    {
        ArgumentNullException.ThrowIfNull(endpoints);
        var agent = endpoints.ServiceProvider.GetRequiredKeyedService<AIAgent>(agentName);
        return endpoints.MapA2A(agent, path, agentRunMode);
    }

    /// <summary>
    /// Attaches A2A (Agent2Agent) communication capabilities via Message processing to the specified web application.
    /// </summary>
    /// <param name="endpoints">The <see cref="IEndpointRouteBuilder"/> to add the A2A endpoints to.</param>
    /// <param name="agentBuilder">The configuration builder for <see cref="AIAgent"/>.</param>
    /// <param name="path">The route group to use for A2A endpoints.</param>
    /// <param name="agentCard">Agent card describing the agent's capabilities for discovery.</param>
    /// <returns>An <see cref="IEndpointConventionBuilder"/> for further endpoint configuration.</returns>
    /// <remarks>
    /// This method can be used to access A2A agents that support the
    /// <see href="https://github.com/a2aproject/A2A/blob/main/docs/topics/agent-discovery.md#2-curated-registries-catalog-based-discovery">Curated Registries (Catalog-Based Discovery)</see>
    /// discovery mechanism.
    /// </remarks>
    public static IEndpointConventionBuilder MapA2A(this IEndpointRouteBuilder endpoints, IHostedAgentBuilder agentBuilder, string path, AgentCard agentCard)
    {
        ArgumentNullException.ThrowIfNull(agentBuilder);
        return endpoints.MapA2A(agentBuilder.Name, path, agentCard);
    }

    /// <summary>
    /// Attaches A2A (Agent2Agent) communication capabilities via Message processing to the specified web application.
    /// </summary>
    /// <param name="endpoints">The <see cref="IEndpointRouteBuilder"/> to add the A2A endpoints to.</param>
    /// <param name="agentName">The name of the agent to use for A2A protocol integration.</param>
    /// <param name="path">The route group to use for A2A endpoints.</param>
    /// <param name="agentCard">Agent card describing the agent's capabilities for discovery.</param>
    /// <returns>An <see cref="IEndpointConventionBuilder"/> for further endpoint configuration.</returns>
    /// <remarks>
    /// This method can be used to access A2A agents that support the
    /// <see href="https://github.com/a2aproject/A2A/blob/main/docs/topics/agent-discovery.md#2-curated-registries-catalog-based-discovery">Curated Registries (Catalog-Based Discovery)</see>
    /// discovery mechanism.
    /// </remarks>
    public static IEndpointConventionBuilder MapA2A(this IEndpointRouteBuilder endpoints, string agentName, string path, AgentCard agentCard)
    {
        ArgumentNullException.ThrowIfNull(endpoints);
        var agent = endpoints.ServiceProvider.GetRequiredKeyedService<AIAgent>(agentName);
        return endpoints.MapA2A(agent, path, agentCard);
    }

    /// <summary>
    /// Attaches A2A (Agent2Agent) communication capabilities via Message processing to the specified web application.
    /// </summary>
    /// <param name="endpoints">The <see cref="IEndpointRouteBuilder"/> to add the A2A endpoints to.</param>
    /// <param name="agentBuilder">The configuration builder for <see cref="AIAgent"/>.</param>
    /// <param name="path">The route group to use for A2A endpoints.</param>
    /// <param name="agentCard">Agent card describing the agent's capabilities for discovery.</param>
    /// <param name="agentRunMode">Controls the response behavior of the agent run.</param>
    /// <returns>An <see cref="IEndpointConventionBuilder"/> for further endpoint configuration.</returns>
    public static IEndpointConventionBuilder MapA2A(this IEndpointRouteBuilder endpoints, IHostedAgentBuilder agentBuilder, string path, AgentCard agentCard, AgentRunMode agentRunMode)
    {
        ArgumentNullException.ThrowIfNull(agentBuilder);
        return endpoints.MapA2A(agentBuilder.Name, path, agentCard, agentRunMode);
    }

    /// <summary>
    /// Attaches A2A (Agent2Agent) communication capabilities via Message processing to the specified web application.
    /// </summary>
    /// <param name="endpoints">The <see cref="IEndpointRouteBuilder"/> to add the A2A endpoints to.</param>
    /// <param name="agentName">The name of the agent to use for A2A protocol integration.</param>
    /// <param name="path">The route group to use for A2A endpoints.</param>
    /// <param name="agentCard">Agent card describing the agent's capabilities for discovery.</param>
    /// <param name="agentRunMode">Controls the response behavior of the agent run.</param>
    /// <returns>An <see cref="IEndpointConventionBuilder"/> for further endpoint configuration.</returns>
    public static IEndpointConventionBuilder MapA2A(this IEndpointRouteBuilder endpoints, string agentName, string path, AgentCard agentCard, AgentRunMode agentRunMode)
    {
        ArgumentNullException.ThrowIfNull(endpoints);
        var agent = endpoints.ServiceProvider.GetRequiredKeyedService<AIAgent>(agentName);
        return endpoints.MapA2A(agent, path, agentCard, agentRunMode);
    }

    /// <summary>
    /// Attaches A2A (Agent2Agent) communication capabilities via Message processing to the specified web application.
    /// </summary>
    /// <param name="endpoints">The <see cref="IEndpointRouteBuilder"/> to add the A2A endpoints to.</param>
    /// <param name="agent">The agent to use for A2A protocol integration.</param>
    /// <param name="path">The route group to use for A2A endpoints.</param>
    /// <returns>An <see cref="IEndpointConventionBuilder"/> for further endpoint configuration.</returns>
    public static IEndpointConventionBuilder MapA2A(this IEndpointRouteBuilder endpoints, AIAgent agent, string path)
        => endpoints.MapA2A(agent, path, AgentRunMode.DisallowBackground);

    /// <summary>
    /// Attaches A2A (Agent2Agent) communication capabilities via Message processing to the specified web application.
    /// </summary>
    /// <param name="endpoints">The <see cref="IEndpointRouteBuilder"/> to add the A2A endpoints to.</param>
    /// <param name="agent">The agent to use for A2A protocol integration.</param>
    /// <param name="path">The route group to use for A2A endpoints.</param>
    /// <param name="agentRunMode">Controls the response behavior of the agent run.</param>
    /// <returns>An <see cref="IEndpointConventionBuilder"/> for further endpoint configuration.</returns>
    public static IEndpointConventionBuilder MapA2A(this IEndpointRouteBuilder endpoints, AIAgent agent, string path, AgentRunMode agentRunMode)
    {
        ArgumentNullException.ThrowIfNull(endpoints);
        ArgumentNullException.ThrowIfNull(agent);

        var loggerFactory = endpoints.ServiceProvider.GetRequiredService<ILoggerFactory>();
        var agentSessionStore = endpoints.ServiceProvider.GetKeyedService<AgentSessionStore>(agent.Name);
        var handler = agent.MapA2A(loggerFactory: loggerFactory, agentSessionStore: agentSessionStore, runMode: agentRunMode);
        return A2ARouteBuilderExtensions.MapA2A(endpoints, handler, path);
    }

    /// <summary>
    /// Attaches A2A (Agent2Agent) communication capabilities via Message processing to the specified web application.
    /// </summary>
    /// <param name="endpoints">The <see cref="IEndpointRouteBuilder"/> to add the A2A endpoints to.</param>
    /// <param name="agent">The agent to use for A2A protocol integration.</param>
    /// <param name="path">The route group to use for A2A endpoints.</param>
    /// <param name="agentCard">Agent card describing the agent's capabilities for discovery.</param>
    /// <returns>An <see cref="IEndpointConventionBuilder"/> for further endpoint configuration.</returns>
    /// <remarks>
    /// This method can be used to access A2A agents that support the
    /// <see href="https://github.com/a2aproject/A2A/blob/main/docs/topics/agent-discovery.md#2-curated-registries-catalog-based-discovery">Curated Registries (Catalog-Based Discovery)</see>
    /// discovery mechanism.
    /// </remarks>
    public static IEndpointConventionBuilder MapA2A(this IEndpointRouteBuilder endpoints, AIAgent agent, string path, AgentCard agentCard)
        => endpoints.MapA2A(agent, path, agentCard, AgentRunMode.DisallowBackground);

    /// <summary>
    /// Attaches A2A (Agent2Agent) communication capabilities via Message processing to the specified web application.
    /// </summary>
    /// <param name="endpoints">The <see cref="IEndpointRouteBuilder"/> to add the A2A endpoints to.</param>
    /// <param name="agent">The agent to use for A2A protocol integration.</param>
    /// <param name="path">The route group to use for A2A endpoints.</param>
    /// <param name="agentCard">Agent card describing the agent's capabilities for discovery.</param>
    /// <param name="agentRunMode">Controls the response behavior of the agent run.</param>
    /// <returns>An <see cref="IEndpointConventionBuilder"/> for further endpoint configuration.</returns>
    /// <remarks>
    /// This method can be used to access A2A agents that support the
    /// <see href="https://github.com/a2aproject/A2A/blob/main/docs/topics/agent-discovery.md#2-curated-registries-catalog-based-discovery">Curated Registries (Catalog-Based Discovery)</see>
    /// discovery mechanism.
    /// </remarks>
    public static IEndpointConventionBuilder MapA2A(this IEndpointRouteBuilder endpoints, AIAgent agent, string path, AgentCard agentCard, AgentRunMode agentRunMode)
    {
        ArgumentNullException.ThrowIfNull(endpoints);
        ArgumentNullException.ThrowIfNull(agent);

        var loggerFactory = endpoints.ServiceProvider.GetRequiredService<ILoggerFactory>();
        var agentSessionStore = endpoints.ServiceProvider.GetKeyedService<AgentSessionStore>(agent.Name);
        var handler = agent.MapA2A(loggerFactory: loggerFactory, agentSessionStore: agentSessionStore, runMode: agentRunMode);
        A2ARouteBuilderExtensions.MapA2A(endpoints, handler, path);
        endpoints.MapWellKnownAgentCard(agentCard);
        return endpoints.MapHttpA2A(handler, agentCard);
    }

    /// <summary>
    /// Maps A2A JSON-RPC communication endpoints to the specified path using a pre-configured request handler.
    /// </summary>
    /// <param name="endpoints">The <see cref="IEndpointRouteBuilder"/> to add the A2A endpoints to.</param>
    /// <param name="handler">Pre-configured <see cref="IA2ARequestHandler"/> for handling A2A requests.</param>
    /// <param name="path">The route group to use for A2A endpoints.</param>
    /// <returns>An <see cref="IEndpointConventionBuilder"/> for further endpoint configuration.</returns>
    public static IEndpointConventionBuilder MapA2A(this IEndpointRouteBuilder endpoints, IA2ARequestHandler handler, string path)
    {
        return A2ARouteBuilderExtensions.MapA2A(endpoints, handler, path);
    }

    /// <summary>
    /// Maps A2A communication endpoints including JSON-RPC, well-known agent card, and REST API
    /// to the specified path using a pre-configured request handler.
    /// </summary>
    /// <param name="endpoints">The <see cref="IEndpointRouteBuilder"/> to add the A2A endpoints to.</param>
    /// <param name="handler">Pre-configured <see cref="IA2ARequestHandler"/> for handling A2A requests.</param>
    /// <param name="path">The route group to use for A2A endpoints.</param>
    /// <param name="agentCard">Agent card describing the agent's capabilities for discovery.</param>
    /// <returns>An <see cref="IEndpointConventionBuilder"/> for further endpoint configuration.</returns>
    public static IEndpointConventionBuilder MapA2A(this IEndpointRouteBuilder endpoints, IA2ARequestHandler handler, string path, AgentCard agentCard)
    {
        A2ARouteBuilderExtensions.MapA2A(endpoints, handler, path);
        endpoints.MapWellKnownAgentCard(agentCard);
        return endpoints.MapHttpA2A(handler, agentCard);
    }
}
