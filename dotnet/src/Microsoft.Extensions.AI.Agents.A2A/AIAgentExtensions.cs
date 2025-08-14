// Copyright (c) Microsoft. All rights reserved.

using A2A;
using Microsoft.Extensions.AI.Agents.A2A.Internal;
using Microsoft.Extensions.AI.Agents.Runtime;
using Microsoft.Extensions.Logging;

namespace Microsoft.Extensions.AI.Agents.A2A;

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
    /// <param name="taskManager">Instance of <see cref="TaskManager"/> to configure for A2A messaging.</param>
    /// <param name="loggerFactory">The logger factory to use for creating <see cref="ILogger"/> instances.</param>
    public static void AttachA2AMessaging(
        this AIAgent agent,
        IActorClient actorClient,
        TaskManager taskManager,
        ILoggerFactory? loggerFactory = null)
    {
        taskManager ??= new();
        var a2aAgentWrapper = new A2AAgentWrapper(actorClient, agent, taskManager, loggerFactory);

        taskManager.OnAgentCardQuery += a2aAgentWrapper.GetAgentCardAsync;
        taskManager.OnMessageReceived += a2aAgentWrapper.ProcessMessageAsync;
    }
}
