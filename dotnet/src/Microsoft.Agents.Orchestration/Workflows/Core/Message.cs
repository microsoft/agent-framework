// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;

using ExecutorId = string;
// TODO: Unclear whether this should be forcibly a serializable type.
using MetadataValueT = object;
using RetryExceptionT = System.InvalidOperationException;
using TopicId = string;

namespace Microsoft.Agents.Orchestration.Workflows.Core;

/// <summary>
/// .
/// </summary>
public record MessageMetadata
{
    /// <summary>
    /// .
    /// </summary>
    public string CorrelationId { get; init; } = Guid.NewGuid().ToString();
    /// <summary>
    /// .
    /// </summary>
    public ExecutorId? SourceId { get; init; }
    /// <summary>
    /// .
    /// </summary>
    public ExecutorId? TargetId { get; init; }
    /// <summary>
    /// .
    /// </summary>
    public DateTimeOffset Timestamp { get; init; } = DateTimeOffset.UtcNow;
    /// <summary>
    /// .
    /// </summary>
    public string IsoTimestamp => this.Timestamp.ToString("o");
    /// <summary>
    /// .
    /// </summary>
    public TopicId? Topic { get; init; }
    /// <summary>
    /// .
    /// </summary>
    public int Priority { get; init; } = 0; // Higher values indicate higher priority.
    /// <summary>
    /// .
    /// </summary>
    public TimeSpan? Timeout { get; init; } = null;

    /// <summary>
    /// .
    /// </summary>
    public int Retries { get; init; } = 0;
    /// <summary>
    /// .
    /// </summary>
    public int MaxRetries { get; init; } = 3;

    /// <summary>
    /// .
    /// </summary>
    public IDictionary<string, MetadataValueT> CustomData { get; init; } = new Dictionary<string, MetadataValueT>();
}

/// <summary>
/// .
/// </summary>
/// <typeparam name="TContent"></typeparam>
public record Message<TContent>
{
    /// <summary>
    /// .
    /// </summary>
    public TContent Content { get; init; }

    /// <summary>
    /// .
    /// </summary>
    public Type ContentType => typeof(TContent);

    /// <summary>
    /// .
    /// </summary>
    public MessageMetadata Metadata { get; init; }

    /// <summary>
    /// .
    /// </summary>
    /// <param name="content"></param>
    /// <param name="metadata"></param>
    /// <exception cref="ArgumentNullException"></exception>
    public Message(TContent content, MessageMetadata metadata)
    {
        this.Content = content ?? throw new ArgumentNullException(nameof(content));
        this.Metadata = metadata ?? throw new ArgumentNullException(nameof(metadata));
    }

    /// <summary>
    /// Creates a new message instance for a new target.
    /// </summary>
    /// <param name="targetId">The identifier of the target executor to associate with the message.</param>
    /// <returns>A new <see cref="Message{TContent}"/> instance with the updated target identifier.</returns>
    public Message<TContent> WithTarget(ExecutorId targetId)
        => this with { Metadata = this.Metadata with { TargetId = targetId } };

    /// <summary>
    /// Create a copy of this message for next retry attempt.
    /// </summary>
    /// <returns>A copy of this message with incremented retry count.</returns>
    /// <exception cref="RetryExceptionT">If the maximum number of retries has been exceeded.</exception>
    public Message<TContent> WithRetry()
        => this.Metadata.Retries < this.Metadata.MaxRetries
            ? this with { Metadata = this.Metadata with { Retries = this.Metadata.Retries + 1 } }
            : throw new RetryExceptionT($"Maximum retries ({this.Metadata.MaxRetries}) exceeded for message with ID '{this.Metadata.CorrelationId}'.");
}
