// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Text.Json;
using System.Text.Json.Serialization;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses.Converters;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Responses.Models;

/// <summary>
/// Base class for all item resources (output items from a response).
/// </summary>
[JsonPolymorphic(TypeDiscriminatorPropertyName = "type", UnknownDerivedTypeHandling = JsonUnknownDerivedTypeHandling.FailSerialization)]
[JsonDerivedType(typeof(ResponsesAssistantMessageItemResource), "message")]
[JsonDerivedType(typeof(FunctionToolCallItemResource), "function")]
[JsonDerivedType(typeof(FunctionToolCallOutputItemResource), "function_call_output")]
internal abstract record ItemResource
{
    /// <summary>
    /// The unique identifier for the item.
    /// </summary>
    [JsonPropertyName("id")]
    public string Id { get; init; } = string.Empty;

    /// <summary>
    /// The type of the item.
    /// </summary>
    [JsonIgnore]
    public abstract string Type { get; }
}

/// <summary>
/// An assistant message item resource.
/// </summary>
internal sealed record ResponsesAssistantMessageItemResource : ItemResource
{
    /// <inheritdoc/>
    public override string Type => "message";

    /// <summary>
    /// Initializes a new instance of the <see cref="ResponsesAssistantMessageItemResource"/> class.
    /// </summary>
    /// <param name="id">The unique identifier for the item.</param>
    /// <param name="status">The status of the message.</param>
    /// <param name="content">The content of the message.</param>
    public ResponsesAssistantMessageItemResource(string id, ResponsesMessageItemResourceStatus status, IList<ItemContent> content)
    {
        this.Id = id;
        this.Status = status;
        this.Content = content;
    }

    /// <summary>
    /// The status of the message.
    /// </summary>
    [JsonPropertyName("status")]
    public ResponsesMessageItemResourceStatus Status { get; init; }

    /// <summary>
    /// The role of the message sender.
    /// </summary>
    [JsonPropertyName("role")]
    public ChatRole Role { get; init; } = ChatRole.Assistant;

    /// <summary>
    /// The content of the message.
    /// </summary>
    [JsonPropertyName("content")]
    public IList<ItemContent> Content { get; init; }
}

/// <summary>
/// A function tool call item resource.
/// </summary>
internal sealed record FunctionToolCallItemResource : ItemResource
{
    /// <inheritdoc/>
    public override string Type => "function";

    /// <summary>
    /// Initializes a new instance of the <see cref="FunctionToolCallItemResource"/> class.
    /// </summary>
    /// <param name="id">The unique identifier for the item.</param>
    /// <param name="status">The status of the function call.</param>
    /// <param name="callId">The call ID of the function.</param>
    /// <param name="name">The name of the function.</param>
    /// <param name="arguments">The arguments to the function as a JSON string.</param>
    public FunctionToolCallItemResource(string id, FunctionToolCallItemResourceStatus status, string callId, string name, string arguments)
    {
        this.Id = id;
        this.Status = status;
        this.CallId = callId;
        this.Name = name;
        this.Arguments = arguments;
    }

    /// <summary>
    /// The status of the function call.
    /// </summary>
    [JsonPropertyName("status")]
    public FunctionToolCallItemResourceStatus Status { get; init; }

    /// <summary>
    /// The call ID of the function.
    /// </summary>
    [JsonPropertyName("call_id")]
    public string CallId { get; init; }

    /// <summary>
    /// The name of the function.
    /// </summary>
    [JsonPropertyName("name")]
    public string Name { get; init; }

    /// <summary>
    /// The arguments to the function as a JSON string.
    /// </summary>
    [JsonPropertyName("arguments")]
    public string Arguments { get; init; }
}

/// <summary>
/// A function tool call output item resource.
/// </summary>
internal sealed record FunctionToolCallOutputItemResource : ItemResource
{
    /// <inheritdoc/>
    public override string Type => "function_call_output";

    /// <summary>
    /// Initializes a new instance of the <see cref="FunctionToolCallOutputItemResource"/> class.
    /// </summary>
    /// <param name="id">The unique identifier for the item.</param>
    /// <param name="status">The status of the function call output.</param>
    /// <param name="callId">The call ID of the function.</param>
    /// <param name="output">The output of the function as a JSON string.</param>
    public FunctionToolCallOutputItemResource(string id, FunctionToolCallOutputItemResourceStatus status, string callId, string output)
    {
        this.Id = id;
        this.Status = status;
        this.CallId = callId;
        this.Output = output;
    }

