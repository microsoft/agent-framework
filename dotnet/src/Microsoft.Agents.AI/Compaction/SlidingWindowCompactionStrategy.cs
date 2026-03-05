// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI.Compaction;

/// <summary>
/// A compaction strategy that removes the oldest user turns and their associated response groups
/// to bound conversation length.
/// </summary>
/// <remarks>
/// <para>
/// This strategy always preserves system messages. It identifies user turns in the
/// conversation (via <see cref="MessageGroup.TurnIndex"/>) and excludes the oldest turns
/// one at a time until the <see cref="CompactionStrategy.Target"/> condition is met.
/// </para>
/// <para>
/// <see cref="MinimumPreserved"/> is a hard floor: even if the <see cref="CompactionStrategy.Target"/>
/// has not been reached, compaction will not touch the last <see cref="MinimumPreserved"/> non-system groups.
/// </para>
/// <para>
/// This strategy is more predictable than token-based truncation for bounding conversation
/// length, since it operates on logical turn boundaries rather than estimated token counts.
/// </para>
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class SlidingWindowCompactionStrategy : CompactionStrategy
{
    /// <summary>
    /// The default minimum number of most-recent non-system groups to preserve.
    /// </summary>
    public const int DefaultMinimumPreserved = 1;

    /// <summary>
    /// Initializes a new instance of the <see cref="SlidingWindowCompactionStrategy"/> class.
    /// </summary>
    /// <param name="trigger">
    /// The <see cref="CompactionTrigger"/> that controls when compaction proceeds.
    /// Use <see cref="CompactionTriggers.TurnsExceed"/> for turn-based thresholds.
    /// </param>
    /// <param name="minimumPreserved">
    /// The minimum number of most-recent non-system message groups to preserve.
    /// This is a hard floor — compaction will not exclude groups beyond this limit,
    /// regardless of the target condition.
    /// </param>
    /// <param name="target">
    /// An optional target condition that controls when compaction stops. When <see langword="null"/>,
    /// defaults to the inverse of the <paramref name="trigger"/> — compaction stops as soon as the trigger would no longer fire.
    /// </param>
    public SlidingWindowCompactionStrategy(CompactionTrigger trigger, int minimumPreserved = DefaultMinimumPreserved, CompactionTrigger? target = null)
        : base(trigger, target)
    {
        this.MinimumPreserved = minimumPreserved;
    }

    /// <summary>
    /// Gets the minimum number of most-recent non-system groups that are always preserved.
    /// This is a hard floor that compaction cannot exceed, regardless of the target condition.
    /// </summary>
    public int MinimumPreserved { get; }

    /// <inheritdoc/>
    protected override Task<bool> ApplyCompactionAsync(MessageIndex index, CancellationToken cancellationToken)
    {
        // Identify protected groups: the N most-recent non-system, non-excluded groups
        List<int> nonSystemIncludedIndices = [];
        foreach (MessageGroup group in index.Groups)
        {
            if (!group.IsExcluded && group.Kind != MessageGroupKind.System)
            {
                nonSystemIncludedIndices.Add(index.Groups.IndexOf(group));
            }
        }

        int protectedStart = Math.Max(0, nonSystemIncludedIndices.Count - this.MinimumPreserved);
        HashSet<int> protectedGroupIndices = [];
        for (int i = protectedStart; i < nonSystemIncludedIndices.Count; i++)
        {
            protectedGroupIndices.Add(nonSystemIncludedIndices[i]);
        }

        // Collect distinct included turn indices in order (oldest first), excluding protected groups
        List<int> excludableTurns = [];
        for (int i = 0; i < index.Groups.Count; i++)
        {
            MessageGroup group = index.Groups[i];
            if (!group.IsExcluded
                && group.Kind != MessageGroupKind.System
                && !protectedGroupIndices.Contains(i)
                && group.TurnIndex is int turnIndex
                && !excludableTurns.Contains(turnIndex))
            {
                excludableTurns.Add(turnIndex);
            }
        }

        // Exclude one turn at a time from oldest, re-checking target after each
        bool compacted = false;

        for (int t = 0; t < excludableTurns.Count; t++)
        {
            int turnToExclude = excludableTurns[t];

            for (int i = 0; i < index.Groups.Count; i++)
            {
                MessageGroup group = index.Groups[i];
                if (!group.IsExcluded
                    && group.Kind != MessageGroupKind.System
                    && !protectedGroupIndices.Contains(i)
                    && group.TurnIndex == turnToExclude)
                {
                    group.IsExcluded = true;
                    group.ExcludeReason = $"Excluded by {nameof(SlidingWindowCompactionStrategy)}";
                }
            }

            compacted = true;

            // Stop when target condition is met
            if (this.Target(index))
            {
                break;
            }
        }

        return Task.FromResult(compacted);
    }
}
