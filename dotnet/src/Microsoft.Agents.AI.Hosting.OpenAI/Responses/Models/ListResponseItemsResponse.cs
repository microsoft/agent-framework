// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Responses.Models;

/// <summary>
/// Response containing a list of response items.
/// </summary>
internal sealed record ListResponseItemsResponse
{
    /// <summary>
    /// The object type, always "list".
    /// </summary>
    [JsonPropertyName("object")]
    [SuppressMessage("Naming", "CA1720:Identifiers should not match keywords", Justification = "Matches OpenAI API specification")]
    public required string Object { get; init; }

    /// <summary>
    /// The list of items used to generate the response.
    /// </summary>
    [JsonPropertyName("data")]
    public required List<ItemResource> Data { get; init; }

    /// <summary>
    /// The ID of the first item in the list.
    /// </summary>
    [JsonPropertyName("first_id")]
    public string? FirstId { get; init; }

    /// <summary>
    /// The ID of the last item in the list.
    /// </summary>
    [JsonPropertyName("last_id")]
    public string? LastId { get; init; }

    /// <summary>
    /// Whether there are more items available.
    /// </summary>
    [JsonPropertyName("has_more")]
    public required bool HasMore { get; init; }
}
