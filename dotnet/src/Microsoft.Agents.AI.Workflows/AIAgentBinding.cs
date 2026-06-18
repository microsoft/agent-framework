// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows.Specialized;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// Represents the workflow binding details for an AI agent, including configuration options for agent hosting behaviour.
/// </summary>
/// <param name="Agent">The AI agent.</param>
/// <param name="Options">The options for configuring the AI agent host.
/// </param>
public record AIAgentBinding(AIAgent Agent, AIAgentHostOptions? Options = null)
    : ExecutorBinding(Throw.IfNull(Agent).GetDescriptiveId(),
                           (_) => new(new AIAgentHostExecutor(Agent, Options ?? new())),
                           typeof(AIAgentHostExecutor),
                           Agent)
{
    /// <summary>
    /// Initializes a new instance of the AIAgentBinding class, associating it with the specified AI agent and
    /// optionally enabling event emission.
    /// </summary>
    /// <param name="agent">The AI agent.</param>
    /// <param name="emitEvents">Specifies whether the agent should emit events. If null, the default behavior is applied.</param>
    public AIAgentBinding(AIAgent agent, bool emitEvents = false)
        : this(agent, new AIAgentHostOptions { EmitAgentUpdateEvents = emitEvents })
    { }

    /// <inheritdoc/>
    public override bool IsSharedInstance => false;

    /// <inheritdoc/>
    public override bool SupportsConcurrentSharedExecution => true;

    /// <inheritdoc/>
    public override bool SupportsResetting => false;
}
