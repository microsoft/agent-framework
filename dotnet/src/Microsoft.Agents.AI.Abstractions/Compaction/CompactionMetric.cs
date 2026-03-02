// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;

namespace Microsoft.Agents.AI.Compaction;

/// <summary>
/// Immutable snapshot of conversation metrics used for compaction trigger evaluation and reporting.
/// </summary>
public sealed class CompactionMetric
{
    /// <summary>
    /// Gets the estimated token count across all messages.
    /// </summary>
    public int TokenCount { get; init; }

    /// <summary>
    /// Gets the total serialized byte count of all messages.
    /// </summary>
    public long ByteCount { get; init; }

#pragma warning disable IDE0001 // Simplify Names
    /// <summary>
    /// Gets the total number of <see cref="Microsoft.Extensions.AI.ChatMessage"/> objects.
    /// </summary>
#pragma warning restore IDE0001 // Simplify Names
    public int MessageCount { get; init; }

    /// <summary>
    /// Gets the number of tool/function call content items across all messages.
    /// </summary>
    public int ToolCallCount { get; init; }

    /// <summary>
    /// Gets the number of user turns. A user turn is a user message together with the full
    /// set of agent responses (including tool calls and results) before the next user input.
    /// </summary>
    public int UserTurnCount { get; init; }

    /// <summary>
    /// Gets the atomic message group index for the analyzed messages.
    /// Each group represents a contiguous range of messages that must be kept or removed together.
    /// </summary>
    public IReadOnlyList<ChatMessageGroup> Groups { get; init; } = [];
}
