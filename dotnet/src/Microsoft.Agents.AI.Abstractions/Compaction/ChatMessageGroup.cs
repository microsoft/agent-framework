// Copyright (c) Microsoft. All rights reserved.

using System;

namespace Microsoft.Agents.AI.Compaction;

/// <summary>
/// Represents a contiguous range of messages in a conversation that form an atomic group.
/// Atomic groups must be kept or removed together to maintain API correctness.
/// </summary>
/// <remarks>
/// For example, an assistant message containing tool calls and the subsequent tool result messages
/// form an atomic group — removing one without the other causes API errors.
/// </remarks>
public readonly struct ChatMessageGroup : IEquatable<ChatMessageGroup>
{
    /// <summary>
    /// Initializes a new instance of the <see cref="ChatMessageGroup"/> struct.
    /// </summary>
    /// <param name="startIndex">The zero-based index of the first message in this group.</param>
    /// <param name="count">The number of messages in this group.</param>
    /// <param name="kind">The kind of this message group.</param>
    public ChatMessageGroup(int startIndex, int count, ChatMessageGroupKind kind)
    {
        this.StartIndex = startIndex;
        this.Count = count;
        this.Kind = kind;
    }

    /// <summary>
    /// Gets the zero-based index of the first message in this group within the original message list.
    /// </summary>
    public int StartIndex { get; }

    /// <summary>
    /// Gets the number of messages in this group.
    /// </summary>
    public int Count { get; }

    /// <summary>
    /// Gets the kind of this message group.
    /// </summary>
    public ChatMessageGroupKind Kind { get; }

    /// <inheritdoc/>
    public bool Equals(ChatMessageGroup other) =>
        this.StartIndex == other.StartIndex &&
        this.Count == other.Count &&
        this.Kind == other.Kind;

    /// <inheritdoc/>
    public override bool Equals(object? obj) =>
        obj is ChatMessageGroup other &&
        this.Equals(other);

    /// <inheritdoc/>
    public override int GetHashCode() => HashCode.Combine(this.StartIndex, this.Count, (int)this.Kind);

    /// <summary>Determines whether two <see cref="ChatMessageGroup"/> instances are equal.</summary>
    public static bool operator ==(ChatMessageGroup left, ChatMessageGroup right) => left.Equals(right);

    /// <summary>Determines whether two <see cref="ChatMessageGroup"/> instances are not equal.</summary>
    public static bool operator !=(ChatMessageGroup left, ChatMessageGroup right) => !left.Equals(right);
}
