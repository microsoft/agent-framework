// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI.Compaction;

/// <summary>
/// Base class for compaction strategies that operate on <see cref="CompactionGroupKind.ToolCall"/>
/// groups, providing the shared logic for protected-group identification, eligible-group collection,
/// and the exclude-and-insert processing loop.
/// </summary>
/// <remarks>
/// <para>
/// Subclasses customize behavior through two hook methods:
/// <list type="bullet">
/// <item><description>
/// <see cref="IsToolGroupEligible"/> — determines whether a specific tool call group should be processed.
/// The default returns <see langword="true"/> for all tool call groups.
/// </description></item>
/// <item><description>
/// <see cref="TransformToolGroup"/> — transforms an eligible group into replacement messages.
/// Returns the replacement group kind, messages, and an exclude reason for diagnostics.
/// </description></item>
/// </list>
/// </para>
/// <para>
/// <see cref="MinimumPreservedGroups"/> is a hard floor: even if the <see cref="CompactionStrategy.Target"/>
/// has not been reached, processing will not touch the last <see cref="MinimumPreservedGroups"/> non-system groups.
/// </para>
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public abstract class ToolResultStrategyBase : CompactionStrategy
{
    /// <summary>
    /// Initializes a new instance of the <see cref="ToolResultStrategyBase"/> class.
    /// </summary>
    /// <param name="trigger">
    /// The <see cref="CompactionTrigger"/> that controls when processing proceeds.
    /// </param>
    /// <param name="minimumPreservedGroups">
    /// The minimum number of most-recent non-system message groups to preserve.
    /// This is a hard floor — processing will not touch groups beyond this limit,
    /// regardless of the target condition.
    /// </param>
    /// <param name="target">
    /// An optional target condition that controls when processing stops. When <see langword="null"/>,
    /// defaults to the inverse of the <paramref name="trigger"/>.
    /// </param>
    protected ToolResultStrategyBase(
        CompactionTrigger trigger,
        int minimumPreservedGroups,
        CompactionTrigger? target = null)
        : base(trigger, target)
    {
        this.MinimumPreservedGroups = EnsureNonNegative(minimumPreservedGroups);
    }

    /// <summary>
    /// Gets the minimum number of most-recent non-system groups that are always preserved.
    /// This is a hard floor that processing cannot exceed, regardless of the target condition.
    /// </summary>
    public int MinimumPreservedGroups { get; }

    /// <summary>
    /// Determines whether the specified <see cref="CompactionGroupKind.ToolCall"/> group should be
    /// processed by this strategy. Called for each non-excluded, non-protected tool call group.
    /// </summary>
    /// <param name="group">The tool call group to evaluate.</param>
    /// <returns>
    /// <see langword="true"/> if the group should be processed; <see langword="false"/> to skip it.
    /// </returns>
    /// <remarks>
    /// The default implementation returns <see langword="true"/> for all groups.
    /// Override to add filtering logic such as checking for specific tool names.
    /// </remarks>
    protected virtual bool IsToolGroupEligible(CompactionMessageGroup group) => true;

    /// <summary>
    /// Transforms an eligible tool call group into replacement messages.
    /// </summary>
    /// <param name="group">The tool call group to transform.</param>
    /// <returns>
    /// A tuple containing:
    /// <list type="bullet">
    /// <item><description><b>Kind</b> — the <see cref="CompactionGroupKind"/> for the replacement group.</description></item>
    /// <item><description><b>Messages</b> — the replacement messages to insert.</description></item>
    /// <item><description><b>ExcludeReason</b> — a diagnostic string describing why the original group was excluded.</description></item>
    /// </list>
    /// </returns>
    protected abstract (CompactionGroupKind Kind, List<ChatMessage> Messages, string ExcludeReason)
        TransformToolGroup(CompactionMessageGroup group);

    /// <inheritdoc/>
    protected sealed override ValueTask<bool> CompactCoreAsync(
        CompactionMessageIndex index,
        ILogger logger,
        CancellationToken cancellationToken)
    {
        // Identify protected groups: the N most-recent non-system, non-excluded groups
        List<int> nonSystemIncludedIndices = [];
        for (int i = 0; i < index.Groups.Count; i++)
        {
            CompactionMessageGroup group = index.Groups[i];
            if (!group.IsExcluded && group.Kind != CompactionGroupKind.System)
            {
                nonSystemIncludedIndices.Add(i);
            }
        }

        int protectedStart = EnsureNonNegative(nonSystemIncludedIndices.Count - this.MinimumPreservedGroups);
        HashSet<int> protectedGroupIndices = [];
        for (int i = protectedStart; i < nonSystemIncludedIndices.Count; i++)
        {
            protectedGroupIndices.Add(nonSystemIncludedIndices[i]);
        }

        // Collect eligible tool groups in order (oldest first)
        List<int> eligibleIndices = [];
        for (int i = 0; i < index.Groups.Count; i++)
        {
            CompactionMessageGroup group = index.Groups[i];
            if (group.IsExcluded || group.Kind != CompactionGroupKind.ToolCall || protectedGroupIndices.Contains(i))
            {
                continue;
            }

            if (!this.IsToolGroupEligible(group))
            {
                continue;
            }

            eligibleIndices.Add(i);
        }

        if (eligibleIndices.Count == 0)
        {
            return new ValueTask<bool>(false);
        }

        // Process one tool group at a time from oldest, re-checking target after each
        bool processed = false;
        int offset = 0;

        for (int e = 0; e < eligibleIndices.Count; e++)
        {
            cancellationToken.ThrowIfCancellationRequested();

            int idx = eligibleIndices[e] + offset;
            CompactionMessageGroup group = index.Groups[idx];

            var (kind, messages, excludeReason) = this.TransformToolGroup(group);

            group.IsExcluded = true;
            group.ExcludeReason = excludeReason;

            index.InsertGroup(idx + 1, kind, messages, group.TurnIndex);
            offset++;

            processed = true;

            if (this.Target(index))
            {
                break;
            }
        }

        return new ValueTask<bool>(processed);
    }

    /// <summary>
    /// Extracts function calls, their results, and plain-text tool results from a
    /// <see cref="CompactionMessageGroup"/>.
    /// </summary>
    /// <remarks>
    /// <see cref="FunctionCallContent"/> items are collected as ordered (CallId, Name) pairs,
    /// preserving first-seen order for downstream formatting. <see cref="FunctionResultContent"/>
    /// items are collected by CallId for lookup-based matching. Plain-text Tool-role messages
    /// that lack <see cref="FunctionResultContent"/> are collected separately for positional fallback.
    /// </remarks>
    protected static (
        List<(string CallId, string Name)> FunctionCalls,
        Dictionary<string, string> ResultsByCallId,
        List<string> PlainTextResults) ExtractToolCallsAndResults(CompactionMessageGroup group)
    {
        List<(string CallId, string Name)> functionCalls = [];
        Dictionary<string, string> resultsByCallId = [];
        List<string> plainTextResults = [];

        foreach (ChatMessage message in group.Messages)
        {
            bool hasFunctionResult = false;

            if (message.Contents is not null)
            {
                foreach (AIContent content in message.Contents)
                {
                    if (content is FunctionCallContent fcc)
                    {
                        functionCalls.Add((fcc.CallId, fcc.Name));
                    }
                    else if (content is FunctionResultContent frc && frc.CallId is not null)
                    {
                        resultsByCallId[frc.CallId] = frc.Result?.ToString() ?? string.Empty;
                        hasFunctionResult = true;
                    }
                }
            }

            // Collect plain text from Tool-role messages that lack FunctionResultContent
            if (!hasFunctionResult && message.Role == ChatRole.Tool && message.Text is string text)
            {
                plainTextResults.Add(text);
            }
        }

        return (functionCalls, resultsByCallId, plainTextResults);
    }
}
