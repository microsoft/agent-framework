// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Compaction;

/// <summary>
/// Reports the outcome of a single <see cref="ChatHistoryCompactionStrategy"/> execution.
/// </summary>
public sealed class CompactionResult
{
    /// <summary>
    /// Initializes a new instance of the <see cref="CompactionResult"/> class.
    /// </summary>
    /// <param name="strategyName">The name of the strategy that produced this result.</param>
    /// <param name="applied">Whether the strategy modified the message list.</param>
    /// <param name="before">Metrics before the strategy ran.</param>
    /// <param name="after">Metrics after the strategy ran.</param>
    public CompactionResult(string strategyName, bool applied, CompactionMetric before, CompactionMetric after)
    {
        this.StrategyName = Throw.IfNullOrWhitespace(strategyName);
        this.Applied = applied;
        this.Before = Throw.IfNull(before);
        this.After = Throw.IfNull(after);
    }

    /// <summary>
    /// Gets the name of the strategy that produced this result.
    /// </summary>
    public string StrategyName { get; }

    /// <summary>
    /// Gets a value indicating whether the strategy modified the message list.
    /// </summary>
    public bool Applied { get; }

    /// <summary>
    /// Gets the conversation metrics before the strategy executed.
    /// </summary>
    public CompactionMetric Before { get; }

    /// <summary>
    /// Gets the conversation metrics after the strategy executed.
    /// </summary>
    public CompactionMetric After { get; }

    /// <summary>
    /// Creates a <see cref="CompactionResult"/> representing a skipped strategy.
    /// </summary>
    /// <param name="strategyName">The name of the skipped strategy.</param>
    /// <param name="metrics">The current conversation metrics.</param>
    /// <returns>A result indicating no compaction was applied.</returns>
    internal static CompactionResult Skipped(string strategyName, CompactionMetric metrics)
        => new(strategyName, applied: false, metrics, metrics);
}
