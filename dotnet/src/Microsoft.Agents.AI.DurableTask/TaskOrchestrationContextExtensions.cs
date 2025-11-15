// Copyright (c) Microsoft. All rights reserved.

using System.ComponentModel;
using Microsoft.DurableTask;

namespace Microsoft.Agents.AI.DurableTask;

/// <summary>
/// Agent-related extension methods for the <see cref="TaskOrchestrationContext"/> class.
/// </summary>
[EditorBrowsable(EditorBrowsableState.Never)]
public static class TaskOrchestrationContextExtensions
{
    /// <summary>
    /// Gets a <see cref="DurableAIAgent"/> for interacting with hosted agents within an orchestration.
    /// </summary>
    /// <param name="context">The orchestration context.</param>
    /// <param name="agentName">The name of the agent.</param>
    /// <exception cref="ArgumentException">Thrown when <paramref name="agentName"/> is null or empty.</exception>
    /// <returns>A <see cref="DurableAIAgent"/> that can be used to interact with the agent.</returns>
    public static DurableAIAgent GetAgent(
        this TaskOrchestrationContext context,
        string agentName)
    {
        ArgumentException.ThrowIfNullOrEmpty(agentName);
        return new DurableAIAgent(context, agentName);
    }

    /// <summary>
    /// Generates an <see cref="AgentSessionId"/> for an agent.
    /// </summary>
    /// <remarks>
    /// This method is deterministic and safe for use in an orchestration context.
    /// </remarks>
    /// <param name="context">The orchestration context.</param>
    /// <param name="agentName">The name of the agent.</param>
    /// <exception cref="ArgumentException">Thrown when <paramref name="agentName"/> is null or empty.</exception>
    /// <returns>The generated agent session ID.</returns>
    internal static AgentSessionId NewAgentSessionId(
        this TaskOrchestrationContext context,
        string agentName)
    {
        ArgumentException.ThrowIfNullOrEmpty(agentName);

        return new AgentSessionId(agentName, context.NewGuid().ToString("N"));
    }
}
