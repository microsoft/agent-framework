// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Compaction;

/// <summary>
/// A compaction strategy that collapses old tool call groups into single concise assistant
/// messages, removing the detailed tool results while preserving a record of which tools were called.
/// </summary>
/// <remarks>
/// <para>
/// This is the gentlest compaction strategy — it does not remove any user messages or
/// plain assistant responses. It only targets <see cref="MessageGroupKind.ToolCall"/>
/// groups outside the protected recent window, replacing each multi-message group
/// (assistant call + tool results) with a single assistant message like
/// <c>[Tool calls: get_weather, search_docs]</c>.
/// </para>
/// <para>
/// The <see cref="CompactionTrigger"/> predicate controls when compaction proceeds.
/// When <see langword="null"/>, a default compound trigger of
/// <see cref="CompactionTriggers.TokensExceed"/> AND <see cref="CompactionTriggers.HasToolCalls"/>
/// is used.
/// </para>
/// </remarks>
public sealed class ToolResultCompactionStrategy : CompactionStrategy
{
    /// <summary>
    /// The default number of most-recent non-system groups to protect from collapsing.
    /// </summary>
    public const int DefaultPreserveRecentGroups = 2;

    /// <summary>
    /// Initializes a new instance of the <see cref="ToolResultCompactionStrategy"/> class.
    /// </summary>
    /// <param name="trigger">
    /// The <see cref="CompactionTrigger"/> that controls when compaction proceeds.
    /// </param>
    /// <param name="preserveRecentGroups">
    /// The number of most-recent non-system message groups to protect from collapsing.
    /// Defaults to <see cref="DefaultPreserveRecentGroups"/>, ensuring the current turn's tool interactions remain visible.
    /// </param>
    /// <param name="target">
    /// An optional target condition that controls when compaction stops. When <see langword="null"/>,
    /// defaults to the inverse of the <paramref name="trigger"/> — compaction stops as soon as the trigger would no longer fire.
    /// </param>
    public ToolResultCompactionStrategy(CompactionTrigger trigger, int preserveRecentGroups = DefaultPreserveRecentGroups, CompactionTrigger? target = null)
        : base(trigger, target)
    {
        this.PreserveRecentGroups = preserveRecentGroups;
    }

    /// <summary>
    /// Gets the number of most-recent non-system groups to protect from collapsing.
    /// </summary>
    public int PreserveRecentGroups { get; }

    /// <inheritdoc/>
    protected override Task<bool> ApplyCompactionAsync(MessageIndex index, CancellationToken cancellationToken)
    {
        // Identify protected groups: the N most-recent non-system, non-excluded groups
        List<int> nonSystemIncludedIndices = [];
        for (int i = 0; i < index.Groups.Count; i++)
        {
            MessageGroup group = index.Groups[i];
            if (!group.IsExcluded && group.Kind != MessageGroupKind.System)
            {
                nonSystemIncludedIndices.Add(i);
            }
        }

        int protectedStart = Math.Max(0, nonSystemIncludedIndices.Count - this.PreserveRecentGroups);
        HashSet<int> protectedGroupIndices = [];
        for (int i = protectedStart; i < nonSystemIncludedIndices.Count; i++)
        {
            protectedGroupIndices.Add(nonSystemIncludedIndices[i]);
        }

        // Collect eligible tool groups in order (oldest first)
        List<int> eligibleIndices = [];
        for (int i = 0; i < index.Groups.Count; i++)
        {
            MessageGroup group = index.Groups[i];
            if (!group.IsExcluded && group.Kind == MessageGroupKind.ToolCall && !protectedGroupIndices.Contains(i))
            {
                eligibleIndices.Add(i);
            }
        }

        if (eligibleIndices.Count == 0)
        {
            return Task.FromResult(false);
        }

        // Collapse one tool group at a time from oldest, re-checking target after each
        bool compacted = false;
        int offset = 0;

        for (int e = 0; e < eligibleIndices.Count; e++)
        {
            int idx = eligibleIndices[e] + offset;
            MessageGroup group = index.Groups[idx];

            // Extract tool names from FunctionCallContent
            List<string> toolNames = [];
            foreach (ChatMessage message in group.Messages)
            {
                if (message.Contents is not null)
                {
                    foreach (AIContent content in message.Contents)
                    {
                        if (content is FunctionCallContent fcc)
                        {
                            toolNames.Add(fcc.Name);
                        }
                    }
                }
            }

            // Exclude the original group and insert a collapsed replacement
            group.IsExcluded = true;
            group.ExcludeReason = $"Collapsed by {nameof(ToolResultCompactionStrategy)}";

            string summary = $"[Tool calls: {string.Join(", ", toolNames)}]";
            index.InsertGroup(idx + 1, MessageGroupKind.AssistantText, [new ChatMessage(ChatRole.Assistant, summary)], group.TurnIndex);
            offset++; // Each insertion shifts subsequent indices by 1

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
