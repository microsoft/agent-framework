// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Responses.Models;

/// <summary>
/// Abstract base class for all streaming response events in the OpenAI Responses API.
/// Provides common properties shared across all streaming event types.
/// </summary>
[JsonPolymorphic(TypeDiscriminatorPropertyName = "type", UnknownDerivedTypeHandling = JsonUnknownDerivedTypeHandling.FailSerialization)]
[JsonDerivedType(typeof(StreamingResponseCreated), StreamingResponseCreated.EventType)]
[JsonDerivedType(typeof(StreamingResponseInProgress), StreamingResponseInProgress.EventType)]
[JsonDerivedType(typeof(StreamingResponseCompleted), StreamingResponseCompleted.EventType)]
[JsonDerivedType(typeof(StreamingResponseIncomplete), StreamingResponseIncomplete.EventType)]
[JsonDerivedType(typeof(StreamingResponseFailed), StreamingResponseFailed.EventType)]
[JsonDerivedType(typeof(StreamingOutputItemAdded), StreamingOutputItemAdded.EventType)]
[JsonDerivedType(typeof(StreamingOutputItemDone), StreamingOutputItemDone.EventType)]
[JsonDerivedType(typeof(StreamingContentPartAdded), StreamingContentPartAdded.EventType)]
[JsonDerivedType(typeof(StreamingContentPartDone), StreamingContentPartDone.EventType)]
[JsonDerivedType(typeof(StreamingOutputTextDelta), StreamingOutputTextDelta.EventType)]
[JsonDerivedType(typeof(StreamingOutputTextDone), StreamingOutputTextDone.EventType)]
[JsonDerivedType(typeof(StreamingFunctionCallArgumentsDelta), StreamingFunctionCallArgumentsDelta.EventType)]
[JsonDerivedType(typeof(StreamingFunctionCallArgumentsDone), StreamingFunctionCallArgumentsDone.EventType)]
[JsonDerivedType(typeof(StreamingReasoningSummaryTextDelta), StreamingReasoningSummaryTextDelta.EventType)]
[JsonDerivedType(typeof(StreamingReasoningSummaryTextDone), StreamingReasoningSummaryTextDone.EventType)]
internal abstract record StreamingResponseEvent
{
    /// <summary>
    /// Gets the type identifier for the streaming response event.
    /// This property is used to discriminate between different event types during serialization.
    /// </summary>
    [JsonIgnore]
    public abstract string Type { get; }

    /// <summary>
    /// Gets the sequence number of this event in the streaming response.
    /// Events are numbered sequentially starting from 1 to maintain ordering.
    /// </summary>
    [JsonPropertyName("sequence_number")]
    public int SequenceNumber { get; init; }
}

/// <summary>
/// Represents a streaming response event indicating that a new response has been created and streaming has begun.
/// This is typically the first event sent in a streaming response sequence.
/// </summary>
internal sealed record StreamingResponseCreated : StreamingResponseEvent
{
    /// <summary>
    /// The constant event type identifier for response created events.
    /// </summary>
    public const string EventType = "response.created";

    /// <inheritdoc/>
    [JsonIgnore]
    public override string Type => EventType;

    /// <summary>
    /// Gets or sets the response object that was created.
    /// This contains metadata about the response including ID, creation timestamp, and other properties.
    /// </summary>
    [JsonPropertyName("response")]
    public required Response Response { get; init; }
}

/// <summary>
/// Represents a streaming response event indicating that the response is in progress.
/// </summary>
internal sealed record StreamingResponseInProgress : StreamingResponseEvent
{
    /// <summary>
    /// The constant event type identifier for response in progress events.
    /// </summary>
    public const string EventType = "response.in_progress";

    /// <inheritdoc/>
    [JsonIgnore]
    public override string Type => EventType;

    /// <summary>
    /// Gets or sets the response object that is in progress.
    /// </summary>
    [JsonPropertyName("response")]
    public required Response Response { get; init; }
}

