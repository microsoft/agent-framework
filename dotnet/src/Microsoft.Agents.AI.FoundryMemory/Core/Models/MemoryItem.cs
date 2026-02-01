// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.FoundryMemory.Core.Models;

/// <summary>
/// Represents a memory item.
/// </summary>
internal sealed class MemoryItem
{
    /// <summary>
    /// Gets or sets the unique identifier of the memory.
    /// </summary>
    [JsonPropertyName("memory_id")]
    public string? MemoryId { get; set; }

    /// <summary>
    /// Gets or sets the content of the memory.
    /// </summary>
    [JsonPropertyName("content")]
    public string? Content { get; set; }

    /// <summary>
    /// Gets or sets the type of the memory.
    /// </summary>
    [JsonPropertyName("memory_type")]
    public string? MemoryType { get; set; }
}
