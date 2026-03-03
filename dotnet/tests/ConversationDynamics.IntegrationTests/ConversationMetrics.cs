// Copyright (c) Microsoft. All rights reserved.

namespace ConversationDynamics.IntegrationTests;

/// <summary>
/// Captures the size characteristics of a conversation context at a specific point in time.
/// </summary>
public sealed class ConversationMetrics
{
    /// <summary>
    /// Gets the number of messages in the conversation context.
    /// </summary>
    public required int MessageCount { get; init; }

    /// <summary>
    /// Gets the approximate serialized size of the conversation context in bytes.
    /// This serves as a proxy for context window consumption.
    /// </summary>
    public required long SerializedSizeBytes { get; init; }

    /// <inheritdoc />
    public override string ToString() =>
        $"Messages={MessageCount}, Size={SerializedSizeBytes}B";
}