/// <summary>
/// Represents a streaming response event indicating that the response has been completed.
/// This is typically the last event sent in a streaming response sequence.
/// </summary>
internal sealed record StreamingResponseCompleted : StreamingResponseEvent
{
    /// <summary>
    /// The constant event type identifier for response completed events.
    /// </summary>
    public const string EventType = "response.completed";

    /// <inheritdoc/>
    [JsonIgnore]
    public override string Type => EventType;

    /// <summary>
    /// Gets or sets the completed response object.
    /// This contains the final state of the response including all generated content and metadata.
    /// </summary>
    [JsonPropertyName("response")]
    public required Response Response { get; init; }
}

/// <summary>
/// Represents a streaming response event indicating that the response finished as incomplete.
/// </summary>
internal sealed record StreamingResponseIncomplete : StreamingResponseEvent
{
    /// <summary>
    /// The constant event type identifier for response incomplete events.
    /// </summary>
    public const string EventType = "response.incomplete";

    /// <inheritdoc/>
    [JsonIgnore]
    public override string Type => EventType;

    /// <summary>
    /// Gets or sets the incomplete response object.
    /// </summary>
    [JsonPropertyName("response")]
    public required Response Response { get; init; }
}

/// <summary>
/// Represents a streaming response event indicating that the response has failed.
/// </summary>
internal sealed record StreamingResponseFailed : StreamingResponseEvent
{
    /// <summary>
    /// The constant event type identifier for response failed events.
    /// </summary>
    public const string EventType = "response.failed";

    /// <inheritdoc/>
    [JsonIgnore]
    public override string Type => EventType;

    /// <summary>
    /// Gets or sets the failed response object.
    /// </summary>
    [JsonPropertyName("response")]
    public required Response Response { get; init; }
}

/// <summary>
/// Represents a streaming response event indicating that a new output item has been added to the response.
/// This event is sent when the AI agent produces a new piece of content during streaming.
/// </summary>
internal sealed record StreamingOutputItemAdded : StreamingResponseEvent
{
    /// <summary>
    /// The constant event type identifier for output item added events.
    /// </summary>
    public const string EventType = "response.output_item.added";

    /// <inheritdoc/>
    [JsonIgnore]
    public override string Type => EventType;

    /// <summary>
    /// Gets or sets the index of the output in the response where this item was added.
    /// Multiple outputs can exist in a single response, and this identifies which one.
    /// </summary>
    [JsonPropertyName("output_index")]
    public int OutputIndex { get; init; }

    /// <summary>
    /// Gets or sets the output item that was added.
    /// This contains the actual content or data produced by the AI agent.
    /// </summary>
    [JsonPropertyName("item")]
    public required ItemResource Item { get; init; }
}

/// <summary>
/// Represents a streaming response event indicating that an output item has been completed.
/// This event is sent when the AI agent finishes producing a particular piece of content.
/// </summary>
internal sealed record StreamingOutputItemDone : StreamingResponseEvent
{
    /// <summary>
    /// The constant event type identifier for output item done events.
    /// </summary>
    public const string EventType = "response.output_item.done";

    /// <inheritdoc/>
    [JsonIgnore]
    public override string Type => EventType;

    /// <summary>
    /// Gets or sets the index of the output in the response where this item was completed.
    /// This corresponds to the same output index from the associated <see cref="StreamingOutputItemAdded"/>.
    /// </summary>
    [JsonPropertyName("output_index")]
    public int OutputIndex { get; init; }

    /// <summary>
    /// Gets or sets the completed output item.
    /// This contains the final version of the content produced by the AI agent.
    /// </summary>
    [JsonPropertyName("item")]
    public required ItemResource Item { get; init; }
}

/// <summary>
/// Represents a streaming response event indicating that a new content part has been added to an output item.
/// </summary>
internal sealed record StreamingContentPartAdded : StreamingResponseEvent
{
    /// <summary>
    /// The constant event type identifier for content part added events.
    /// </summary>
    public const string EventType = "response.content_part.added";

    /// <inheritdoc/>
    [JsonIgnore]
    public override string Type => EventType;

