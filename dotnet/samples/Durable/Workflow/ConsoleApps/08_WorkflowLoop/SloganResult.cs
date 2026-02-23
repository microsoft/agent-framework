// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;

namespace WorkflowLoop;

/// <summary>
/// Represents the result produced by the slogan writer executor.
/// </summary>
public sealed class SloganResult
{
    [JsonPropertyName("task")]
    public required string Task { get; set; }

    [JsonPropertyName("slogan")]
    public required string Slogan { get; set; }
}

/// <summary>
/// Represents feedback from the feedback executor, including comments, rating, and improvement actions.
/// </summary>
public sealed class FeedbackResult
{
    [JsonPropertyName("comments")]
    public string Comments { get; set; } = string.Empty;

    [JsonPropertyName("rating")]
    public int Rating { get; set; }

    [JsonPropertyName("actions")]
    public string Actions { get; set; } = string.Empty;
}
