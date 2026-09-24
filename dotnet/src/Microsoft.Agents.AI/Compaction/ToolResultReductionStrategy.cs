// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using Microsoft.Extensions.AI;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Compaction;

/// <summary>
/// A compaction strategy that applies per-tool reducers to individual tool results,
/// preserving the original message structure (assistant tool calls + tool result messages)
/// while transforming the result content.
/// </summary>
/// <remarks>
/// <para>
/// Unlike <see cref="ToolResultCompactionStrategy"/> which collapses entire tool call groups
/// into a single YAML-like summary, this strategy keeps the tool call/result message pairing
/// intact. Each <see cref="FunctionResultContent"/> is passed through its tool's registered
/// reducer, and the group is replaced with a structurally identical group containing the
/// reduced results.
/// </para>
/// <para>
/// This is useful when a tool returns very large results (e.g., a retrieval API returning
/// hundreds of thousands of tokens with relevance scores) that should be reduced before
/// the model sees them — even on the current turn. The reducer can deserialize the result,
/// filter, sort, and re-serialize it. These steps happen outside the framework; the framework
/// only invokes the <c>Func&lt;object?, object?&gt;</c> delegate.
/// </para>
/// <para>
/// Only <see cref="CompactionGroupKind.ToolCall"/> groups that contain at least one tool name
/// registered in <see cref="ToolResultReducers"/> are eligible. Groups with no registered tools
/// are left untouched for other strategies to handle.
/// </para>
/// <para>
/// For tools not registered in the dictionary within an otherwise eligible group, the raw
/// result text is preserved as-is.
/// </para>
/// <para>
/// <see cref="ToolResultStrategyBase.MinimumPreservedGroups"/> defaults to <c>0</c> so that
/// reducers apply to all tool results, including the current turn. Set a higher value to
/// preserve recent results at full fidelity.
/// </para>
/// <para>
/// This strategy composes naturally in a <see cref="PipelineCompactionStrategy"/>. A common
/// pattern is to place it before <see cref="ToolResultCompactionStrategy"/> — this strategy
/// reduces result content while preserving structure, then the compaction strategy collapses
/// older groups into concise summaries.
/// </para>
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class ToolResultReductionStrategy : ToolResultStrategyBase
{
    /// <summary>
    /// Initializes a new instance of the <see cref="ToolResultReductionStrategy"/> class.
    /// </summary>
    /// <param name="toolResultReducers">
    /// A dictionary mapping tool names to per-tool result reducers. Each reducer receives the
    /// <see cref="FunctionResultContent.Result"/> value for a single tool invocation and returns
    /// the transformed result. The result type matches the <c>object?</c> type of
    /// <see cref="FunctionResultContent.Result"/>.
    /// </param>
    /// <param name="trigger">
    /// The <see cref="CompactionTrigger"/> that controls when reduction proceeds.
    /// </param>
    /// <param name="minimumPreservedGroups">
    /// The minimum number of most-recent non-system message groups to preserve.
    /// Defaults to <c>0</c> so that reducers apply to all tool results including the current turn.
    /// </param>
    /// <param name="target">
    /// An optional target condition that controls when reduction stops. When <see langword="null"/>,
    /// defaults to the inverse of the <paramref name="trigger"/>.
    /// </param>
    public ToolResultReductionStrategy(
        IReadOnlyDictionary<string, Func<object?, object?>> toolResultReducers,
        CompactionTrigger trigger,
        int minimumPreservedGroups = 0,
        CompactionTrigger? target = null)
        : base(trigger, minimumPreservedGroups, target)
    {
        this.ToolResultReducers = Throw.IfNull(toolResultReducers);
    }

    /// <summary>
    /// Gets the dictionary mapping tool names to per-tool result reducers.
    /// Each reducer receives the <see cref="FunctionResultContent.Result"/> value for a single
    /// tool invocation and returns the transformed result.
    /// </summary>
    public IReadOnlyDictionary<string, Func<object?, object?>> ToolResultReducers { get; }

    /// <summary>
    /// Key used to mark tool groups that have already been reduced by this strategy,
    /// preventing re-reduction on subsequent <see cref="CompactionStrategy.CompactAsync"/> calls.
    /// </summary>
    internal const string ReducedPropertyKey = "_microsoft_agents_ai_compaction_tool_result_reduced";

    /// <inheritdoc/>
    protected override bool IsToolGroupEligible(CompactionMessageGroup group)
    {
        if (this.ToolResultReducers.Count == 0)
        {
            return false;
        }

        // Skip groups already reduced by this strategy
        foreach (ChatMessage message in group.Messages)
        {
            if (message.AdditionalProperties?.ContainsKey(ReducedPropertyKey) is true)
            {
                return false;
            }
        }

        // Build CallId → tool name mapping to verify matching FunctionResultContent exists
        Dictionary<string, string> callIdToName = [];
        foreach (ChatMessage message in group.Messages)
        {
            if (message.Contents is null)
            {
                continue;
            }

            foreach (AIContent content in message.Contents)
            {
                if (content is FunctionCallContent fcc && this.ToolResultReducers.ContainsKey(fcc.Name))
                {
                    callIdToName[fcc.CallId] = fcc.Name;
                }
            }
        }

        if (callIdToName.Count == 0)
        {
            return false;
        }

        // Verify at least one FunctionResultContent matches a registered tool call
        foreach (ChatMessage message in group.Messages)
        {
            if (message.Contents is null)
            {
                continue;
            }

            foreach (AIContent content in message.Contents)
            {
                if (content is FunctionResultContent frc
                    && frc.CallId is not null
                    && callIdToName.ContainsKey(frc.CallId))
                {
                    return true;
                }
            }
        }

        return false;
    }

    /// <inheritdoc/>
    protected override (CompactionGroupKind Kind, List<ChatMessage> Messages, string ExcludeReason)
        TransformToolGroup(CompactionMessageGroup group)
    {
        // Build a CallId → tool name mapping from the shared extraction helper
        var (functionCalls, _, _) = ExtractToolCallsAndResults(group);

        Dictionary<string, string> callIdToName = [];
        foreach ((string callId, string name) in functionCalls)
        {
            callIdToName[callId] = name;
        }

        // Rebuild messages with reduced FunctionResultContent
        List<ChatMessage> reducedMessages = [];
        foreach (ChatMessage message in group.Messages)
        {
            if (message.Contents is null || message.Contents.Count == 0)
            {
                reducedMessages.Add(message);
                continue;
            }

            bool hasReduction = false;
            List<AIContent> newContents = [];

            foreach (AIContent content in message.Contents)
            {
                if (content is FunctionResultContent frc
                    && frc.CallId is not null
                    && callIdToName.TryGetValue(frc.CallId, out string? toolName)
                    && this.ToolResultReducers.TryGetValue(toolName, out Func<object?, object?>? reducer))
                {
                    newContents.Add(CloneWithReducedResult(frc, reducer(frc.Result)));
                    hasReduction = true;
                }
                else
                {
                    newContents.Add(content);
                }
            }

            if (hasReduction)
            {
                ChatMessage reducedMessage = message.Clone();
                reducedMessage.Contents = newContents;
                (reducedMessage.AdditionalProperties ??= [])[ReducedPropertyKey] = true;
                reducedMessages.Add(reducedMessage);
            }
            else
            {
                reducedMessages.Add(message.Clone());
            }
        }

        return (CompactionGroupKind.ToolCall, reducedMessages, $"Reduced by {nameof(ToolResultReductionStrategy)}");
    }

    /// <summary>
    /// Creates a new <see cref="FunctionResultContent"/> with the reduced result while
    /// preserving all metadata (<see cref="AIContent.RawRepresentation"/>,
    /// <see cref="AIContent.Annotations"/>, <see cref="AIContent.AdditionalProperties"/>)
    /// from the original.
    /// </summary>
    private static FunctionResultContent CloneWithReducedResult(FunctionResultContent original, object? reducedResult)
    {
        var clone = new FunctionResultContent(original.CallId, reducedResult)
        {
            RawRepresentation = original.RawRepresentation,
        };

        if (original.Annotations is { Count: > 0 })
        {
            foreach (var annotation in original.Annotations)
            {
                (clone.Annotations ??= []).Add(annotation);
            }
        }

        if (original.AdditionalProperties is { Count: > 0 })
        {
            foreach (var kvp in original.AdditionalProperties)
            {
                (clone.AdditionalProperties ??= [])[kvp.Key] = kvp.Value;
            }
        }

        return clone;
    }
}
