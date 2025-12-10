// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.Hosting.OpenAI.ChatCompletions.Models;

/// <summary>
/// Represents a part of message content in a chat completion request.
/// Message content can be text, images, audio, or files.
/// </summary>
[JsonPolymorphic(TypeDiscriminatorPropertyName = "type", UnknownDerivedTypeHandling = JsonUnknownDerivedTypeHandling.FailSerialization)]
[JsonDerivedType(typeof(TextContentPart), "text")]
[JsonDerivedType(typeof(ImageContentPart), "image_url")]
[JsonDerivedType(typeof(AudioContentPart), "input_audio")]
[JsonDerivedType(typeof(FileContentPart), "file")]
internal abstract record MessageContentPart
{
    /// <summary>
    /// The type of the content.
    /// </summary>
    [JsonIgnore]
    public abstract string Type { get; }
}

/// <summary>
/// A text content part in a message.
/// </summary>
internal sealed record TextContentPart : MessageContentPart
{
    /// <inheritdoc />
    [JsonIgnore]
    public override string Type => "text";

    /// <summary>
    /// The text content.
    /// </summary>
    [JsonPropertyName("text")]
    public required string Text { get; set; }
}

/// <summary>
/// An image content part in a message.
/// </summary>
internal sealed record ImageContentPart : MessageContentPart
{
    /// <inheritdoc />
    [JsonIgnore]
    public override string Type => "image_url";

    /// <summary>
    /// Details about the image URL or base64-encoded image data.
    /// </summary>
    [JsonPropertyName("image_url")]
    public required ImageUrl ImageUrl { get; set; }

    /// <summary>
    /// Gets the URL or base64-encoded data of the image.
    /// </summary>
    [JsonIgnore]
    public string UrlOrData => this.ImageUrl.Url;

    /// <summary>
    /// Gets the URL of the image.
    /// </summary>
    [JsonIgnore]
    public Uri Url => new(this.ImageUrl.Url);
}

/// <summary>
/// Details about an image for vision-enabled models.
/// </summary>
internal sealed record ImageUrl
{
    /// <summary>
    /// Either a URL of the image or the base64 encoded image data
    /// </summary>
    [JsonPropertyName("url")]
    public required string Url { get; set; }

    /// <summary>
    /// Specifies the detail level of the image
    /// </summary>
    [JsonPropertyName("detail")]
    public string? Detail { get; set; }
}

/// <summary>
/// An audio content part in a message.
/// </summary>
internal sealed record AudioContentPart : MessageContentPart
{
    /// <inheritdoc />
    [JsonIgnore]
    public override string Type => "input_audio";

    /// <summary>
    /// The input audio data.
    /// </summary>
    [JsonPropertyName("input_audio")]
    public required InputAudio InputAudio { get; set; }
}

/// <summary>
/// Input audio data for audio-enabled models.
/// </summary>
internal sealed record InputAudio
{
    /// <summary>
    /// Base64 encoded audio data.
    /// </summary>
    [JsonPropertyName("data")]
    public required string Data { get; set; }

    /// <summary>
    /// The format of the encoded audio data. Currently supports "wav" and "mp3".
    /// </summary>
    [JsonPropertyName("format")]
    public required string Format { get; set; }
}

/// <summary>
/// A file content part in a message.
/// </summary>
internal sealed record FileContentPart : MessageContentPart
{
    /// <inheritdoc />
    [JsonIgnore]
    public override string Type => "file";

    /// <summary>
    /// The input file data.
    /// </summary>
    [JsonPropertyName("file")]
    public required InputFile File { get; set; }
}

/// <summary>
/// Input file data for file-enabled models.
/// </summary>
internal sealed record InputFile
{
    /// <summary>
    /// The base64 encoded file data, used when passing the file to the model as a string.
    /// </summary>
    [JsonPropertyName("file_data")]
    public string? FileData { get; set; }

    /// <summary>
    /// The ID of an uploaded file to use as input.
    /// </summary>
    [JsonPropertyName("file_id")]
    public string? FileId { get; set; }

    /// <summary>
    /// The name of the file, used when passing the file to the model as a string.
    /// </summary>
    [JsonPropertyName("filename")]
    public string? Filename { get; set; }
}
