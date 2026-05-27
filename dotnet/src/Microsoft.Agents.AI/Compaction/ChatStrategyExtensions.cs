// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Compaction;

/// <summary>
/// Provides extension methods for <see cref="CompactionStrategy"/>.
/// </summary>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public static class ChatStrategyExtensions
{
    /// <summary>
    /// Returns an <see cref="IChatReducer"/> that applies this <see cref="CompactionStrategy"/> to reduce a list of messages.
    /// </summary>
    /// <param name="strategy">The compaction strategy to wrap as an <see cref="IChatReducer"/>.</param>
    /// <returns>
    /// An <see cref="IChatReducer"/> that, on each call to <see cref="IChatReducer.ReduceAsync"/>, builds a
    /// <see cref="CompactionMessageIndex"/> from the supplied messages and applies the strategy's compaction logic,
    /// returning the resulting included messages.
    /// </returns>
    /// <remarks>
    /// This allows any <see cref="CompactionStrategy"/> to be used wherever an <see cref="IChatReducer"/> is expected,
    /// bridging the compaction pipeline into systems bound to the <c>Microsoft.Extensions.AI</c> <see cref="IChatReducer"/> contract.
    /// </remarks>
    public static IChatReducer AsChatReducer(this CompactionStrategy strategy)
    {
        Throw.IfNull(strategy);

        return new CompactionStrategyChatReducer(strategy);
    }

    /// <summary>
    /// An <see cref="IChatReducer"/> adapter that delegates to a <see cref="CompactionStrategy"/>.
    /// </summary>
    private sealed class CompactionStrategyChatReducer : IChatReducer
    {
        private readonly CompactionStrategy _strategy;

        public CompactionStrategyChatReducer(CompactionStrategy strategy)
        {
            this._strategy = strategy;
        }

        /// <inheritdoc/>
        public async Task<IEnumerable<ChatMessage>> ReduceAsync(IEnumerable<ChatMessage> messages, CancellationToken cancellationToken = default)
        {
            CompactionMessageIndex index = CompactionMessageIndex.Create([.. messages]);
            await this._strategy.CompactAsync(index, cancellationToken: cancellationToken).ConfigureAwait(false);
            return index.GetIncludedMessages();
        }
    }
}
