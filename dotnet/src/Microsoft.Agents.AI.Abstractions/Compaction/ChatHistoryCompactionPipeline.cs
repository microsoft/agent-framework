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
/// Executes a chain of <see cref="ChatHistoryCompactionStrategy"/> instances in order
/// against a mutable message list.
/// </summary>
/// <remarks>
/// <para>
/// Each strategy's trigger is evaluated against the metrics <em>as they stand after prior strategies</em>,
/// so earlier strategies can bring the conversation within thresholds that cause later strategies to skip.
/// </para>
/// <para>
/// The pipeline is fully standalone — it can be used without any agent, session, or context provider.
/// It also implements <see cref="IChatReducer"/> so it can be used directly anywhere a reducer is
/// accepted (e.g., <see cref="InMemoryChatHistoryProviderOptions.ChatReducer"/>).
/// </para>
/// </remarks>
public partial class ChatHistoryCompactionPipeline : IChatReducer
{
    private readonly ChatHistoryCompactionStrategy[] _strategies;
    private readonly IChatHistoryMetricsCalculator _metricsCalculator;

    /// <summary>
    /// Initializes a new instance of the <see cref="ChatHistoryCompactionPipeline"/> class.
    /// </summary>
    /// <param name="strategies">The ordered list of compaction strategies to execute.</param>
    /// <remarks>
    /// By default, <see cref="DefaultChatHistoryMetricsCalculator"/> is used.
    /// </remarks>
    public ChatHistoryCompactionPipeline(
        params IEnumerable<ChatHistoryCompactionStrategy> strategies)
        : this(metricsCalculator: null, strategies) { }

    /// <summary>
    /// Initializes a new instance of the <see cref="ChatHistoryCompactionPipeline"/> class.
    /// </summary>
    /// <param name="metricsCalculator">
    /// An optional metrics calculator. When <see langword="null"/>, a
    /// <see cref="DefaultChatHistoryMetricsCalculator"/> is used.
    /// </param>
    /// <param name="strategies">The ordered list of compaction strategies to execute.</param>
    public ChatHistoryCompactionPipeline(
        IChatHistoryMetricsCalculator? metricsCalculator,
        params IEnumerable<ChatHistoryCompactionStrategy> strategies)
    {
        this._strategies = [.. Throw.IfNull(strategies)];
        this._metricsCalculator = metricsCalculator ?? DefaultChatHistoryMetricsCalculator.Instance;
    }

    /// <summary>
    /// Reduces the given messages by running all strategies in sequence.
    /// </summary>
    /// <param name="messages">The messages to reduce.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests.</param>
    /// <returns>The reduced set of messages.</returns>
    public virtual async Task<IEnumerable<ChatMessage>> ReduceAsync(
        IEnumerable<ChatMessage> messages,
        CancellationToken cancellationToken = default)
    {
        List<ChatMessage> messageBuffer = messages is List<ChatMessage> messageList ? messageList : [.. messages];
        await this.CompactAsync(messageBuffer, cancellationToken).ConfigureAwait(false);
        return messageBuffer;
    }

    /// <summary>
    /// Run all strategies in sequence against the given messages.
    /// </summary>
    /// <param name="messages">The mutable message list to compact.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests.</param>
    /// <returns>A <see cref="CompactionPipelineResult"/> with aggregate and per-strategy metrics.</returns>
    public async ValueTask<CompactionPipelineResult> CompactAsync(
        List<ChatMessage> messages,
        CancellationToken cancellationToken = default)
    {
        Throw.IfNull(messages);

        ChatHistoryMetric overallBefore = this._metricsCalculator.Calculate(messages);

        Debug.WriteLine($"COMPACTION: BEGIN x{overallBefore.MessageCount}/#{overallBefore.UserTurnCount} ({overallBefore.TokenCount} tokens)");

        List<CompactionResult> compactionResults = new(this._strategies.Length);

        Stopwatch timer = new();
        TimeSpan startTime = TimeSpan.Zero;
        ChatHistoryMetric overallAfter = overallBefore;
        ChatHistoryMetric currentBefore = overallBefore;
        foreach (ChatHistoryCompactionStrategy strategy in this._strategies)
        {
            // %%% VERBOSE - Debug.WriteLine($"COMPACTION: {strategy.Name} START");
            timer.Start();
            ChatHistoryCompactionStrategy.s_currentMetrics.Value = currentBefore;
            CompactionResult strategyResult = await strategy.CompactAsync(messages, this._metricsCalculator, cancellationToken).ConfigureAwait(false);
            timer.Stop();
            TimeSpan elapsedTime = timer.Elapsed - startTime;
            // %%% VERBOSE - Debug.WriteLine($"COMPACTION: {strategy.Name} FINISH [{elapsedTime}]");
            compactionResults.Add(strategyResult);
            overallAfter = currentBefore = strategyResult.After;
        }

        Debug.WriteLineIf(overallBefore.TokenCount != overallAfter.TokenCount, $"COMPACTION: TOTAL [{timer.Elapsed}] {overallBefore.TokenCount} => {overallAfter.TokenCount} tokens");

        return new(overallBefore, overallAfter, compactionResults);
    }
}