    /// <summary>
    /// Gets or sets the item ID.
    /// </summary>
    [JsonPropertyName("item_id")]
    public required string ItemId { get; init; }

    /// <summary>
    /// Gets or sets the output index.
    /// </summary>
    [JsonPropertyName("output_index")]
    public int OutputIndex { get; init; }

    /// <summary>
    /// Gets or sets the content index.
    /// </summary>
    [JsonPropertyName("content_index")]
    public int ContentIndex { get; init; }

    /// <summary>
    /// Gets or sets the content part that was added.
    /// </summary>
    [JsonPropertyName("part")]
    public required ItemContent Part { get; init; }
}

/// <summary>
/// Represents a streaming response event indicating that a content part has been completed.
/// </summary>
internal sealed record StreamingContentPartDone : StreamingResponseEvent
{
    /// <summary>
    /// The constant event type identifier for content part done events.
    /// </summary>
    public const string EventType = "response.content_part.done";

    /// <inheritdoc/>
    [JsonIgnore]
    public override string Type => EventType;

    /// <summary>
    /// Gets or sets the item ID.
    /// </summary>
    [JsonPropertyName("item_id")]
    public required string ItemId { get; init; }

    /// <summary>
    /// Gets or sets the output index.
    /// </summary>
    [JsonPropertyName("output_index")]
    public int OutputIndex { get; init; }

    /// <summary>
    /// Gets or sets the content index.
    /// </summary>
    [JsonPropertyName("content_index")]
    public int ContentIndex { get; init; }

    /// <summary>
    /// Gets or sets the completed content part.
    /// </summary>
    [JsonPropertyName("part")]
    public required ItemContent Part { get; init; }
}

/// <summary>
/// Represents a streaming response event containing a text delta (incremental text chunk).
/// </summary>
internal sealed record StreamingOutputTextDelta : StreamingResponseEvent
{
    /// <summary>
    /// The constant event type identifier for output text delta events.
    /// </summary>
    public const string EventType = "response.output_text.delta";

    /// <inheritdoc/>
    [JsonIgnore]
    public override string Type => EventType;

    /// <summary>
    /// Gets or sets the item ID.
    /// </summary>
    [JsonPropertyName("item_id")]
    public required string ItemId { get; init; }

    /// <summary>
    /// Gets or sets the output index.
    /// </summary>
    [JsonPropertyName("output_index")]
    public int OutputIndex { get; init; }

    /// <summary>
    /// Gets or sets the content index.
    /// </summary>
    [JsonPropertyName("content_index")]
    public int ContentIndex { get; init; }

    /// <summary>
    /// Gets or sets the text delta (incremental chunk of text).
    /// </summary>
    [JsonPropertyName("delta")]
    public required string Delta { get; init; }

    /// <summary>
    /// Gets or sets the log probability information for the output tokens.
    /// </summary>
    [JsonPropertyName("logprobs")]
    public IList<JsonElement> Logprobs { get; init; } = [];
}

/// <summary>
/// Represents a streaming response event indicating that output text has been completed.
/// </summary>
internal sealed record StreamingOutputTextDone : StreamingResponseEvent
{
    /// <summary>
    /// The constant event type identifier for output text done events.
    /// </summary>
    public const string EventType = "response.output_text.done";

    /// <inheritdoc/>
    [JsonIgnore]
    public override string Type => EventType;

    /// <summary>
    /// Gets or sets the item ID.
    /// </summary>
    [JsonPropertyName("item_id")]
    public required string ItemId { get; init; }

    /// <summary>
    /// Gets or sets the output index.
    /// </summary>
    [JsonPropertyName("output_index")]
    public int OutputIndex { get; init; }

    /// <summary>
    /// Gets or sets the content index.
    /// </summary>
    [JsonPropertyName("content_index")]
    public int ContentIndex { get; init; }

    /// <summary>
    /// Gets or sets the complete text.
    /// </summary>
    [JsonPropertyName("text")]
    public required string Text { get; init; }
}

