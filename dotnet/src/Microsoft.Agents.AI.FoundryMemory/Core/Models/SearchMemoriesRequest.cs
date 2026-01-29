// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.FoundryMemory.Core.Models;

/// <summary>
/// Request body for the search memories API.
/// </summary>
internal sealed class SearchMemoriesRequest
{
    /// <summary>
    /// Gets or sets the namespace that logically groups and isolates memories, such as a user ID.
    /// </summary>
    [JsonPropertyName("scope")]
    public string Scope { get; set; } = string.Empty;

    /// <summary>
    /// Gets or sets the conversation messages to use for the search query.
    /// </summary>
    [JsonPropertyName("items")]
    public MemoryInputMessage[] Items { get; set; } = [];

    /// <summary>
    /// Gets or sets the search options.
    /// </summary>
    [JsonPropertyName("options")]
    public SearchMemoriesOptions? Options { get; set; }
}
