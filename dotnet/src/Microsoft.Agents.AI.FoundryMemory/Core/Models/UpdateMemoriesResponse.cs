// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.FoundryMemory.Core.Models;

/// <summary>
/// Response from the update memories API.
/// </summary>
internal sealed class UpdateMemoriesResponse
{
    /// <summary>
    /// Gets or sets the unique identifier of the update operation.
    /// </summary>
    [JsonPropertyName("update_id")]
    public string? UpdateId { get; set; }

    /// <summary>
    /// Gets or sets the status of the update operation.
    /// </summary>
    [JsonPropertyName("status")]
    public string? Status { get; set; }
}
