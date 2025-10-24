// Copyright (c) Microsoft. All rights reserved.

using A2A;
using A2A.AspNetCore;
using Microsoft.Agents.AI;
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
    /// <param name="agentName">The name of the agent to use for A2A protocol integration.</param>
    /// <param name="path">The route group to use for A2A endpoints.</param>
    /// <returns>Configured <see cref="ITaskManager"/> for A2A integration.</returns>
    public static ITaskManager MapA2A(this IEndpointRouteBuilder endpoints, string agentName, string path)
    {
        var agent = endpoints.ServiceProvider.GetRequiredKeyedService<AIAgent>(agentName);
        return endpoints.MapA2A(agent, path);
    }

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
    public static ITaskManager MapA2A(this IEndpointRouteBuilder endpoints, string agentName, string path, AgentCard agentCard)
    {
        var agent = endpoints.ServiceProvider.GetRequiredKeyedService<AIAgent>(agentName);
        return endpoints.MapA2A(agent, path, agentCard);
    }

    /// <summary>
    /// Attaches A2A (Agent2Agent) communication capabilities via Message processing to the specified web application.
    /// </summary>
    /// <param name="endpoints">The <see cref="IEndpointRouteBuilder"/> to add the A2A endpoints to.</param>
    /// <param name="agent">The agent to use for A2A protocol integration.</param>
    /// <param name="path">The route group to use for A2A endpoints.</param>
    /// <returns>Configured <see cref="ITaskManager"/> for A2A integration.</returns>
    public static ITaskManager MapA2A(this IEndpointRouteBuilder endpoints, AIAgent agent, string path)
    {
        var loggerFactory = endpoints.ServiceProvider.GetRequiredService<ILoggerFactory>();
        var taskManager = agent.MapA2A(loggerFactory: loggerFactory);
        return endpoints.MapA2A(taskManager, path);
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
    public static ITaskManager MapA2A(this IEndpointRouteBuilder endpoints, AIAgent agent, string path, AgentCard agentCard)
    {
        var loggerFactory = endpoints.ServiceProvider.GetRequiredService<ILoggerFactory>();
        var taskManager = agent.MapA2A(agentCard: agentCard, loggerFactory: loggerFactory);
        return endpoints.MapA2A(taskManager, path);
    }

    /// <summary>
    /// Maps HTTP A2A communication endpoints to the specified path using the provided TaskManager.
    /// TaskManager should be preconfigured before calling this method.
    /// </summary>
    /// <param name="endpoints">The <see cref="IEndpointRouteBuilder"/> to add the A2A endpoints to.</param>
    /// <param name="taskManager">Pre-configured A2A TaskManager to use for A2A endpoints handling.</param>
    /// <param name="path">The route group to use for A2A endpoints.</param>
    /// <returns>Configured <see cref="ITaskManager"/> for A2A integration.</returns>
    public static ITaskManager MapA2A(this IEndpointRouteBuilder endpoints, TaskManager taskManager, string path)
    {
        // note: current SDK version registers multiple `.well-known/agent.json` handlers here.
        // it makes app return HTTP 500, but will be fixed once new A2A SDK is released.
        // see https://github.com/microsoft/agent-framework/issues/476 for details
        A2ARouteBuilderExtensions.MapA2A(endpoints, taskManager, path);
        endpoints.MapHttpA2A(taskManager, path);

        return taskManager;
    }
}
