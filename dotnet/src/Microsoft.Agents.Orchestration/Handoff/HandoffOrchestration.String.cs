// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI.Agents;

namespace Microsoft.Agents.Orchestration;

/// <summary>
/// An orchestration that passes the input message to the first agent, and
/// then the subsequent result to the next agent, etc...
/// </summary>
public sealed class HandoffOrchestration : HandoffOrchestration<string, string>
{
    /// <summary>
    /// Initializes a new instance of the <see cref="HandoffOrchestration"/> class.
    /// </summary>
    /// <param name="handoffs">Defines the handoff connections for each agent.</param>
    /// <param name="members">The agents to be orchestrated.</param>
    public HandoffOrchestration(OrchestrationHandoffs handoffs, params AIAgent[] members)
        : base(handoffs, members)
    {
    }
}
