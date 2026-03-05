// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Compaction;

/// <summary>
/// A compaction strategy that keeps the most recent message groups up to a specified limit,
/// optionally preserving system message groups.
/// </summary>
/// <remarks>
/// <para>
/// This strategy implements a sliding window approach: it marks older groups as excluded
/// while keeping the most recent groups within the configured <see cref="MaxGroups"/> limit.
/// System message groups can optionally be preserved regardless of their position.
/// </para>
/// <para>
/// This strategy respects atomic group preservation — tool call groups (assistant message + tool results)
/// are always kept or excluded together.
/// </para>
/// </remarks>
public sealed class TruncationCompactionStrategy : ICompactionStrategy
{
    /// <summary>
    /// Initializes a new instance of the <see cref="TruncationCompactionStrategy"/> class.
    /// </summary>
    /// <param name="maxGroups">The maximum number of message groups to keep. Must be greater than zero.</param>
    /// <param name="preserveSystemMessages">Whether to preserve system message groups regardless of position. Defaults to <see langword="true"/>.</param>
    public TruncationCompactionStrategy(int maxGroups, bool preserveSystemMessages = true)
    {
        this.MaxGroups = maxGroups;
        this.PreserveSystemMessages = preserveSystemMessages;
    }

    /// <summary>
    /// Gets the maximum number of message groups to retain after compaction.
    /// </summary>
    public int MaxGroups { get; }

    /// <summary>
    /// Gets a value indicating whether system message groups are preserved regardless of their position in the conversation.
    /// </summary>
    public bool PreserveSystemMessages { get; }

    /// <inheritdoc/>
    public Task<bool> CompactAsync(MessageGroups groups, CancellationToken cancellationToken = default)
    {
        int includedCount = groups.IncludedGroupCount;
        if (includedCount <= this.MaxGroups)
        {
            return Task.FromResult(false);
        }

        int excessCount = includedCount - this.MaxGroups;
        bool compacted = false;

        // Exclude oldest non-system groups first (iterate from the beginning)
        for (int i = 0; i < groups.Groups.Count && excessCount > 0; i++)
        {
            MessageGroup group = groups.Groups[i];
            if (group.IsExcluded)
            {
                continue;
            }

            if (this.PreserveSystemMessages && group.Kind == MessageGroupKind.System)
            {
                continue;
            }

            group.IsExcluded = true;
            group.ExcludeReason = "Truncated by TruncationCompactionStrategy";
            excessCount--;
            compacted = true;
        }

        return Task.FromResult(compacted);
    }
}
