// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System;
using System.Text.Json.Serialization;

#if ASPNETCORE
namespace Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.Shared;
#else
namespace Microsoft.Agents.AI.AGUI.Shared;
#endif

[JsonConverter(typeof(AGUIMessageContentJsonConverter))]
internal sealed class AGUIMessageContent
{
    public AGUIMessageContent()
    {
        this.Text = string.Empty;
        this.IsText = true;
    }

    public AGUIMessageContent(string text)
    {
        this.Text = text ?? string.Empty;
        this.IsText = true;
    }

    public AGUIMessageContent(IEnumerable<AGUIMessageContentBlock> blocks)
    {
        this.Blocks = [..blocks];
        this.IsText = false;
        this.Text = string.Empty;
    }

    [JsonIgnore]
    public bool IsText { get; }

    [JsonIgnore]
    public string Text { get; }

    [JsonIgnore]
    public AGUIMessageContentBlock[]? Blocks { get; }

    public static AGUIMessageContent FromBlocks(IEnumerable<AGUIMessageContentBlock> blocks) => new AGUIMessageContent(blocks);

    public static implicit operator AGUIMessageContent(string value) => new(value);

    public static implicit operator string(AGUIMessageContent content) => content.ToString();

    public override string ToString() => this.IsText
        ? this.Text
        : this.Blocks is null
            ? string.Empty
            : string.Concat(this.Blocks.Where(block => string.Equals(block.Type, "text", StringComparison.OrdinalIgnoreCase)).Select(block => block.Text ?? string.Empty));
}

internal sealed class AGUIMessageContentBlock
{
    [JsonPropertyName("type")]
    public string Type { get; set; } = string.Empty;

    [JsonPropertyName("text")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingDefault)]
    public string? Text { get; set; }

    [JsonPropertyName("id")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingDefault)]
    public string? Id { get; set; }

    [JsonPropertyName("url")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingDefault)]
    public string? Url { get; set; }

    [JsonPropertyName("data")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingDefault)]
    public string? Data { get; set; }

    [JsonPropertyName("filename")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingDefault)]
    public string? Filename { get; set; }

    [JsonPropertyName("mimeType")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingDefault)]
    public string? MimeType { get; set; }

    [JsonPropertyName("source")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingDefault)]
    public AGUIMessageContentSource? Source { get; set; }
}

internal sealed class AGUIMessageContentSource
{
    [JsonPropertyName("type")]
    public string Type { get; set; } = string.Empty;

    [JsonPropertyName("value")]
    public string Value { get; set; } = string.Empty;

    [JsonPropertyName("mimeType")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingDefault)]
    public string? MimeType { get; set; }
}
