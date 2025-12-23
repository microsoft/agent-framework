// Copyright (c) Microsoft. All rights reserved.

using System;
using A2A;
using A2A.AspNetCore;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Hosting;
using Microsoft.Agents.AI.Hosting.A2A;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Routing;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;

namespace Microsoft.AspNetCore.Builder;

/// <summary>
/// Provides extension methods for configuring A2A (Agent2Agent) communication in a host application builder.
/// </summary>
public static class MicrosoftAgentAIHostingA2AEndpointRouteBuilderExtensions
{
    /// <summary>
    /// Attaches A2A (Agent2Agent) communication capabilities via Message processing to the specified web application.
    /// </summary>
    /// <param name="endpoints">The <see cref="IEndpointRouteBuilder"/> to add the A2A endpoints to.</param>
    /// <param name="agentBuilder">The configuration builder for <see cref="AIAgent"/>.</param>
    /// <param name="path">The route group to use for A2A endpoints.</param>
    /// <returns>Configured <see cref="ITaskManager"/> for A2A integration.</returns>
    /// <remarks>
    /// This method can be used to access A2A agents that support the
    /// <see href="https://github.com/a2aproject/A2A/blob/main/docs/topics/agent-discovery.md#2-curated-registries-catalog-based-discovery">Curated Registries (Catalog-Based Discovery)</see>
    /// discovery mechanism.
    /// </remarks>
    public static IEndpointConventionBuilder MapA2A(this IEndpointRouteBuilder endpoints, IHostedAgentBuilder agentBuilder, string path)
        => endpoints.MapA2A(agentBuilder, path, _ => { });

    /// <summary>
    /// Attaches A2A (Agent2Agent) communication capabilities via Message processing to the specified web application.
    /// </summary>
    /// <param name="endpoints">The <see cref="IEndpointRouteBuilder"/> to add the A2A endpoints to.</param>
    /// <param name="agentName">The name of the agent to use for A2A protocol integration.</param>
    /// <param name="path">The route group to use for A2A endpoints.</param>
    /// <returns>Configured <see cref="ITaskManager"/> for A2A integration.</returns>
    public static IEndpointConventionBuilder MapA2A(this IEndpointRouteBuilder endpoints, string agentName, string path)
        => endpoints.MapA2A(agentName, path, _ => { });

    /// <summary>
    /// Attaches A2A (Agent2Agent) communication capabilities via Message processing to the specified web application.
    /// </summary>
    /// <param name="endpoints">The <see cref="IEndpointRouteBuilder"/> to add the A2A endpoints to.</param>
    /// <param name="agentBuilder">The configuration builder for <see cref="AIAgent"/>.</param>
    /// <param name="path">The route group to use for A2A endpoints.</param>
    /// <param name="configureTaskManager">The callback to configure <see cref="ITaskManager"/>.</param>
    /// <returns>Configured <see cref="ITaskManager"/> for A2A integration.</returns>
    /// <remarks>
    /// This method can be used to access A2A agents that support the
    /// <see href="https://github.com/a2aproject/A2A/blob/main/docs/topics/agent-discovery.md#2-curated-registries-catalog-based-discovery">Curated Registries (Catalog-Based Discovery)</see>
    /// discovery mechanism.
    /// </remarks>
    public static IEndpointConventionBuilder MapA2A(this IEndpointRouteBuilder endpoints, IHostedAgentBuilder agentBuilder, string path, Action<ITaskManager> configureTaskManager)
    {
        ArgumentNullException.ThrowIfNull(agentBuilder);
        return endpoints.MapA2A(agentBuilder.Name, path, configureTaskManager);
    }

