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
/// conversation (via <see cref="CompactionMessageGroup.TurnIndex"/>) and excludes the oldest turns
/// one at a time until the <see cref="CompactionStrategy.Target"/> condition is met.
/// </para>
/// <para>
/// <see cref="MinimumPreservedTurns"/> is a hard floor: even if the <see cref="CompactionStrategy.Target"/>
/// has not been reached, compaction will not touch the last <see cref="MinimumPreservedTurns"/> turns
/// (by <see cref="CompactionMessageGroup.TurnIndex"/>). Groups with a <see cref="CompactionMessageGroup.TurnIndex"/>
/// of <c>0</c> or <see langword="null"/> are always preserved regardless of this setting.
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
    /// The default minimum number of most-recent turns to preserve.
    /// </summary>
    public const int DefaultMinimumPreserved = 1;

    /// <summary>
    /// Initializes a new instance of the <see cref="SlidingWindowCompactionStrategy"/> class.
    /// </summary>
    /// <param name="trigger">
    /// The <see cref="CompactionTrigger"/> that controls when compaction proceeds.
    /// Use <see cref="CompactionTriggers.TurnsExceed"/> for turn-based thresholds.
    /// </param>
    /// <param name="minimumPreservedTurns">
    /// The minimum number of most-recent turns (by <see cref="CompactionMessageGroup.TurnIndex"/>) to preserve.
    /// This is a hard floor — compaction will not exclude turns within this range, regardless of the target condition.
    /// Groups with <see cref="CompactionMessageGroup.TurnIndex"/> of <c>0</c> or <see langword="null"/> are always preserved.
    /// </param>
    /// <param name="target">
    /// An optional target condition that controls when compaction stops. When <see langword="null"/>,
    /// defaults to the inverse of the <paramref name="trigger"/> — compaction stops as soon as the trigger would no longer fire.
    /// </param>
    public SlidingWindowCompactionStrategy(CompactionTrigger trigger, int minimumPreservedTurns = DefaultMinimumPreserved, CompactionTrigger? target = null)
        : base(trigger, target)
    {
        this.MinimumPreservedTurns = EnsureNonNegative(minimumPreservedTurns);
    }

    /// <summary>
    /// Gets the minimum number of most-recent turns (by <see cref="CompactionMessageGroup.TurnIndex"/>) that are always preserved.
    /// This is a hard floor that compaction cannot exceed, regardless of the target condition.
    /// Groups with <see cref="CompactionMessageGroup.TurnIndex"/> of <c>0</c> or <see langword="null"/> are always preserved
    /// independently of this value.
    /// </summary>
    public int MinimumPreservedTurns { get; }

    /// <inheritdoc/>
    protected override ValueTask<bool> CompactCoreAsync(CompactionMessageIndex index, ILogger logger, CancellationToken cancellationToken)
    {
        // Forward pass: pre-index non-system included groups by TurnIndex.
        Dictionary<int, List<int>> turnGroups = [];
        List<int> turnOrder = [];

        for (int i = 0; i < index.Groups.Count; i++)
        {
            CompactionMessageGroup group = index.Groups[i];
            if (!group.IsExcluded && group.Kind != CompactionGroupKind.System && group.TurnIndex is int turnIndex)
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

        // Backward pass: identify protected turns by TurnIndex.
        // TurnIndex = 0 is always protected (non-system messages before first user message).
        // TurnIndex = null is always protected (system messages, already excluded from turn tracking).
        HashSet<int> protectedTurnIndices = [];
        if (turnGroups.ContainsKey(0))
        {
            protectedTurnIndices.Add(0);
        }

        // Protect the last MinimumPreservedTurns distinct turns.
        int turnsToProtect = Math.Min(this.MinimumPreservedTurns, turnOrder.Count);
        for (int i = turnOrder.Count - turnsToProtect; i < turnOrder.Count; i++)
        {
            protectedTurnIndices.Add(turnOrder[i]);
        }

        // Exclude turns oldest-first, skipping protected turns, checking target after each turn.
        bool compacted = false;

        for (int t = 0; t < turnOrder.Count; t++)
        {
            int currentTurnIndex = turnOrder[t];
            if (protectedTurnIndices.Contains(currentTurnIndex))
            {
                continue;
            }

            List<int> groupIndices = turnGroups[currentTurnIndex];
            for (int g = 0; g < groupIndices.Count; g++)
            {
                int idx = groupIndices[g];
                index.Groups[idx].IsExcluded = true;
                index.Groups[idx].ExcludeReason = $"Excluded by {nameof(SlidingWindowCompactionStrategy)}";
            }

            compacted = true;

            if (this.Target(index))
            {
                break;
            }
        }

        return new ValueTask<bool>(compacted);
    }
}
