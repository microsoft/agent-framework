// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.Orchestration.Handoff;

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
    public HandoffOrchestration(OrchestrationHandoffs handoffs)
        : base(handoffs)
    {
    }
}
