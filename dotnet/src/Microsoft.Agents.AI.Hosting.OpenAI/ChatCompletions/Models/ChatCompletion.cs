// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.Hosting.OpenAI.ChatCompletions.Models;

/// <summary>
/// Represents a chat completion response returned by the model, based on the provided input.
/// </summary>
internal sealed record ChatCompletion
{
    /// <summary>
    /// A unique identifier for the chat completion.
    /// </summary>
    [JsonPropertyName("id")]
    [JsonRequired]
    public required string Id { get; init; }

    /// <summary>
    /// The object type, which is always "chat.completion".
    /// </summary>
    [JsonPropertyName("object")]
    public string Object { get; init; } = "chat.completion";

    /// <summary>
    /// The Unix timestamp (in seconds) of when the chat completion was created.
    /// </summary>
    [JsonPropertyName("created")]
    [JsonRequired]
    public required long Created { get; init; }

    /// <summary>
    /// The model used for the chat completion.
    /// </summary>
    [JsonPropertyName("model")]
    [JsonRequired]
    public required string Model { get; init; }

    /// <summary>
    /// A list of chat completion choices. Can be more than one if n is greater than 1.
    /// </summary>
    [JsonPropertyName("choices")]
    [JsonRequired]
    public required IList<ChatCompletionChoice> Choices { get; init; }

    /// <summary>
    /// Usage statistics for the completion request.
    /// </summary>
    [JsonPropertyName("usage")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public CompletionUsage? Usage { get; init; }

    /// <summary>
    /// The service tier used for processing the request. This field is only included if the service_tier parameter is specified in the request.
    /// </summary>
    [JsonPropertyName("service_tier")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? ServiceTier { get; init; }

    /// <summary>
    /// This fingerprint represents the backend configuration that the model runs with.
    /// Can be used in conjunction with the seed request parameter to understand when backend changes have been made that might impact determinism.
    /// </summary>
    [JsonPropertyName("system_fingerprint")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? SystemFingerprint { get; init; }
}
