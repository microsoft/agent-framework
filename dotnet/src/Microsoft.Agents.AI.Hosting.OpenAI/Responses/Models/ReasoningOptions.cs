// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Responses.Models;

/// <summary>
/// Configuration options for reasoning models.
/// </summary>
internal sealed class ReasoningOptions
{
    /// <summary>
    /// Constrains effort on reasoning for reasoning models.
    /// Currently supported values are "low", "medium", and "high".
    /// Reducing reasoning effort can result in faster responses and fewer tokens used on reasoning.
    /// </summary>
    [JsonPropertyName("effort")]
    public string? Effort { get; init; }

    /// <summary>
    /// A summary of the reasoning performed by the model.
    /// One of "concise" or "detailed".
    /// </summary>
    [JsonPropertyName("summary")]
    public string? Summary { get; init; }
}
