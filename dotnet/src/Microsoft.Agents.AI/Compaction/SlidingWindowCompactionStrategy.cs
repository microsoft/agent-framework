// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.Logging;
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
        this.MinimumPreserved = EnsureNonNegative(minimumPreserved);
    }

    /// <summary>
    /// Gets the minimum number of most-recent non-system groups that are always preserved.
    /// This is a hard floor that compaction cannot exceed, regardless of the target condition.
    /// </summary>
    public int MinimumPreserved { get; }

    /// <inheritdoc/>
    protected override ValueTask<bool> CompactCoreAsync(MessageIndex index, ILogger logger, CancellationToken cancellationToken)
    {
        // Forward pass: count non-system included groups and pre-index them by TurnIndex.
        int nonSystemIncludedCount = 0;
        Dictionary<int, List<int>> turnGroups = [];
        List<int> turnOrder = [];

        for (int i = 0; i < index.Groups.Count; i++)
        {
            MessageGroup group = index.Groups[i];
            if (!group.IsExcluded && group.Kind != MessageGroupKind.System)
            {
                nonSystemIncludedCount++;

                if (group.TurnIndex is int turnIndex)
                {
                    if (!turnGroups.TryGetValue(turnIndex, out List<int>? indices))
                    {
                        indices = [];
                        turnGroups[turnIndex] = indices;
                        turnOrder.Add(turnIndex);
                    }

                    indices.Add(i);
                }
            }
        }

        // Backward pass: identify the protected tail (last MinimumPreserved non-system included groups).
        int protectedCount = Math.Min(this.MinimumPreserved, nonSystemIncludedCount);
#if NETSTANDARD
        HashSet<int> protectedIndices = [];
#else
        HashSet<int> protectedIndices = new(protectedCount);
#endif
        int remaining = protectedCount;
        for (int i = index.Groups.Count - 1; i >= 0 && remaining > 0; i--)
        {
            MessageGroup group = index.Groups[i];
            if (!group.IsExcluded && group.Kind != MessageGroupKind.System)
            {
                protectedIndices.Add(i);
                remaining--;
            }
        }

        // Exclude turns oldest-first using the pre-built index, checking target after each turn.
        bool compacted = false;

        for (int t = 0; t < turnOrder.Count; t++)
        {
            List<int> groupIndices = turnGroups[turnOrder[t]];
            bool anyExcluded = false;

            for (int g = 0; g < groupIndices.Count; g++)
            {
                int idx = groupIndices[g];
                if (!protectedIndices.Contains(idx))
                {
                    index.Groups[idx].IsExcluded = true;
                    index.Groups[idx].ExcludeReason = $"Excluded by {nameof(SlidingWindowCompactionStrategy)}";
                    anyExcluded = true;
                }
            }

            if (anyExcluded)
            {
                compacted = true;

                if (this.Target(index))
                {
                    break;
                }
            }
        }

        return new ValueTask<bool>(compacted);
    }
}
