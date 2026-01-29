// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.FoundryMemory.Core.Models;

/// <summary>
/// Options for searching memories.
/// </summary>
internal sealed class SearchMemoriesOptions
{
    /// <summary>
    /// Gets or sets the maximum number of memories to return.
    /// </summary>
    [JsonPropertyName("max_memories")]
    public int MaxMemories { get; set; } = 5;
}