    /// <summary>
    /// Attaches A2A (Agent2Agent) communication capabilities via Message processing to the specified web application.
    /// </summary>
    /// <param name="endpoints">The <see cref="IEndpointRouteBuilder"/> to add the A2A endpoints to.</param>
    /// <param name="agentName">The name of the agent to use for A2A protocol integration.</param>
    /// <param name="path">The route group to use for A2A endpoints.</param>
    /// <param name="configureTaskManager">The callback to configure <see cref="ITaskManager"/>.</param>
    /// <returns>Configured <see cref="ITaskManager"/> for A2A integration.</returns>
    public static IEndpointConventionBuilder MapA2A(this IEndpointRouteBuilder endpoints, string agentName, string path, Action<ITaskManager> configureTaskManager)
    {
        ArgumentNullException.ThrowIfNull(endpoints);
        var agent = endpoints.ServiceProvider.GetRequiredKeyedService<AIAgent>(agentName);
        return endpoints.MapA2A(agent, path, configureTaskManager);
    }

    /// <summary>
    /// Attaches A2A (Agent2Agent) communication capabilities via Message processing to the specified web application.
    /// </summary>
    /// <param name="endpoints">The <see cref="IEndpointRouteBuilder"/> to add the A2A endpoints to.</param>
    /// <param name="agentBuilder">The configuration builder for <see cref="AIAgent"/>.</param>
    /// <param name="path">The route group to use for A2A endpoints.</param>
    /// <param name="agentCard">Agent card info to return on query.</param>
    /// <returns>Configured <see cref="ITaskManager"/> for A2A integration.</returns>
    /// <remarks>
    /// This method can be used to access A2A agents that support the
    /// <see href="https://github.com/a2aproject/A2A/blob/main/docs/topics/agent-discovery.md#2-curated-registries-catalog-based-discovery">Curated Registries (Catalog-Based Discovery)</see>
    /// discovery mechanism.
    /// </remarks>
    public static IEndpointConventionBuilder MapA2A(this IEndpointRouteBuilder endpoints, IHostedAgentBuilder agentBuilder, string path, AgentCard agentCard)
        => endpoints.MapA2A(agentBuilder, path, agentCard, _ => { });

    /// <summary>
    /// Attaches A2A (Agent2Agent) communication capabilities via Message processing to the specified web application.
    /// </summary>
    /// <param name="endpoints">The <see cref="IEndpointRouteBuilder"/> to add the A2A endpoints to.</param>
    /// <param name="agentName">The name of the agent to use for A2A protocol integration.</param>
    /// <param name="path">The route group to use for A2A endpoints.</param>
    /// <param name="agentCard">Agent card info to return on query.</param>
    /// <returns>Configured <see cref="ITaskManager"/> for A2A integration.</returns>
    /// <remarks>
    /// This method can be used to access A2A agents that support the
    /// <see href="https://github.com/a2aproject/A2A/blob/main/docs/topics/agent-discovery.md#2-curated-registries-catalog-based-discovery">Curated Registries (Catalog-Based Discovery)</see>
    /// discovery mechanism.
    /// </remarks>
    public static IEndpointConventionBuilder MapA2A(this IEndpointRouteBuilder endpoints, string agentName, string path, AgentCard agentCard)
        => endpoints.MapA2A(agentName, path, agentCard, _ => { });

    /// <summary>
    /// Attaches A2A (Agent2Agent) communication capabilities via Message processing to the specified web application.
    /// </summary>
    /// <param name="endpoints">The <see cref="IEndpointRouteBuilder"/> to add the A2A endpoints to.</param>
    /// <param name="agentBuilder">The configuration builder for <see cref="AIAgent"/>.</param>
    /// <param name="path">The route group to use for A2A endpoints.</param>
    /// <param name="agentCard">Agent card info to return on query.</param>
    /// <param name="configureTaskManager">The callback to configure <see cref="ITaskManager"/>.</param>
    /// <returns>Configured <see cref="ITaskManager"/> for A2A integration.</returns>
    /// <remarks>
    /// This method can be used to access A2A agents that support the
    /// <see href="https://github.com/a2aproject/A2A/blob/main/docs/topics/agent-discovery.md#2-curated-registries-catalog-based-discovery">Curated Registries (Catalog-Based Discovery)</see>
    /// discovery mechanism.
    /// </remarks>
    public static IEndpointConventionBuilder MapA2A(this IEndpointRouteBuilder endpoints, IHostedAgentBuilder agentBuilder, string path, AgentCard agentCard, Action<ITaskManager> configureTaskManager)
    {
        ArgumentNullException.ThrowIfNull(agentBuilder);
        return endpoints.MapA2A(agentBuilder.Name, path, agentCard, configureTaskManager);
    }

