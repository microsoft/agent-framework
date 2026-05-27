// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.Logging;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI.Compaction;

/// <summary>
/// A compaction strategy that removes the oldest non-system message groups,
/// keeping at least <see cref="MinimumPreservedGroups"/> most-recent groups intact.
/// </summary>
/// <remarks>
/// <para>
/// This strategy preserves system messages and removes the oldest non-system message groups first.
/// It respects atomic group boundaries — an assistant message with tool calls and its
/// corresponding tool result messages are always removed together.
/// </para>
/// <para>
/// <see cref="MinimumPreservedGroups"/> is a hard floor: even if the <see cref="CompactionStrategy.Target"/>
/// has not been reached, compaction will not touch the last <see cref="MinimumPreservedGroups"/> non-system groups.
/// </para>
/// <para>
/// The <see cref="CompactionTrigger"/> controls when compaction proceeds.
/// Use <see cref="CompactionTriggers"/> for common trigger conditions such as token or group thresholds.
/// </para>
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class TruncationCompactionStrategy : CompactionStrategy
{
    /// <summary>
    /// The default minimum number of most-recent non-system groups to preserve.
    /// </summary>
    public const int DefaultMinimumPreserved = 32;

    /// <summary>
    /// Initializes a new instance of the <see cref="TruncationCompactionStrategy"/> class.
    /// </summary>
    /// <param name="trigger">
    /// The <see cref="CompactionTrigger"/> that controls when compaction proceeds.
    /// </param>
    /// <param name="minimumPreservedGroups">
    /// The minimum number of most-recent non-system message groups to preserve.
    /// This is a hard floor — compaction will not remove groups beyond this limit,
    /// regardless of the target condition.
    /// </param>
    /// <param name="target">
    /// An optional target condition that controls when compaction stops. When <see langword="null"/>,
    /// defaults to the inverse of the <paramref name="trigger"/> — compaction stops as soon as the trigger would no longer fire.
    /// </param>
    public TruncationCompactionStrategy(CompactionTrigger trigger, int minimumPreservedGroups = DefaultMinimumPreserved, CompactionTrigger? target = null)
        : base(trigger, target)
    {
        this.MinimumPreservedGroups = EnsureNonNegative(minimumPreservedGroups);
    }

    /// <summary>
    /// Gets the minimum number of most-recent non-system message groups that are always preserved.
    /// This is a hard floor that compaction cannot exceed, regardless of the target condition.
    /// </summary>
    public int MinimumPreservedGroups { get; }

    /// <inheritdoc/>
    protected override ValueTask<bool> CompactCoreAsync(CompactionMessageIndex index, ILogger logger, CancellationToken cancellationToken)
    {
        // Count removable (non-system, non-excluded) groups
        int removableCount = 0;
        for (int i = 0; i < index.Groups.Count; i++)
        {
            CompactionMessageGroup group = index.Groups[i];
            if (!group.IsExcluded && group.Kind != CompactionGroupKind.System)
            {
                removableCount++;
            }
        }

        int maxRemovable = removableCount - this.MinimumPreservedGroups;
        if (maxRemovable <= 0)
        {
            return new ValueTask<bool>(false);
        }

        // Exclude oldest non-system groups one at a time, re-checking target after each
        bool compacted = false;
        int removed = 0;
        for (int i = 0; i < index.Groups.Count && removed < maxRemovable; i++)
        {
            CompactionMessageGroup group = index.Groups[i];
            if (group.IsExcluded || group.Kind == CompactionGroupKind.System)
            {
                continue;
            }

            group.IsExcluded = true;
            group.ExcludeReason = $"Truncated by {nameof(TruncationCompactionStrategy)}";
            removed++;
            compacted = true;

            // Stop when target condition is met
            if (this.Target(index))
            {
                break;
            }
        }

        return new ValueTask<bool>(compacted);
    }
}
