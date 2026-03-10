// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI.Compaction;

/// <summary>
/// Identifies the kind of a <see cref="CompactionMessageGroup"/>.
/// </summary>
/// <remarks>
/// Message groups are used to classify logically related messages that must be kept together
/// during compaction operations. For example, an assistant message containing tool calls
/// and its corresponding tool result messages form an atomic <see cref="ToolCall"/> group.
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public enum CompactionGroupKind
{
    /// <summary>
    /// A system message group containing one or more system messages.
    /// </summary>
    System,

    /// <summary>
    /// A user message group containing a single user message.
    /// </summary>
    User,

    /// <summary>
    /// An assistant message group containing a single assistant text response (no tool calls).
    /// </summary>
    AssistantText,

    /// <summary>
    /// An atomic tool call group containing an assistant message with tool calls
    /// followed by the corresponding tool result messages.
    /// </summary>
    /// <remarks>
    /// This group must be treated as an atomic unit during compaction. Removing the assistant
    /// message without its tool results (or vice versa) will cause LLM API errors.
    /// </remarks>
    ToolCall,

#pragma warning disable IDE0001 // Simplify Names
    /// <summary>
    /// A summary message group produced by a compaction strategy (e.g., <c>SummarizationCompactionStrategy</c>).
    /// </summary>
    /// <remarks>
    /// Summary groups replace previously compacted messages with a condensed representation.
    /// They are identified by the <see cref="CompactionMessageGroup.SummaryPropertyKey"/> metadata entry
    /// on the underlying <see cref="Microsoft.Extensions.AI.ChatMessage"/>.
    /// </remarks>
#pragma warning restore IDE0001 // Simplify Names
    Summary,
}
