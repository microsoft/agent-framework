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
/// A compaction strategy that collapses old tool call groups into single concise assistant
/// messages, removing the detailed tool results while preserving a record of which tools were called
/// and what they returned.
/// </summary>
/// <remarks>
/// <para>
/// This is the gentlest compaction strategy — it does not remove any user messages or
/// plain assistant responses. It only targets <see cref="CompactionGroupKind.ToolCall"/>
/// groups outside the protected recent window, replacing each multi-message group
/// (assistant call + tool results) with a single assistant message in a YAML-like format:
/// <code>
/// [Tool Calls]
/// get_weather:
///   - Sunny and 72°F
/// search_docs:
///   - Found 3 docs
/// </code>
/// </para>
/// <para>
/// <see cref="MinimumPreservedGroups"/> is a hard floor: even if the <see cref="CompactionStrategy.Target"/>
/// has not been reached, compaction will not touch the last <see cref="MinimumPreservedGroups"/> non-system groups.
/// </para>
/// <para>
/// The <see cref="CompactionTrigger"/> predicate controls when compaction proceeds. Use
/// <see cref="CompactionTriggers"/> for common trigger conditions such as token thresholds.
/// </para>
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class ToolResultCompactionStrategy : CompactionStrategy
{
    /// <summary>
    /// The default minimum number of most-recent non-system groups to preserve.
    /// </summary>
    public const int DefaultMinimumPreserved = 16;

    /// <summary>
    /// Initializes a new instance of the <see cref="ToolResultCompactionStrategy"/> class.
    /// </summary>
    /// <param name="trigger">
    /// The <see cref="CompactionTrigger"/> that controls when compaction proceeds.
    /// </param>
    /// <param name="minimumPreservedGroups">
    /// The minimum number of most-recent non-system message groups to preserve.
    /// This is a hard floor — compaction will not collapse groups beyond this limit,
    /// regardless of the target condition.
    /// Defaults to <see cref="DefaultMinimumPreserved"/>, ensuring the current turn's tool interactions remain visible.
    /// </param>
    /// <param name="target">
    /// An optional target condition that controls when compaction stops. When <see langword="null"/>,
    /// defaults to the inverse of the <paramref name="trigger"/> — compaction stops as soon as the trigger would no longer fire.
    /// </param>
    public ToolResultCompactionStrategy(CompactionTrigger trigger, int minimumPreservedGroups = DefaultMinimumPreserved, CompactionTrigger? target = null)
        : base(trigger, target)
    {
        this.MinimumPreservedGroups = EnsureNonNegative(minimumPreservedGroups);
    }

    /// <summary>
    /// Gets the minimum number of most-recent non-system groups that are always preserved.
    /// This is a hard floor that compaction cannot exceed, regardless of the target condition.
    /// </summary>
    public int MinimumPreservedGroups { get; }

    /// <inheritdoc/>
    protected override ValueTask<bool> CompactCoreAsync(CompactionMessageIndex index, ILogger logger, CancellationToken cancellationToken)
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
            if (!group.IsExcluded && group.Kind == CompactionGroupKind.ToolCall && !protectedGroupIndices.Contains(i))
            {
                eligibleIndices.Add(i);
            }
        }

        if (eligibleIndices.Count == 0)
        {
            return new ValueTask<bool>(false);
        }

        // Collapse one tool group at a time from oldest, re-checking target after each
        bool compacted = false;
        int offset = 0;

        for (int e = 0; e < eligibleIndices.Count; e++)
        {
            int idx = eligibleIndices[e] + offset;
            CompactionMessageGroup group = index.Groups[idx];

            string summary = BuildToolCallSummary(group);

            // Exclude the original group and insert a collapsed replacement
            group.IsExcluded = true;
            group.ExcludeReason = $"Collapsed by {nameof(ToolResultCompactionStrategy)}";

            ChatMessage summaryMessage = new(ChatRole.Assistant, summary);
            (summaryMessage.AdditionalProperties ??= [])[CompactionMessageGroup.SummaryPropertyKey] = true;

            index.InsertGroup(idx + 1, CompactionGroupKind.Summary, [summaryMessage], group.TurnIndex);
            offset++; // Each insertion shifts subsequent indices by 1

            compacted = true;

            // Stop when target condition is met
            if (this.Target(index))
            {
                break;
            }
        }

        return new ValueTask<bool>(compacted);
    }

    /// <summary>
    /// Builds a concise summary string for a tool call group, including tool names,
    /// results, and deduplication counts for repeated tool names.
    /// </summary>
    private static string BuildToolCallSummary(CompactionMessageGroup group)
    {
        // Collect function calls (callId, name) and results (callId → result text)
        List<(string CallId, string Name)> functionCalls = [];
        Dictionary<string, string> resultsByCallId = new();
        List<string> plainTextResults = [];

        foreach (ChatMessage message in group.Messages)
        {
            if (message.Contents is null)
            {
                continue;
            }

            bool hasFunctionResult = false;
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

            // Collect plain text from Tool-role messages that lack FunctionResultContent
            if (!hasFunctionResult && message.Role == ChatRole.Tool && message.Text is string text)
            {
                plainTextResults.Add(text);
            }
        }

        // Match function calls to their results using CallId or positional fallback,
        // grouping by tool name while preserving first-seen order.
        int plainTextIdx = 0;
        List<string> orderedNames = [];
        Dictionary<string, List<string>> groupedResults = new();

        foreach ((string callId, string name) in functionCalls)
        {
            if (!groupedResults.TryGetValue(name, out _))
            {
                orderedNames.Add(name);
                groupedResults[name] = [];
            }

            string? result = null;
            if (resultsByCallId.TryGetValue(callId, out string? matchedResult))
            {
                result = matchedResult;
            }
            else if (plainTextIdx < plainTextResults.Count)
            {
                result = plainTextResults[plainTextIdx++];
            }

            if (!string.IsNullOrEmpty(result))
            {
                groupedResults[name].Add(result);
            }
        }

        // Format as YAML-like block with [Tool Calls] header
        List<string> lines = ["[Tool Calls]"];
        foreach (string name in orderedNames)
        {
            List<string> results = groupedResults[name];

            lines.Add($"{name}:");
            if (results.Count > 0)
            {
                foreach (string result in results)
                {
                    lines.Add($"  - {result}");
                }
            }
        }

        return string.Join("\n", lines);
    }
}
