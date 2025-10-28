// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.Hosting.OpenAI.ChatCompletions.Models;

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

internal sealed record TextContentPart : MessageContentPart
{
    /// <inheritdoc />
    [JsonIgnore]
    public override string Type => "text";

    [JsonPropertyName("text")]
    public required string Text { get; set; }
}

internal sealed record ImageContentPart : MessageContentPart
{
    /// <inheritdoc />
    [JsonIgnore]
    public override string Type => "image_url";

    [JsonPropertyName("image_url")]
    public required ImageUrl ImageUrl { get; set; }

    [JsonIgnore]
    public string UrlOrData => this.ImageUrl.Url;
}

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

internal sealed record AudioContentPart : MessageContentPart
{
    /// <inheritdoc />
    [JsonIgnore]
    public override string Type => "input_audio";

    [JsonPropertyName("input_audio")]
    public required InputAudio InputAudio { get; set; }
}

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

internal sealed record FileContentPart : MessageContentPart
{
    /// <inheritdoc />
    [JsonIgnore]
    public override string Type => "file";

    [JsonPropertyName("file")]
    public required InputFile File { get; set; }
}

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
