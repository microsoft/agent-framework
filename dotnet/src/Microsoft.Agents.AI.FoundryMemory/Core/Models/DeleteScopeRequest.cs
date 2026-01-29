// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.FoundryMemory.Core.Models;

/// <summary>
/// Request body for the delete scope API.
/// </summary>
internal sealed class DeleteScopeRequest
{
    /// <summary>
    /// Gets or sets the scope to delete.
    /// </summary>
    [JsonPropertyName("scope")]
    public string Scope { get; set; } = string.Empty;
}
