// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
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
public class ChatHistoryCompactionPipeline : IChatReducer
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
        this._strategies = Throw.IfNull(strategies).ToArray();
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
        List<ChatMessage> messageList = messages.ToList(); // %%% HAXX
        await this.CompactAsync(messageList, cancellationToken).ConfigureAwait(false);
        return messageList;
    }

    /// <summary>
    /// Run all strategies in sequence against the given messages.
    /// </summary>
    /// <param name="messages">The mutable message list to compact.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests.</param>
    /// <returns>A <see cref="CompactionPipelineResult"/> with aggregate and per-strategy metrics.</returns>
    public async ValueTask<CompactionPipelineResult> CompactAsync( // %%% SCOPE
        IList<ChatMessage> messages,
        CancellationToken cancellationToken = default)
    {
        Throw.IfNull(messages);

        IReadOnlyList<ChatMessage> readOnlyMessages = messages as IReadOnlyList<ChatMessage> ?? [.. messages]; // %%% TYPE CONSISTENCY
        CompactionMetric overallBefore = this._metricsCalculator.Calculate(readOnlyMessages);

        List<CompactionResult> results = new(this._strategies.Length);

        foreach (ChatHistoryCompactionStrategy strategy in this._strategies)
        {
            CompactionResult result = await strategy.CompactAsync(messages, this._metricsCalculator, cancellationToken).ConfigureAwait(false);
            results.Add(result);
        }

        readOnlyMessages = messages as IReadOnlyList<ChatMessage> ?? [.. messages];
        CompactionMetric overallAfter = this._metricsCalculator.Calculate(readOnlyMessages);

        return new(overallBefore, overallAfter, results);
    }
}