    /// <summary>
    /// Attaches A2A (Agent2Agent) communication capabilities via Message processing to the specified web application.
    /// </summary>
    /// <param name="endpoints">The <see cref="IEndpointRouteBuilder"/> to add the A2A endpoints to.</param>
    /// <param name="agentName">The name of the agent to use for A2A protocol integration.</param>
    /// <param name="path">The route group to use for A2A endpoints.</param>
    /// <param name="agentCard">Agent card info to return on query.</param>
    /// <param name="configureTaskManager">The callback to configure <see cref="ITaskManager"/>.</param>
    /// <returns>Configured <see cref="ITaskManager"/> for A2A integration.</returns>
    /// <remarks>
    /// This method can be used to access A2A agents that support the
    /// <see href="https://github.com/a2aproject/A2A/blob/main/docs/topics/agent-discovery.md#2-curated-registries-catalog-based-discovery">Curated Registries (Catalog-Based Discovery)</see>
    /// discovery mechanism.
    /// </remarks>
    public static IEndpointConventionBuilder MapA2A(this IEndpointRouteBuilder endpoints, string agentName, string path, AgentCard agentCard, Action<ITaskManager> configureTaskManager)
    {
        ArgumentNullException.ThrowIfNull(endpoints);
        var agent = endpoints.ServiceProvider.GetRequiredKeyedService<AIAgent>(agentName);
        return endpoints.MapA2A(agent, path, agentCard, configureTaskManager);
    }

    /// <summary>
    /// Attaches A2A (Agent2Agent) communication capabilities via Message processing to the specified web application.
    /// </summary>
    /// <param name="endpoints">The <see cref="IEndpointRouteBuilder"/> to add the A2A endpoints to.</param>
    /// <param name="agent">The agent to use for A2A protocol integration.</param>
    /// <param name="path">The route group to use for A2A endpoints.</param>
    /// <returns>Configured <see cref="ITaskManager"/> for A2A integration.</returns>
    public static IEndpointConventionBuilder MapA2A(this IEndpointRouteBuilder endpoints, AIAgent agent, string path)
        => endpoints.MapA2A(agent, path, _ => { });

    /// <summary>
    /// Attaches A2A (Agent2Agent) communication capabilities via Message processing to the specified web application.
    /// </summary>
    /// <param name="endpoints">The <see cref="IEndpointRouteBuilder"/> to add the A2A endpoints to.</param>
    /// <param name="agent">The agent to use for A2A protocol integration.</param>
    /// <param name="path">The route group to use for A2A endpoints.</param>
    /// <param name="configureTaskManager">The callback to configure <see cref="ITaskManager"/>.</param>
    /// <returns>Configured <see cref="ITaskManager"/> for A2A integration.</returns>
    public static IEndpointConventionBuilder MapA2A(this IEndpointRouteBuilder endpoints, AIAgent agent, string path, Action<ITaskManager> configureTaskManager)
    {
        ArgumentNullException.ThrowIfNull(endpoints);
        ArgumentNullException.ThrowIfNull(agent);

        var loggerFactory = endpoints.ServiceProvider.GetRequiredService<ILoggerFactory>();
        var agentThreadStore = endpoints.ServiceProvider.GetKeyedService<AgentThreadStore>(agent.Name);
        var taskManager = agent.MapA2A(loggerFactory: loggerFactory, agentThreadStore: agentThreadStore);
        var endpointConventionBuilder = endpoints.MapA2A(taskManager, path);

        configureTaskManager(taskManager);
        return endpointConventionBuilder;
    }

