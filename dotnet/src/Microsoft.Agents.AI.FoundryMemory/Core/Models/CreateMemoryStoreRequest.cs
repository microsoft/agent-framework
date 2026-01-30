// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.FoundryMemory.Core.Models;

/// <summary>
/// Request body for creating a memory store.
/// </summary>
internal sealed class CreateMemoryStoreRequest
{
    /// <summary>
    /// Gets or sets the name of the memory store.
    /// </summary>
    [JsonPropertyName("name")]
    public string? Name { get; set; }

    /// <summary>
    /// Gets or sets an optional description for the memory store.
    /// </summary>
    [JsonPropertyName("description")]
    public string? Description { get; set; }

    /// <summary>
    /// Gets or sets the definition for the memory store.
    /// </summary>
    [JsonPropertyName("definition")]
    public MemoryStoreDefinitionRequest? Definition { get; set; }
}
