// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;
using OpenAI.Responses;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Responses.Model;

/// <summary>
/// Abstract base class for all streaming response events in the OpenAI Responses API.
/// Provides common properties shared across all streaming event types.
/// </summary>
[JsonPolymorphic(UnknownDerivedTypeHandling = JsonUnknownDerivedTypeHandling.FailSerialization)]
[JsonDerivedType(typeof(StreamingOutputItemAddedResponse), StreamingOutputItemAddedResponse.EventType)]
[JsonDerivedType(typeof(StreamingOutputItemDoneResponse), StreamingOutputItemDoneResponse.EventType)]
[JsonDerivedType(typeof(StreamingCreatedResponse), StreamingCreatedResponse.EventType)]
[JsonDerivedType(typeof(StreamingCompletedResponse), StreamingCompletedResponse.EventType)]
internal abstract class StreamingResponseEventBase
{
    /// <summary>
    /// Gets or sets the type identifier for the streaming response event.
    /// This property is used to discriminate between different event types during serialization.
    /// </summary>
    [JsonPropertyName("type")]
    public string Type { get; set; }

    /// <summary>
    /// Gets or sets the sequence number of this event in the streaming response.
    /// Events are numbered sequentially starting from 1 to maintain ordering.
    /// </summary>
    [JsonPropertyName("sequence_number")]
    public int SequenceNumber { get; set; }

    /// <summary>
    /// Initializes a new instance of the <see cref="StreamingResponseEventBase"/> class.
    /// </summary>
    /// <param name="type">The type identifier for this streaming response event.</param>
    /// <param name="sequenceNumber">The sequence number of this event in the streaming response.</param>
    [JsonConstructor]
    public StreamingResponseEventBase(string type, int sequenceNumber)
    {
        this.Type = type;
        this.SequenceNumber = sequenceNumber;
    }
}

/// <summary>
/// Represents a streaming response event indicating that a new output item has been added to the response.
/// This event is sent when the AI agent produces a new piece of content during streaming.
/// </summary>
internal sealed class StreamingOutputItemAddedResponse : StreamingResponseEventBase
{
    /// <summary>
    /// The constant event type identifier for output item added events.
    /// </summary>
    public const string EventType = "response.output_item.added";

    /// <summary>
    /// Initializes a new instance of the <see cref="StreamingOutputItemAddedResponse"/> class.
    /// </summary>
    /// <param name="sequenceNumber">The sequence number of this event in the streaming response.</param>
    public StreamingOutputItemAddedResponse(int sequenceNumber) : base(EventType, sequenceNumber)
    {
    }

    /// <summary>
    /// Gets or sets the index of the output in the response where this item was added.
    /// Multiple outputs can exist in a single response, and this identifies which one.
    /// </summary>
    [JsonPropertyName("output_index")]
    public int OutputIndex { get; set; }

    /// <summary>
    /// Gets or sets the response item that was added to the output.
    /// This contains the actual content or data produced by the AI agent.
    /// </summary>
    [JsonPropertyName("item")]
    public ResponseItem? Item { get; set; }
}

/// <summary>
/// Represents a streaming response event indicating that an output item has been completed.
/// This event is sent when the AI agent finishes producing a particular piece of content.
/// </summary>
internal sealed class StreamingOutputItemDoneResponse : StreamingResponseEventBase
{
    /// <summary>
    /// The constant event type identifier for output item done events.
    /// </summary>
    public const string EventType = "response.output_item.done";

    /// <summary>
    /// Initializes a new instance of the <see cref="StreamingOutputItemDoneResponse"/> class.
    /// </summary>
    /// <param name="sequenceNumber">The sequence number of this event in the streaming response.</param>
    public StreamingOutputItemDoneResponse(int sequenceNumber) : base(EventType, sequenceNumber)
    {
    }

    /// <summary>
    /// Gets or sets the index of the output in the response where this item was completed.
    /// This corresponds to the same output index from the associated <see cref="StreamingOutputItemAddedResponse"/>.
    /// </summary>
    [JsonPropertyName("output_index")]
    public int OutputIndex { get; set; }

    /// <summary>
    /// Gets or sets the completed response item.
    /// This contains the final version of the content produced by the AI agent.
    /// </summary>
    [JsonPropertyName("item")]
    public ResponseItem? Item { get; set; }
}

/// <summary>
/// Represents a streaming response event indicating that a new response has been created and streaming has begun.
/// This is typically the first event sent in a streaming response sequence.
/// </summary>
internal sealed class StreamingCreatedResponse : StreamingResponseEventBase
{
    /// <summary>
    /// The constant event type identifier for response created events.
    /// </summary>
    public const string EventType = "response.created";

    /// <summary>
    /// Initializes a new instance of the <see cref="StreamingCreatedResponse"/> class.
    /// </summary>
    /// <param name="sequenceNumber">The sequence number of this event in the streaming response.</param>
    public StreamingCreatedResponse(int sequenceNumber) : base(EventType, sequenceNumber)
    {
    }

    /// <summary>
    /// Gets or sets the OpenAI response object that was created.
    /// This contains metadata about the response including ID, creation timestamp, and other properties.
    /// </summary>
    [JsonPropertyName("response")]
    public required OpenAIResponse Response { get; set; }
}

/// <summary>
/// Represents a streaming response event indicating that the response has been completed.
/// This is typically the last event sent in a streaming response sequence.
/// </summary>
internal sealed class StreamingCompletedResponse : StreamingResponseEventBase
{
    /// <summary>
    /// The constant event type identifier for response completed events.
    /// </summary>
    public const string EventType = "response.completed";

    /// <summary>
    /// Initializes a new instance of the <see cref="StreamingCompletedResponse"/> class.
    /// </summary>
    /// <param name="sequenceNumber">The sequence number of this event in the streaming response.</param>
    public StreamingCompletedResponse(int sequenceNumber) : base(EventType, sequenceNumber)
    {
    }

    /// <summary>
    /// Gets or sets the completed OpenAI response object.
    /// This contains the final state of the response including all generated content and metadata.
    /// </summary>
    [JsonPropertyName("response")]
    public required OpenAIResponse Response { get; set; }
}
