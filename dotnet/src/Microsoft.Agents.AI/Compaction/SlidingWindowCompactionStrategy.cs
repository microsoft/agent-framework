// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Compaction;

/// <summary>
/// A compaction strategy that keeps only the most recent user turns and their
/// associated response groups, removing older turns to bound conversation length.
/// </summary>
/// <remarks>
/// <para>
/// This strategy always preserves system messages. It identifies user turns in the
/// conversation (via <see cref="MessageGroup.TurnIndex"/>) and keeps the last
/// <see cref="MaxTurns"/> turns along with all response groups (assistant replies,
/// tool call groups) that belong to each kept turn.
/// </para>
/// <para>
/// The <see cref="CompactionTrigger"/> predicate controls when compaction proceeds.
/// When <see langword="null"/>, a default trigger of <see cref="CompactionTriggers.TurnsExceed"/>
/// with <see cref="MaxTurns"/> is used.
/// </para>
/// <para>
/// This strategy is more predictable than token-based truncation for bounding conversation
/// length, since it operates on logical turn boundaries rather than estimated token counts.
/// </para>
/// </remarks>
public sealed class SlidingWindowCompactionStrategy : CompactionStrategy
{
    /// <summary>
    /// The default maximum number of user turns to retain before compaction occurs. This default is a reasonable starting point
    /// for many conversations, but should be tuned based on the expected conversation length and token budget.
    /// </summary>
    public const int DefaultMaximumTurns = 32;

    /// <summary>
    /// Initializes a new instance of the <see cref="SlidingWindowCompactionStrategy"/> class.
    /// </summary>
    /// <param name="maximumTurns">
    /// The maximum number of user turns to keep. Older turns and their associated responses are removed.
    /// </param>
    public SlidingWindowCompactionStrategy(int maximumTurns = DefaultMaximumTurns)
        : base(CompactionTriggers.TurnsExceed(maximumTurns))
    {
        this.MaxTurns = maximumTurns;
    }

    /// <summary>
    /// Gets the maximum number of user turns to retain after compaction.
    /// </summary>
    public int MaxTurns { get; }

    /// <inheritdoc/>
    protected override Task<bool> ApplyCompactionAsync(MessageIndex index, CancellationToken cancellationToken)
    {
        // Collect distinct included turn indices in order
        List<int> includedTurns = [];
        foreach (MessageGroup group in index.Groups)
        {
            if (!group.IsExcluded && group.TurnIndex is int turnIndex && !includedTurns.Contains(turnIndex))
            {
                includedTurns.Add(turnIndex);
            }
        }

        if (includedTurns.Count <= this.MaxTurns)
        {
            return Task.FromResult(false);
        }

        // Determine which turn indices to exclude (oldest)
        int turnsToRemove = includedTurns.Count - this.MaxTurns;
        HashSet<int> excludedTurnIndices = [.. includedTurns.Take(turnsToRemove)];

        bool compacted = false;
        for (int i = 0; i < index.Groups.Count; i++)
        {
            MessageGroup group = index.Groups[i];
            if (group.IsExcluded || group.Kind == MessageGroupKind.System)
            {
                continue;
            }

            if (group.TurnIndex is int ti && excludedTurnIndices.Contains(ti))
            {
                group.IsExcluded = true;
                group.ExcludeReason = $"Excluded by {nameof(SlidingWindowCompactionStrategy)}";
                compacted = true;
            }
        }

        return Task.FromResult(compacted);
    }
}
