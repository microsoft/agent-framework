// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading.Tasks;
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

    private static (string effectiveId, Func<string, ValueTask<Executor>> factory) CreateBindingArgs(AIAgent agent, bool emitEvents, string? descriptiveId)
    {
        string effectiveId = GetEffectiveId(agent, descriptiveId);
        return (effectiveId, (_) => new(new AIAgentHostExecutor(agent, effectiveId, emitEvents)));
    }

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
        : this(agent, emitEvents, descriptiveId, CreateBindingArgs(agent, emitEvents, descriptiveId))
    {
    }

    private AIAgentBinding(AIAgent agent, bool emitEvents, string? descriptiveId, (string effectiveId, Func<string, ValueTask<Executor>> factory) args)
        : base(args.effectiveId, args.factory, typeof(AIAgentHostExecutor), agent)
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
