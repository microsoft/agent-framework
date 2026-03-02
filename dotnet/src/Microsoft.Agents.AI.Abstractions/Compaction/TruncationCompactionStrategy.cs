// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Compaction;

/// <summary>
/// A compaction strategy that removes the oldest message groups until the estimated
/// token count is within a specified budget.
/// </summary>
/// <remarks>
/// <para>
/// This strategy preserves system messages and removes the oldest non-system message groups first.
/// It respects atomic group boundaries — an assistant message with tool calls and its
/// corresponding tool result messages are always removed together.
/// </para>
/// <para>
/// The trigger condition fires only when the current token count exceeds <c>maxTokens</c>.
/// </para>
/// </remarks>
public class TruncationCompactionStrategy : ChatHistoryCompactionStrategy
{
    private readonly int _maxTokens;

    /// <summary>
    /// Initializes a new instance of the <see cref="TruncationCompactionStrategy"/> class.
    /// </summary>
    /// <param name="maxTokens">The maximum token budget. Groups are removed until the token count is at or below this value.</param>
    /// <param name="preserveRecentGroups">
    /// The minimum number of most-recent non-system message groups to keep.
    /// Defaults to 1 so that at least the latest exchange is always preserved.
    /// </param>
    public TruncationCompactionStrategy(int maxTokens, int preserveRecentGroups = 1)
        : base(new TruncationReducer(preserveRecentGroups))
    {
        this._maxTokens = maxTokens;
    }

    /// <inheritdoc/>
    public override bool ShouldCompact(CompactionMetric metrics) =>
        metrics.TokenCount > this._maxTokens;

    /// <summary>
    /// An <see cref="IChatReducer"/> that removes the oldest non-system message groups,
    /// keeping at least the most recent group.
    /// </summary>
    private sealed class TruncationReducer(int preserveRecentGroups) : IChatReducer
    {
        public Task<IEnumerable<ChatMessage>> ReduceAsync(
            IEnumerable<ChatMessage> messages,
            CancellationToken cancellationToken = default)
        {
            IReadOnlyList<ChatMessage> messageList = [.. messages];

            List<ChatMessageGroup> removableGroups = CurrentMetrics.Groups.Where(g => g.Kind != ChatMessageGroupKind.System).ToList();

            if (removableGroups.Count == 0)
            {
                return Task.FromResult<IEnumerable<ChatMessage>>(messageList);
            }

            // Remove oldest non-system groups, keeping at least preserveRecentGroups.
            int maxRemovable = removableGroups.Count - preserveRecentGroups;

            if (maxRemovable <= 0)
            {
                return Task.FromResult<IEnumerable<ChatMessage>>(messageList);
            }

            HashSet<int> removedGroupStarts = [];
            for (int ri = 0; ri < maxRemovable; ri++)
            {
                removedGroupStarts.Add(removableGroups[ri].StartIndex);
            }

            List<ChatMessage> messagesToKeep = new(messageList.Count);
            foreach (ChatMessageGroup group in CurrentMetrics.Groups)
            {
                if (removedGroupStarts.Contains(group.StartIndex))
                {
                    continue;
                }

                for (int j = group.StartIndex; j < group.StartIndex + group.Count; j++)
                {
                    messagesToKeep.Add(messageList[j]);
                }
            }

            return Task.FromResult<IEnumerable<ChatMessage>>(messagesToKeep);
        }
    }
}
