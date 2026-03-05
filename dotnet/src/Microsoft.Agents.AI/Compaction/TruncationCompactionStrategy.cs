// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Compaction;

/// <summary>
/// A compaction strategy that removes the oldest non-system message groups,
/// keeping the most recent groups up to <see cref="PreserveRecentGroups"/>.
/// </summary>
/// <remarks>
/// <para>
/// This strategy preserves system messages and removes the oldest non-system message groups first.
/// It respects atomic group boundaries — an assistant message with tool calls and its
/// corresponding tool result messages are always removed together.
/// </para>
/// <para>
/// The <see cref="CompactionTrigger"/> controls when compaction proceeds.
/// Use <see cref="CompactionTriggers"/> for common trigger conditions such as token or group thresholds.
/// </para>
/// </remarks>
public sealed class TruncationCompactionStrategy : CompactionStrategy
{
    /// <summary>
    /// The default number of most-recent non-system groups to protect from collapsing.
    /// </summary>
    public const int DefaultPreserveRecentGroups = 32;

    /// <summary>
    /// Initializes a new instance of the <see cref="TruncationCompactionStrategy"/> class.
    /// </summary>
    /// <param name="trigger">
    /// The <see cref="CompactionTrigger"/> that controls when compaction proceeds.
    /// </param>
    /// <param name="preserveRecentGroups">
    /// The minimum number of most-recent non-system message groups to keep.
    /// Defaults to 1 so that at least the latest exchange is always preserved.
    /// </param>
    public TruncationCompactionStrategy(CompactionTrigger trigger, int preserveRecentGroups = DefaultPreserveRecentGroups)
        : base(trigger)
    {
        this.PreserveRecentGroups = preserveRecentGroups;
    }

    /// <summary>
    /// Gets the minimum number of most-recent non-system message groups to retain after compaction.
    /// </summary>
    public int PreserveRecentGroups { get; }

    /// <inheritdoc/>
    protected override Task<bool> ApplyCompactionAsync(MessageIndex index, CancellationToken cancellationToken)
    {
        // Count removable (non-system, non-excluded) groups
        int removableCount = 0;
        for (int i = 0; i < index.Groups.Count; i++)
        {
            MessageGroup group = index.Groups[i];
            if (!group.IsExcluded && group.Kind != MessageGroupKind.System)
            {
                removableCount++;
            }
        }

        int maxRemovable = removableCount - this.PreserveRecentGroups;
        if (maxRemovable <= 0)
        {
            return Task.FromResult(false);
        }

        // Exclude oldest non-system groups first (iterate from the beginning)
        bool compacted = false;
        int removed = 0;
        for (int i = 0; i < index.Groups.Count && removed < maxRemovable; i++)
        {
            MessageGroup group = index.Groups[i];
            if (group.IsExcluded || group.Kind == MessageGroupKind.System)
            {
                continue;
            }

            group.IsExcluded = true;
            group.ExcludeReason = $"Truncated by {nameof(TruncationCompactionStrategy)}";
            removed++;
            compacted = true;
        }

        return Task.FromResult(compacted);
    }
}
