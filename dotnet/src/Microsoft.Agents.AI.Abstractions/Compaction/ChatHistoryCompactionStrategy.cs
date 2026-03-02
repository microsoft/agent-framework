// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.Linq;
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
/// <item><description>Before/after <see cref="CompactionMetric"/> reporting via <see cref="CompactionResult"/>.</description></item>
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
    private static readonly AsyncLocal<CompactionMetric> s_currentMetrics = new();

    /// <summary>
    /// Initializes a new instance of the <see cref="ChatHistoryCompactionStrategy"/> class.
    /// </summary>
    /// <param name="reducer">The <see cref="IChatReducer"/> that performs the actual message compaction.</param>
    protected ChatHistoryCompactionStrategy(IChatReducer reducer)
    {
        this.Reducer = Throw.IfNull(reducer);
    }

    /// <summary>
    /// Exposes the current <see cref="CompactionMetric"/> for the executing strategy, allowing <see cref="Reducer"/> to make informed decisions.
    /// </summary>
    protected static CompactionMetric CurrentMetrics => s_currentMetrics.Value ?? throw new InvalidOperationException($"No active {nameof(ChatHistoryCompactionStrategy)}.");

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
    public abstract bool ShouldCompact(CompactionMetric metrics);

    /// <summary>
    /// Execute this strategy: check the trigger, delegate to the <see cref="IChatReducer"/>, and report metrics.
    /// </summary>
    /// <param name="messages">The mutable message list to compact.</param>
    /// <param name="metricsCalculator">The calculator to use for metric snapshots.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests.</param>
    /// <returns>A <see cref="CompactionResult"/> reporting the outcome.</returns>
    public async ValueTask<CompactionResult> CompactAsync(
        IList<ChatMessage> messages,
        IChatHistoryMetricsCalculator metricsCalculator,
        CancellationToken cancellationToken = default)
    {
        messages = Throw.IfNull(messages);
        Throw.IfNull(metricsCalculator);

        List<ChatMessage>? messageList = messages as List<ChatMessage>;
        ReadOnlyCollection<ChatMessage> snapshot = messageList is not null ? messageList.AsReadOnly() : new(messages);
        CompactionMetric before = metricsCalculator.Calculate(snapshot);
        s_currentMetrics.Value = before;
        if (!this.ShouldCompact(before))
        {
            return CompactionResult.Skipped(this.Name, before);
        }

        ChatMessage[] reduced = (await this.Reducer.ReduceAsync(snapshot, cancellationToken).ConfigureAwait(false)).ToArray();

        bool modified = reduced.Length != snapshot.Count;
        if (modified)
        {
            messages.Clear();
            foreach (ChatMessage message in reduced)
            {
                messages.Add(message);
            }
        }

        CompactionMetric after = modified
            ? metricsCalculator.Calculate(reduced)
            : before;

        return new(this.Name, applied: modified, before, after);
    }
}
