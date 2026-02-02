// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.DurableTask.Workflows;

/// <summary>
/// Represents a message envelope for durable workflow message passing.
/// </summary>
/// <remarks>
/// <para>
/// This is the durable equivalent of <c>MessageEnvelope</c> in the in-process runner.
/// Unlike the in-process version which holds native .NET objects, this envelope
/// contains serialized JSON strings suitable for Durable Task activities.
/// </para>
/// </remarks>
internal sealed class DurableMessageEnvelope
{
    /// <summary>
    /// Gets or sets the serialized JSON message content.
    /// </summary>
    public required string Message { get; init; }

    /// <summary>
    /// Gets or sets the full type name of the message for deserialization.
    /// </summary>
    public string? InputTypeName { get; init; }

    /// <summary>
    /// Gets or sets the ID of the executor that produced this message.
    /// </summary>
    /// <remarks>
    /// Used for tracing and debugging. Null for initial workflow input.
    /// </remarks>
    public string? SourceExecutorId { get; init; }

    /// <summary>
    /// Creates a new message envelope.
    /// </summary>
    /// <param name="message">The serialized JSON message content.</param>
    /// <param name="inputTypeName">The full type name of the message for deserialization.</param>
    /// <param name="sourceExecutorId">The ID of the executor that produced this message, or null for initial input.</param>
    /// <returns>A new <see cref="DurableMessageEnvelope"/> instance.</returns>
    internal static DurableMessageEnvelope Create(string message, string? inputTypeName, string? sourceExecutorId = null)
    {
        return new DurableMessageEnvelope
        {
            Message = message,
            InputTypeName = inputTypeName,
            SourceExecutorId = sourceExecutorId
        };
    }
}
