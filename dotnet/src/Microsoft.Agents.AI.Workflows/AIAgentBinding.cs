// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows.Specialized;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// Represents the workflow binding details for an AI agent, including configuration options for event emission.
/// </summary>
public record AIAgentBinding : ExecutorBinding
{
    private static string GetEffectiveId(AIAgent agent, string? descriptiveId)
        => descriptiveId ?? Throw.IfNull(agent).GetDescriptiveId();

    /// <summary>
    /// The AI agent.
    /// </summary>
    public AIAgent Agent { get; }

    /// <summary>
    /// Specifies whether the agent should emit events.
    /// </summary>
    public bool EmitEvents { get; }

    /// <summary>
    /// The custom descriptive ID for the executor, if provided.
    /// </summary>
    public string? DescriptiveId { get; }

    /// <summary>
    /// Initializes a new instance of the <see cref="AIAgentBinding"/> class.
    /// </summary>
    /// <param name="agent">The AI agent.</param>
    /// <param name="emitEvents">Specifies whether the agent should emit events.</param>
    /// <param name="descriptiveId">An optional custom descriptive ID for the executor.</param>
    public AIAgentBinding(AIAgent agent, bool emitEvents = false, string? descriptiveId = null)
        : base(GetEffectiveId(agent, descriptiveId),
               (_) => new(new AIAgentHostExecutor(agent, GetEffectiveId(agent, descriptiveId), emitEvents)),
               typeof(AIAgentHostExecutor),
               agent)
    {
        this.Agent = agent;
        this.EmitEvents = emitEvents;
        this.DescriptiveId = descriptiveId;
    }

    /// <inheritdoc/>
    public override bool IsSharedInstance => false;

    /// <inheritdoc/>
    public override bool SupportsConcurrentSharedExecution => true;

    /// <inheritdoc/>
    public override bool SupportsResetting => false;
}
