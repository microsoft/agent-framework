// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics.CodeAnalysis;
using A2A;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI.Hosting.A2A;

/// <summary>
/// Provides extension methods for attaching A2A (Agent2Agent) messaging capabilities to an <see cref="AIAgent"/>.
/// </summary>
[Experimental(DiagnosticIds.Experiments.AIResponseContinuations)]
public static class AIAgentExtensions
{
    /// <summary>
    /// Creates an <see cref="IAgentHandler"/> that bridges the specified <see cref="AIAgent"/> to
    /// the A2A (Agent2Agent) protocol.
    /// </summary>
    /// <param name="agent">Agent to attach A2A messaging processing capabilities to.</param>
    /// <param name="agentSessionStore">The store to store session contents and metadata.</param>
    /// <param name="runMode">Controls the response behavior of the agent run.</param>
    /// <returns>An <see cref="IAgentHandler"/> that handles A2A message execution and cancellation.</returns>
    public static IAgentHandler MapA2A(
        this AIAgent agent,
        AgentSessionStore? agentSessionStore = null,
        AgentRunMode? runMode = null)
    {
        ArgumentNullException.ThrowIfNull(agent);
        ArgumentNullException.ThrowIfNull(agent.Name);

        runMode ??= AgentRunMode.DisallowBackground;

        var hostAgent = new AIHostAgent(
            innerAgent: agent,
            sessionStore: agentSessionStore ?? new InMemoryAgentSessionStore());

        return new A2AAgentHandler(hostAgent, runMode);
    }
}
