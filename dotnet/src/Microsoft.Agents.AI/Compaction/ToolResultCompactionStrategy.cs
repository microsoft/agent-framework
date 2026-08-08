// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using Microsoft.Extensions.AI;
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
/// A custom <see cref="ToolCallFormatter"/> can be supplied to override the default YAML-like
/// summary format. The formatter receives the <see cref="CompactionMessageGroup"/> being collapsed
/// and must return the replacement summary string. <see cref="DefaultToolCallFormatter"/> is the
/// built-in default and can be reused inside a custom formatter when needed.
/// </para>
/// <para>
/// <see cref="ToolResultStrategyBase.MinimumPreservedGroups"/> is a hard floor: even if the
/// <see cref="CompactionStrategy.Target"/> has not been reached, compaction will not touch the last
/// <see cref="ToolResultStrategyBase.MinimumPreservedGroups"/> non-system groups.
/// </para>
/// <para>
/// The <see cref="CompactionTrigger"/> predicate controls when compaction proceeds. Use
/// <see cref="CompactionTriggers"/> for common trigger conditions such as token thresholds.
/// </para>
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class ToolResultCompactionStrategy : ToolResultStrategyBase
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
    public ToolResultCompactionStrategy(
        CompactionTrigger trigger,
        int minimumPreservedGroups = DefaultMinimumPreserved,
        CompactionTrigger? target = null)
        : base(trigger, minimumPreservedGroups, target)
    {
    }

    /// <summary>
    /// An optional custom formatter that converts a <see cref="CompactionMessageGroup"/> into a summary string.
    /// When <see langword="null"/>, <see cref="DefaultToolCallFormatter"/> is used, which produces a YAML-like
    /// block listing each tool name and its results.
    /// </summary>
    public Func<CompactionMessageGroup, string>? ToolCallFormatter { get; init; }

    /// <inheritdoc/>
    protected override (CompactionGroupKind Kind, List<ChatMessage> Messages, string ExcludeReason)
        TransformToolGroup(CompactionMessageGroup group)
    {
        string summary = (this.ToolCallFormatter ?? DefaultToolCallFormatter).Invoke(group);

        ChatMessage summaryMessage = new(ChatRole.Assistant, summary);
        (summaryMessage.AdditionalProperties ??= [])[CompactionMessageGroup.SummaryPropertyKey] = true;

        return (CompactionGroupKind.Summary, [summaryMessage], $"Collapsed by {nameof(ToolResultCompactionStrategy)}");
    }

    /// <summary>
    /// The default formatter that produces a YAML-like summary of tool call groups, including tool names,
    /// results, and deduplication counts for repeated tool names.
    /// </summary>
    /// <remarks>
    /// This is the formatter used when no custom <see cref="ToolCallFormatter"/> is supplied.
    /// It can be referenced directly in a custom formatter to augment or wrap the default output.
    /// </remarks>
    public static string DefaultToolCallFormatter(CompactionMessageGroup group)
    {
        var (functionCalls, resultsByCallId, plainTextResults) = ExtractToolCallsAndResults(group);

        // Match function calls to their results using CallId or positional fallback,
        // grouping by tool name while preserving first-seen order.
        int plainTextIdx = 0;
        List<string> orderedNames = [];
        Dictionary<string, List<string>> groupedResults = [];

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