    /// <summary>
    /// The status of the function call output.
    /// </summary>
    [JsonPropertyName("status")]
    public FunctionToolCallOutputItemResourceStatus Status { get; init; }

    /// <summary>
    /// The call ID of the function.
    /// </summary>
    [JsonPropertyName("call_id")]
    public string CallId { get; init; }

    /// <summary>
    /// The output of the function as a JSON string.
    /// </summary>
    [JsonPropertyName("output")]
    public string Output { get; init; }
}

/// <summary>
/// The status of a message item resource.
/// </summary>
[JsonConverter(typeof(SnakeCaseEnumConverter<ResponsesMessageItemResourceStatus>))]
public enum ResponsesMessageItemResourceStatus
{
    /// <summary>
    /// The message is completed.
    /// </summary>
    Completed,

    /// <summary>
    /// The message is in progress.
    /// </summary>
    InProgress,

    /// <summary>
    /// The message is incomplete.
    /// </summary>
    Incomplete
}

/// <summary>
/// The status of a function tool call item resource.
/// </summary>
[JsonConverter(typeof(SnakeCaseEnumConverter<FunctionToolCallItemResourceStatus>))]
public enum FunctionToolCallItemResourceStatus
{
    /// <summary>
    /// The function call is completed.
    /// </summary>
    Completed,

    /// <summary>
    /// The function call is in progress.
    /// </summary>
    InProgress
}

/// <summary>
/// The status of a function tool call output item resource.
/// </summary>
[JsonConverter(typeof(SnakeCaseEnumConverter<FunctionToolCallOutputItemResourceStatus>))]
public enum FunctionToolCallOutputItemResourceStatus
{
    /// <summary>
    /// The function call output is completed.
    /// </summary>
    Completed
}

/// <summary>
/// Base class for item content.
/// </summary>
[JsonPolymorphic(TypeDiscriminatorPropertyName = "type", UnknownDerivedTypeHandling = JsonUnknownDerivedTypeHandling.FailSerialization)]
[JsonDerivedType(typeof(ItemContentInputText), "input_text")]
[JsonDerivedType(typeof(ItemContentInputAudio), "input_audio")]
[JsonDerivedType(typeof(ItemContentInputImage), "input_image")]
[JsonDerivedType(typeof(ItemContentInputFile), "input_file")]
[JsonDerivedType(typeof(ItemContentOutputText), "output_text")]
[JsonDerivedType(typeof(ItemContentOutputAudio), "output_audio")]
[JsonDerivedType(typeof(ItemContentRefusal), "refusal")]
internal abstract record ItemContent
{
    /// <summary>
    /// The type of the content.
    /// </summary>
    [JsonIgnore]
    public abstract string Type { get; }

    /// <summary>
    /// Gets or sets the original representation of the content, if applicable.
    /// This property is not serialized and is used for round-tripping conversions.
    /// </summary>
    [JsonIgnore]
    public object? RawRepresentation { get; set; }
}

/// <summary>
/// Text input content.
/// </summary>
internal sealed record ItemContentInputText : ItemContent
{
    /// <inheritdoc/>
    public override string Type => "input_text";

    /// <summary>
    /// Initializes a new instance of the <see cref="ItemContentInputText"/> class.
    /// </summary>
    /// <param name="text">The text content.</param>
    public ItemContentInputText(string text)
    {
        this.Text = text;
    }

    /// <summary>
    /// The text content.
    /// </summary>
    [JsonPropertyName("text")]
    public string Text { get; init; }
}

/// <summary>
/// Audio input content.
/// </summary>
internal sealed record ItemContentInputAudio : ItemContent
{
    /// <inheritdoc/>
    public override string Type => "input_audio";

    /// <summary>
    /// Initializes a new instance of the <see cref="ItemContentInputAudio"/> class.
    /// </summary>
    /// <param name="data">Base64-encoded audio data.</param>
    /// <param name="format">The format of the audio data (mp3 or wav).</param>
    public ItemContentInputAudio(string data, string format)
    {
        this.Data = data;
        this.Format = format;
    }

