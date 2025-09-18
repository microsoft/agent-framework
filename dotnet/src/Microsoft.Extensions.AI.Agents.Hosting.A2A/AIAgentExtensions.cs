// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading.Tasks;
using A2A;
using Microsoft.Extensions.AI.Agents.Hosting.A2A.Internal;
using Microsoft.Extensions.AI.Agents.Runtime;
using Microsoft.Extensions.Logging;

namespace Microsoft.Extensions.AI.Agents.Hosting.A2A;

/// <summary>
/// Provides extension methods for attaching A2A (Agent-to-Agent) messaging capabilities to an <see cref="AIAgent"/>.
/// </summary>
public static class AIAgentExtensions
{
    /// <summary>
    /// Attaches A2A (Agent-to-Agent) messaging capabilities via Message processing to the specified <see cref="AIAgent"/>.
    /// </summary>
    /// <param name="agent">Agent to attach A2A messaging processing capabilities to.</param>
    /// <param name="actorClient">The actor client implementation to use.</param>
    /// <param name="taskManager">Instance of <see cref="TaskManager"/> to configure for A2A messaging. New instance will be created if not passed.</param>
    /// <param name="loggerFactory">The logger factory to use for creating <see cref="ILogger"/> instances.</param>
    /// <returns>The configured <see cref="TaskManager"/>.</returns>
    public static TaskManager AttachA2A(
        this AIAgent agent,
        IActorClient actorClient,
        TaskManager? taskManager = null,
        ILoggerFactory? loggerFactory = null)
    {
        ArgumentNullException.ThrowIfNull(agent, nameof(agent));
        ArgumentNullException.ThrowIfNull(actorClient, nameof(actorClient));

        taskManager ??= new();

        var a2aAgentWrapper = new A2AAgentWrapper(actorClient, agent, loggerFactory);

        taskManager.OnMessageReceived += a2aAgentWrapper.ProcessMessageAsync;

        return taskManager;
    }

    /// <summary>
    /// Attaches A2A (Agent-to-Agent) messaging capabilities via Message processing to the specified <see cref="AIAgent"/>.
    /// </summary>
    /// <param name="agent">Agent to attach A2A messaging processing capabilities to.</param>
    /// <param name="actorClient">The actor client implementation to use.</param>
    /// <param name="agentCard">The agent card to return on query.</param>
    /// <param name="taskManager">Instance of <see cref="TaskManager"/> to configure for A2A messaging. New instance will be created if not passed.</param>
    /// <param name="loggerFactory">The logger factory to use for creating <see cref="ILogger"/> instances.</param>
    /// <returns>The configured <see cref="TaskManager"/>.</returns>
    public static TaskManager AttachA2A(
        this AIAgent agent,
        IActorClient actorClient,
        AgentCard agentCard,
        TaskManager? taskManager = null,
        ILoggerFactory? loggerFactory = null)
    {
        taskManager = agent.AttachA2A(actorClient, taskManager, loggerFactory);

        taskManager.OnAgentCardQuery += (context, query) =>
        {
            // A2A SDK assigns the url on its own
            // we can help user if they did not set Url explicitly.
            agentCard.Url ??= context;

            return Task.FromResult(agentCard);
        };
        return taskManager;
    }
}
