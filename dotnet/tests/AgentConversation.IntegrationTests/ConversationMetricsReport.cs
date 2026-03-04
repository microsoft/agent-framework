// Copyright (c) Microsoft. All rights reserved.

namespace AgentConversation.IntegrationTests;

/// <summary>
/// Captures the before-and-after <see cref="ConversationMetrics"/> for a single test case run,
/// enabling comparison and reporting of context size changes.
/// </summary>
public sealed class ConversationMetricsReport
{
    /// <summary>
    /// Gets the metrics captured before the agent steps were executed.
    /// </summary>
    public required ConversationMetrics Before { get; init; }

    /// <summary>
    /// Gets the metrics captured after the agent steps were executed.
    /// </summary>
    public required ConversationMetrics After { get; init; }

    /// <summary>
    /// Gets the change in message count between <see cref="Before"/> and <see cref="After"/>.
    /// A positive value means messages were added; a negative value means compaction removed messages.
    /// </summary>
    public int MessageCountDelta => After.MessageCount - Before.MessageCount;

    /// <summary>
    /// Gets the change in serialized size in bytes between <see cref="Before"/> and <see cref="After"/>.
    /// </summary>
    public long SizeDeltaBytes => After.SerializedSizeBytes - Before.SerializedSizeBytes;

    /// <inheritdoc />
    public override string ToString() =>
        $"Before=[{Before}] After=[{After}] Delta=[Messages={MessageCountDelta:+#;-#;0}, Size={SizeDeltaBytes:+#;-#;0}B]";
}
