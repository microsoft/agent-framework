// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Compaction;

/// <summary>
/// A compaction strategy that keeps only the most recent user turns and their
/// associated response groups, removing older turns to bound conversation length.
/// </summary>
/// <remarks>
/// <para>
/// This strategy always preserves system messages. It identifies user turns in the
/// conversation and keeps the last <c>maxTurns</c> turns along with all response groups
/// (assistant replies, tool call groups) that follow each kept turn.
/// </para>
/// <para>
/// The trigger condition fires only when the number of user turns exceeds <c>maxTurns</c>.
/// </para>
/// <para>
/// This strategy is more predictable than token-based truncation for bounding conversation
/// length, since it operates on logical turn boundaries rather than estimated token counts.
/// </para>
/// </remarks>
public class SlidingWindowCompactionStrategy : ChatHistoryCompactionStrategy
{
    private readonly int _maxTurns;

    /// <summary>
    /// Initializes a new instance of the <see cref="SlidingWindowCompactionStrategy"/> class.
    /// </summary>
    /// <param name="maxTurns">
    /// The maximum number of user turns to keep. Older turns and their associated responses are removed.
    /// </param>
    public SlidingWindowCompactionStrategy(int maxTurns)
        : base(new SlidingWindowReducer(maxTurns))
    {
        this._maxTurns = maxTurns;
    }

    /// <inheritdoc/>
    protected override bool ShouldCompact(ChatHistoryMetric metrics) =>
        metrics.UserTurnCount > this._maxTurns;

    /// <summary>
    /// An <see cref="IChatReducer"/> that keeps system messages and the last N user turns
    /// with all their associated response groups.
    /// </summary>
    private sealed class SlidingWindowReducer(int maxTurns) : IChatReducer
    {
        public Task<IEnumerable<ChatMessage>> ReduceAsync(
            IEnumerable<ChatMessage> messages,
            CancellationToken cancellationToken = default)
        {
            IReadOnlyList<ChatMessage> messageList = [.. messages]; // %%% PERFORMANCE
            IReadOnlyList<ChatMessageGroup> groups = CurrentMetrics.Groups;

            // Find the group-list indices where each user turn starts
            int[] turnGroupIndices =
                [.. CurrentMetrics.Groups
                    .Select((group, index) => (group, index))
                    .Where(t => t.group.Kind == ChatMessageGroupKind.UserTurn)
                    .Select(t => t.index)];

            // Keep the last maxTurns user turns and everything after the first kept turn
            int firstKeptTurnIndex = turnGroupIndices.Length - maxTurns;
            int firstKeptGroupIndex = turnGroupIndices[firstKeptTurnIndex];

            List<ChatMessage> result = new(messageList.Count); // %%% PERFORMANCE
            for (int gi = 0; gi < groups.Count; gi++)
            {
                ChatMessageGroup group = groups[gi];

                // Always keep system messages; keep groups at or after the window start
                if (group.Kind == ChatMessageGroupKind.System || gi >= firstKeptGroupIndex)
                {
                    for (int j = group.StartIndex; j < group.StartIndex + group.Count; j++)
                    {
                        result.Add(messageList[j]);
                    }
                }
            }

            return Task.FromResult<IEnumerable<ChatMessage>>(result);
        }
    }
}