/// <summary>
/// Represents a streaming response event containing a function call arguments delta.
/// </summary>
internal sealed record StreamingFunctionCallArgumentsDelta : StreamingResponseEvent
{
    /// <summary>
    /// The constant event type identifier for function call arguments delta events.
    /// </summary>
    public const string EventType = "response.function_call_arguments.delta";

    /// <inheritdoc/>
    [JsonIgnore]
    public override string Type => EventType;

    /// <summary>
    /// Gets or sets the item ID.
    /// </summary>
    [JsonPropertyName("item_id")]
    public required string ItemId { get; init; }

    /// <summary>
    /// Gets or sets the output index.
    /// </summary>
    [JsonPropertyName("output_index")]
    public int OutputIndex { get; init; }

    /// <summary>
    /// Gets or sets the function arguments delta.
    /// </summary>
    [JsonPropertyName("delta")]
    public required string Delta { get; init; }
}

/// <summary>
/// Represents a streaming response event indicating that function call arguments are complete.
/// </summary>
internal sealed record StreamingFunctionCallArgumentsDone : StreamingResponseEvent
{
    /// <summary>
    /// The constant event type identifier for function call arguments done events.
    /// </summary>
    public const string EventType = "response.function_call_arguments.done";

    /// <inheritdoc/>
    [JsonIgnore]
    public override string Type => EventType;

    /// <summary>
    /// Gets or sets the item ID.
    /// </summary>
    [JsonPropertyName("item_id")]
    public required string ItemId { get; init; }

    /// <summary>
    /// Gets or sets the output index.
    /// </summary>
    [JsonPropertyName("output_index")]
    public int OutputIndex { get; init; }

    /// <summary>
    /// Gets or sets the complete function arguments.
    /// </summary>
    [JsonPropertyName("arguments")]
    public required string Arguments { get; init; }
}

/// <summary>
/// Represents a streaming response event containing a reasoning summary text delta (incremental text chunk).
/// </summary>
internal sealed record StreamingReasoningSummaryTextDelta : StreamingResponseEvent
{
    /// <summary>
    /// The constant event type identifier for reasoning summary text delta events.
    /// </summary>
    public const string EventType = "response.reasoning_summary_text.delta";

    /// <inheritdoc/>
    [JsonIgnore]
    public override string Type => EventType;

    /// <summary>
    /// Gets or sets the item ID this summary text delta is associated with.
    /// </summary>
    [JsonPropertyName("item_id")]
    public required string ItemId { get; init; }

    /// <summary>
    /// Gets or sets the output index.
    /// </summary>
    [JsonPropertyName("output_index")]
    public int OutputIndex { get; init; }

    /// <summary>
    /// Gets or sets the index of the summary part within the reasoning summary.
    /// </summary>
    [JsonPropertyName("summary_index")]
    public int SummaryIndex { get; init; }

    /// <summary>
    /// Gets or sets the text delta that was added to the summary.
    /// </summary>
    [JsonPropertyName("delta")]
    public required string Delta { get; init; }
}

/// <summary>
/// Represents a streaming response event indicating that reasoning summary text has been completed.
/// </summary>
internal sealed record StreamingReasoningSummaryTextDone : StreamingResponseEvent
{
    /// <summary>
    /// The constant event type identifier for reasoning summary text done events.
    /// </summary>
    public const string EventType = "response.reasoning_summary_text.done";

    /// <inheritdoc/>
    [JsonIgnore]
    public override string Type => EventType;

    /// <summary>
    /// Gets or sets the item ID this summary text is associated with.
    /// </summary>
    [JsonPropertyName("item_id")]
    public required string ItemId { get; init; }

    /// <summary>
    /// Gets or sets the output index.
    /// </summary>
    [JsonPropertyName("output_index")]
    public int OutputIndex { get; init; }

    /// <summary>
    /// Gets or sets the index of the summary part within the reasoning summary.
    /// </summary>
    [JsonPropertyName("summary_index")]
    public int SummaryIndex { get; init; }

    /// <summary>
    /// Gets or sets the full text of the completed reasoning summary.
    /// </summary>
    [JsonPropertyName("text")]
    public required string Text { get; init; }
}
