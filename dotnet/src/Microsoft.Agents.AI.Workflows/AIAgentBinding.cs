// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows.Specialized;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// Represents the workflow binding details for an AI agent, including configuration options for event emission.
/// </summary>
/// <param name="Agent">The AI agent.</param>
/// <param name="EmitEvents">Specifies whether the agent should emit events. If null, the default behavior is applied.</param>
public record AIAgentBinding(AIAgent Agent, bool EmitEvents = false)
    : ExecutorBinding(Throw.IfNull(Agent).GetDescriptiveId(),
                           (_) => new(new AIAgentHostExecutor(Agent, EmitEvents)),
                           typeof(AIAgentHostExecutor),
                           Agent)
{
    /// <inheritdoc/>
    public override bool IsSharedInstance => false;

    /// <inheritdoc/>
    public override bool SupportsConcurrentSharedExecution => true;

    /// <inheritdoc/>
    public override bool SupportsResetting => false;
}
