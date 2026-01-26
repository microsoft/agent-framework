// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;

namespace SingleAgent;

public sealed class SloganResult
{
    [JsonPropertyName("task")]
    public required string Task { get; set; }

    [JsonPropertyName("slogan")]
    public required string Slogan { get; set; }
}

public sealed class FeedbackResult
{
    [JsonPropertyName("comments")]
    public string Comments { get; set; } = string.Empty;

    [JsonPropertyName("rating")]
    public int Rating { get; set; }

    [JsonPropertyName("actions")]
    public string Actions { get; set; } = string.Empty;
}
