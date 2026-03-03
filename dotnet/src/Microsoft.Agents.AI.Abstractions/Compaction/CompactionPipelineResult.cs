// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Compaction;

/// <summary>
/// Reports the aggregate outcome of a <see cref="ChatHistoryCompactionPipeline"/> execution.
/// </summary>
public sealed class CompactionPipelineResult
{
    /// <summary>
    /// Initializes a new instance of the <see cref="CompactionPipelineResult"/> class.
    /// </summary>
    /// <param name="before">Metrics of the conversation before any strategy ran.</param>
    /// <param name="after">Metrics of the conversation after all strategies ran.</param>
    /// <param name="strategyResults">Per-strategy results in execution order.</param>
    internal CompactionPipelineResult(
        ChatHistoryMetric before,
        ChatHistoryMetric after,
        IReadOnlyList<CompactionResult> strategyResults)
    {
        this.Before = Throw.IfNull(before);
        this.After = Throw.IfNull(after);
        this.StrategyResults = Throw.IfNull(strategyResults);
    }

    /// <summary>
    /// Gets the conversation metrics before any compaction strategy ran.
    /// </summary>
    public ChatHistoryMetric Before { get; }

    /// <summary>
    /// Gets the conversation metrics after all compaction strategies ran.
    /// </summary>
    public ChatHistoryMetric After { get; }

    /// <summary>
    /// Gets the per-strategy results in execution order.
    /// </summary>
    public IReadOnlyList<CompactionResult> StrategyResults { get; }

    /// <summary>
    /// Gets a value indicating whether any strategy modified the message list.
    /// </summary>
    public bool AnyApplied => this.StrategyResults.Any(r => r.Applied);
}
