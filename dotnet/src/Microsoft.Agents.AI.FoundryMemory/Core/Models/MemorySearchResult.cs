// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.FoundryMemory.Core.Models;

/// <summary>
/// Represents a memory search result.
/// </summary>
internal sealed class MemorySearchResult
{
    /// <summary>
    /// Gets or sets the memory item.
    /// </summary>
    [JsonPropertyName("memory_item")]
    public MemoryItem? MemoryItem { get; set; }

    /// <summary>
    /// Gets or sets the relevance score.
    /// </summary>
    [JsonPropertyName("score")]
    public double Score { get; set; }
}
