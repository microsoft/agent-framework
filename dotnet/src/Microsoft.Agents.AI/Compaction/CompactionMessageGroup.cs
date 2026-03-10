// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Text.Json.Serialization;
using Microsoft.Extensions.AI;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI.Compaction;

/// <summary>
/// Represents a logical group of <see cref="ChatMessage"/> instances that must be kept or removed together during compaction.
/// </summary>
/// <remarks>
/// <para>
/// Message groups ensure atomic preservation of related messages. For example, an assistant message
/// containing tool calls and its corresponding tool result messages form a <see cref="CompactionGroupKind.ToolCall"/>
/// group — removing one without the other would cause LLM API errors.
/// </para>
/// <para>
/// Groups also support exclusion semantics: a group can be marked as excluded (with an optional reason)
/// to indicate it should not be included in the messages sent to the model, while still being preserved
/// for diagnostics, storage, or later re-inclusion.
/// </para>
/// <para>
/// Each group tracks its <see cref="MessageCount"/>, <see cref="ByteCount"/>, and <see cref="TokenCount"/>
/// so that <see cref="CompactionMessageIndex"/> can efficiently aggregate totals across all or only included groups.
/// </para>
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class CompactionMessageGroup
{
    /// <summary>
    /// The <see cref="ChatMessage.AdditionalProperties"/> key used to identify a message as a compaction summary.
    /// </summary>
    /// <remarks>
    /// When this key is present with a value of <see langword="true"/>, the message is classified as
    /// <see cref="CompactionGroupKind.Summary"/> by <see cref="CompactionMessageIndex.Create"/>.
    /// </remarks>
    public static readonly string SummaryPropertyKey = "_is_summary";

    /// <summary>
    /// Initializes a new instance of the <see cref="CompactionMessageGroup"/> class.
    /// </summary>
    /// <param name="kind">The kind of message group.</param>
    /// <param name="messages">The messages in this group. The list is captured as a read-only snapshot.</param>
    /// <param name="byteCount">The total UTF-8 byte count of the text content in the messages.</param>
    /// <param name="tokenCount">The token count for the messages, computed by a tokenizer or estimated.</param>
    /// <param name="turnIndex">
    /// The user turn this group belongs to, or <see langword="null"/> for <see cref="CompactionGroupKind.System"/>.
    /// </param>
    [JsonConstructor]
    internal CompactionMessageGroup(CompactionGroupKind kind, IReadOnlyList<ChatMessage> messages, int byteCount, int tokenCount, int? turnIndex = null)
    {
        this.Kind = kind;
        this.Messages = messages;
        this.MessageCount = messages.Count;
        this.ByteCount = byteCount;
        this.TokenCount = tokenCount;
        this.TurnIndex = turnIndex;
    }

    /// <summary>
    /// Gets the kind of this message group.
    /// </summary>
    public CompactionGroupKind Kind { get; }

    /// <summary>
    /// Gets the messages in this group.
    /// </summary>
    public IReadOnlyList<ChatMessage> Messages { get; }

    /// <summary>
    /// Gets the number of messages in this group.
    /// </summary>
    public int MessageCount { get; }

    /// <summary>
    /// Gets the total UTF-8 byte count of the text content in this group's messages.
    /// </summary>
    public int ByteCount { get; }

    /// <summary>
    /// Gets the estimated or actual token count for this group's messages.
    /// </summary>
    public int TokenCount { get; }

    /// <summary>
    /// Gets user turn index this group belongs to, or <see langword="null"/> for groups
    /// that precede the first user message (e.g., system messages).  A turn index of 0
    /// corresponds with any non-system message that precedes the first user message,
    /// turn index 1 corresponds with the first user message and its subsequent non-user
    /// messages, and so on...
    /// </summary>
    /// <remarks>
    /// A turn starts with a <see cref="CompactionGroupKind.User"/> group and includes all subsequent
    /// non-user, non-system groups until the next user group or end of conversation.  System messages
    /// (<see cref="CompactionGroupKind.System"/>) are always assigned a <see langword="null"/> turn index
    /// since they never belong to a user turn.
    /// </remarks>
    public int? TurnIndex { get; }

    /// <summary>
    /// Gets or sets a value indicating whether this group is excluded from the projected message list.
    /// </summary>
    /// <remarks>
    /// Excluded groups are preserved in the collection for diagnostics or storage purposes
    /// but are not included when calling <see cref="CompactionMessageIndex.GetIncludedMessages"/>.
    /// </remarks>
    public bool IsExcluded { get; set; }

    /// <summary>
    /// Gets or sets an optional reason explaining why this group was excluded.
    /// </summary>
    public string? ExcludeReason { get; set; }
}
