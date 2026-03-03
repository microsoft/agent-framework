// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Compaction;

/// <summary>
/// A named compaction strategy with an optional conditional trigger that delegates
/// actual message reduction to an <see cref="IChatReducer"/>.
/// </summary>
/// <remarks>
/// <para>
/// Each strategy wraps an <see cref="IChatReducer"/> that performs the actual compaction,
/// while the strategy adds:
/// <list type="bullet">
/// <item><description>A conditional trigger via <see cref="ShouldCompact"/> that decides whether compaction runs.</description></item>
/// <item><description>Before/after <see cref="ChatHistoryMetric"/> reporting via <see cref="CompactionResult"/>.</description></item>
/// </list>
/// </para>
/// <para>
/// For simple cases, construct a <see cref="ChatHistoryCompactionStrategy"/> directly with any
/// <see cref="IChatReducer"/>. For custom trigger logic, subclass and override <see cref="ShouldCompact"/>.
/// </para>
/// <para>
/// Reducers <b>must</b> preserve atomic message groups: an assistant message containing
/// tool calls and its corresponding tool result messages must be kept or removed together.
/// Use <see cref="DefaultChatHistoryMetricsCalculator"/> to identify these groups when authoring custom reducers.
/// </para>
/// </remarks>
public abstract class ChatHistoryCompactionStrategy
{
    internal static readonly AsyncLocal<ChatHistoryMetric> s_currentMetrics = new();

    /// <summary>
    /// Initializes a new instance of the <see cref="ChatHistoryCompactionStrategy"/> class.
    /// </summary>
    /// <param name="reducer">The <see cref="IChatReducer"/> that performs the actual message compaction.</param>
    protected ChatHistoryCompactionStrategy(IChatReducer reducer)
    {
        this.Reducer = Throw.IfNull(reducer);
    }

    /// <summary>
    /// Exposes the current <see cref="ChatHistoryMetric"/> for the executing strategy, allowing <see cref="Reducer"/> to make informed decisions.
    /// </summary>
    protected static ChatHistoryMetric CurrentMetrics => s_currentMetrics.Value ?? throw new InvalidOperationException($"No active {nameof(ChatHistoryCompactionStrategy)}.");

    /// <summary>
    /// Gets the <see cref="IChatReducer"/> that performs the actual message compaction.
    /// </summary>
    public IChatReducer Reducer { get; }

    /// <summary>
    /// Gets the display name of this strategy, used for logging and diagnostics.
    /// </summary>
    /// <remarks>
    /// The default implementation returns the type name of the underlying <see cref="IChatReducer"/>.
    /// </remarks>
    public virtual string Name => this.Reducer.GetType().Name;

    /// <summary>
    /// Evaluates whether this strategy should execute given the current conversation metrics.
    /// </summary>
    /// <param name="metrics">The current conversation metrics.</param>
    /// <returns>
    /// <see langword="true"/> to proceed with compaction; <see langword="false"/> to skip.
    /// </returns>
    protected abstract bool ShouldCompact(ChatHistoryMetric metrics);

    /// <summary>
    /// Execute this strategy: check the trigger, delegate to the <see cref="IChatReducer"/>, and report metrics.
    /// </summary>
    /// <param name="history">The mutable message list to compact.</param>
    /// <param name="metricsCalculator">The calculator to use for metric snapshots.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests.</param>
    /// <returns>A <see cref="CompactionResult"/> reporting the outcome.</returns>
    internal async ValueTask<CompactionResult> CompactAsync(
        List<ChatMessage> history,
        IChatHistoryMetricsCalculator metricsCalculator,
        CancellationToken cancellationToken = default)
    {
        Throw.IfNull(metricsCalculator);
        Throw.IfNull(history);

        ChatHistoryMetric beforeMetrics = CurrentMetrics;
        if (!this.ShouldCompact(beforeMetrics))
        {
            // %%% VERBOSE - Debug.WriteLine($"COMPACTION: {this.Name} - Skipped");
            return CompactionResult.Skipped(this.Name, beforeMetrics);
        }

        Debug.WriteLine($"COMPACTION: {this.Name} - Reducing");

        IEnumerable<ChatMessage> reducerResult = await this.Reducer.ReduceAsync(history, cancellationToken).ConfigureAwait(false);

        // Ensure we have a concrete collection to avoid multiple enumerations of the reducer result, which could be costly if it's an iterator.
        ChatMessage[] reducedCopy = [.. reducerResult];

        bool modified = reducedCopy.Length != history.Count;
        if (modified)
        {
            history.Clear();
            history.AddRange(reducedCopy);
        }

        ChatHistoryMetric afterMetrics = modified
            ? metricsCalculator.Calculate(reducedCopy)
            : beforeMetrics;

        Debug.WriteLine($"COMPACTION: {this.Name} - Tokens {beforeMetrics.TokenCount} => {afterMetrics.TokenCount}");

        return new(this.Name, applied: modified, beforeMetrics, afterMetrics);
    }
}
