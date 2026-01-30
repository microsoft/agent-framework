// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.FoundryMemory.Core.Models;

/// <summary>
/// Response from creating or getting a memory store.
/// </summary>
internal sealed class MemoryStoreResponse
{
    /// <summary>
    /// Gets or sets the unique identifier of the memory store.
    /// </summary>
    [JsonPropertyName("id")]
    public string? Id { get; set; }

    /// <summary>
    /// Gets or sets the name of the memory store.
    /// </summary>
    [JsonPropertyName("name")]
    public string? Name { get; set; }

    /// <summary>
    /// Gets or sets the description of the memory store.
    /// </summary>
    [JsonPropertyName("description")]
    public string? Description { get; set; }
}
