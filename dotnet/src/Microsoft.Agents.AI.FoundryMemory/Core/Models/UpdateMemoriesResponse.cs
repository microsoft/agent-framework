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
    /// Known values are: "queued", "in_progress", "completed", "failed", "superseded".
    /// </summary>
    [JsonPropertyName("status")]
    public string? Status { get; set; }

    /// <summary>
    /// Gets or sets the update_id that superseded this operation when status is "superseded".
    /// </summary>
    [JsonPropertyName("superseded_by")]
    public string? SupersededBy { get; set; }

    /// <summary>
    /// Gets or sets the error information when status is "failed".
    /// </summary>
    [JsonPropertyName("error")]
    public UpdateMemoriesError? Error { get; set; }
}
