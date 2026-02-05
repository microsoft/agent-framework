// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.FoundryMemory.Core.Models;

/// <summary>
/// Request body for the update memories API.
/// </summary>
internal sealed class UpdateMemoriesRequest
{
    /// <summary>
    /// Gets or sets the namespace that logically groups and isolates memories, such as a user ID.
    /// </summary>
    [JsonPropertyName("scope")]
    public string Scope { get; set; } = string.Empty;

    /// <summary>
    /// Gets or sets the conversation messages to extract memories from.
    /// </summary>
    [JsonPropertyName("items")]
    public MemoryInputMessage[] Items { get; set; } = [];

    /// <summary>
    /// Gets or sets the delay in seconds before processing the update.
    /// </summary>
    [JsonPropertyName("update_delay")]
    public int UpdateDelay { get; set; }

    /// <summary>
    /// Gets or sets the ID of a previous update operation to chain with.
    /// </summary>
    [JsonPropertyName("previous_update_id")]
    public string? PreviousUpdateId { get; set; }
}