    /// <summary>
    /// Attaches A2A (Agent2Agent) communication capabilities via Message processing to the specified web application.
    /// </summary>
    /// <param name="endpoints">The <see cref="IEndpointRouteBuilder"/> to add the A2A endpoints to.</param>
    /// <param name="agent">The agent to use for A2A protocol integration.</param>
    /// <param name="path">The route group to use for A2A endpoints.</param>
    /// <param name="agentCard">Agent card info to return on query.</param>
    /// <returns>Configured <see cref="ITaskManager"/> for A2A integration.</returns>
    /// <remarks>
    /// This method can be used to access A2A agents that support the
    /// <see href="https://github.com/a2aproject/A2A/blob/main/docs/topics/agent-discovery.md#2-curated-registries-catalog-based-discovery">Curated Registries (Catalog-Based Discovery)</see>
    /// discovery mechanism.
    /// </remarks>
    public static IEndpointConventionBuilder MapA2A(this IEndpointRouteBuilder endpoints, AIAgent agent, string path, AgentCard agentCard)
        => endpoints.MapA2A(agent, path, agentCard, _ => { });

    /// <summary>
    /// Attaches A2A (Agent2Agent) communication capabilities via Message processing to the specified web application.
    /// </summary>
    /// <param name="endpoints">The <see cref="IEndpointRouteBuilder"/> to add the A2A endpoints to.</param>
    /// <param name="agent">The agent to use for A2A protocol integration.</param>
    /// <param name="path">The route group to use for A2A endpoints.</param>
    /// <param name="agentCard">Agent card info to return on query.</param>
    /// <param name="configureTaskManager">The callback to configure <see cref="ITaskManager"/>.</param>
    /// <returns>Configured <see cref="ITaskManager"/> for A2A integration.</returns>
    /// <remarks>
    /// This method can be used to access A2A agents that support the
    /// <see href="https://github.com/a2aproject/A2A/blob/main/docs/topics/agent-discovery.md#2-curated-registries-catalog-based-discovery">Curated Registries (Catalog-Based Discovery)</see>
    /// discovery mechanism.
    /// </remarks>
    public static IEndpointConventionBuilder MapA2A(this IEndpointRouteBuilder endpoints, AIAgent agent, string path, AgentCard agentCard, Action<ITaskManager> configureTaskManager)
    {
        ArgumentNullException.ThrowIfNull(endpoints);
        ArgumentNullException.ThrowIfNull(agent);

        var loggerFactory = endpoints.ServiceProvider.GetRequiredService<ILoggerFactory>();
        var agentThreadStore = endpoints.ServiceProvider.GetKeyedService<AgentThreadStore>(agent.Name);
        var taskManager = agent.MapA2A(agentCard: agentCard, agentThreadStore: agentThreadStore, loggerFactory: loggerFactory);
        var endpointConventionBuilder = endpoints.MapA2A(taskManager, path);

        configureTaskManager(taskManager);

        return endpointConventionBuilder;
    }

    /// <summary>
    /// Maps HTTP A2A communication endpoints to the specified path using the provided TaskManager.
    /// TaskManager should be preconfigured before calling this method.
    /// </summary>
    /// <param name="endpoints">The <see cref="IEndpointRouteBuilder"/> to add the A2A endpoints to.</param>
    /// <param name="taskManager">Pre-configured A2A TaskManager to use for A2A endpoints handling.</param>
    /// <param name="path">The route group to use for A2A endpoints.</param>
    /// <returns>Configured <see cref="ITaskManager"/> for A2A integration.</returns>
    public static IEndpointConventionBuilder MapA2A(this IEndpointRouteBuilder endpoints, ITaskManager taskManager, string path)
    {
        // note: current SDK version registers multiple `.well-known/agent.json` handlers here.
        // it makes app return HTTP 500, but will be fixed once new A2A SDK is released.
        // see https://github.com/microsoft/agent-framework/issues/476 for details
        A2ARouteBuilderExtensions.MapA2A(endpoints, taskManager, path);
        return endpoints.MapHttpA2A(taskManager, path);
    }
}