    /// <summary>
    /// Base64-encoded audio data.
    /// </summary>
    [JsonPropertyName("data")]
    public string Data { get; init; }

    /// <summary>
    /// The format of the audio data. Currently supported formats are mp3 and wav.
    /// </summary>
    [JsonPropertyName("format")]
    public string Format { get; init; }
}

/// <summary>
/// Image input content.
/// </summary>
internal sealed record ItemContentInputImage : ItemContent
{
    /// <inheritdoc/>
    public override string Type => "input_image";

    /// <summary>
    /// The URL of the image to be sent to the model. A fully qualified URL or base64 encoded image in a data URL.
    /// </summary>
    [JsonPropertyName("image_url")]
    [System.Diagnostics.CodeAnalysis.SuppressMessage("Design", "CA1056:URI-like properties should not be strings", Justification = "OpenAI API uses string for image_url")]
    public string? ImageUrl { get; init; }

    /// <summary>
    /// The ID of the file to be sent to the model.
    /// </summary>
    [JsonPropertyName("file_id")]
    public string? FileId { get; init; }

    /// <summary>
    /// The detail level of the image to be sent to the model. One of 'high', 'low', or 'auto'. Defaults to 'auto'.
    /// </summary>
    [JsonPropertyName("detail")]
    public string? Detail { get; init; }
}

/// <summary>
/// File input content.
/// </summary>
internal sealed record ItemContentInputFile : ItemContent
{
    /// <inheritdoc/>
    public override string Type => "input_file";

    /// <summary>
    /// The ID of the file to be sent to the model.
    /// </summary>
    [JsonPropertyName("file_id")]
    public string? FileId { get; init; }

    /// <summary>
    /// The name of the file to be sent to the model.
    /// </summary>
    [JsonPropertyName("filename")]
    public string? Filename { get; init; }

    /// <summary>
    /// The content of the file to be sent to the model.
    /// </summary>
    [JsonPropertyName("file_data")]
    public string? FileData { get; init; }
}

/// <summary>
/// Text output content.
/// </summary>
internal sealed record ItemContentOutputText : ItemContent
{
    /// <inheritdoc/>
    public override string Type => "output_text";

    /// <summary>
    /// Initializes a new instance of the <see cref="ItemContentOutputText"/> class.
    /// </summary>
    /// <param name="text">The text content.</param>
    /// <param name="annotations">The annotations.</param>
    public ItemContentOutputText(string text, IList<JsonElement> annotations)
    {
        this.Text = text;
        this.Annotations = annotations;
    }

    /// <summary>
    /// The text content.
    /// </summary>
    [JsonPropertyName("text")]
    public string Text { get; init; }

    /// <summary>
    /// The annotations.
    /// </summary>
    [JsonPropertyName("annotations")]
    public IList<JsonElement> Annotations { get; init; }
}

/// <summary>
/// Audio output content.
/// </summary>
internal sealed record ItemContentOutputAudio : ItemContent
{
    /// <inheritdoc/>
    public override string Type => "output_audio";

    /// <summary>
    /// Initializes a new instance of the <see cref="ItemContentOutputAudio"/> class.
    /// </summary>
    /// <param name="data">Base64-encoded audio data from the model.</param>
    /// <param name="transcript">The transcript of the audio data from the model.</param>
    public ItemContentOutputAudio(string data, string transcript)
    {
        this.Data = data;
        this.Transcript = transcript;
    }

    /// <summary>
    /// Base64-encoded audio data from the model.
    /// </summary>
    [JsonPropertyName("data")]
    public string Data { get; init; }

    /// <summary>
    /// The transcript of the audio data from the model.
    /// </summary>
    [JsonPropertyName("transcript")]
    public string Transcript { get; init; }
}

/// <summary>
/// Refusal content.
/// </summary>
internal sealed record ItemContentRefusal : ItemContent
{
    /// <inheritdoc/>
    public override string Type => "refusal";

    /// <summary>
    /// Initializes a new instance of the <see cref="ItemContentRefusal"/> class.
    /// </summary>
    /// <param name="refusal">The refusal explanation from the model.</param>
    public ItemContentRefusal(string refusal)
    {
        this.Refusal = refusal;
    }

    /// <summary>
    /// The refusal explanation from the model.
    /// </summary>
    [JsonPropertyName("refusal")]
    public string Refusal { get; init; }
}
