// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.FoundryMemory.Core.Models;

/// <summary>
/// Response from the search memories API.
/// </summary>
internal sealed class SearchMemoriesResponse
{
    /// <summary>
    /// Gets or sets the unique identifier for the search operation.
    /// </summary>
    [JsonPropertyName("search_id")]
    public string? SearchId { get; set; }

    /// <summary>
    /// Gets or sets the list of retrieved memories.
    /// </summary>
    [JsonPropertyName("memories")]
    public MemorySearchResult[]? Memories { get; set; }
}
