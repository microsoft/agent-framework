// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.Purview.Models.Common;

/// <summary>
/// Represents a plugin used in an AI interaction within the Purview SDK.
/// </summary>
internal sealed class AIInteractionPlugin
{
    /// <summary>
    /// Gets or sets Plugin id.
    /// </summary>
    [JsonPropertyName("identifier")]
    public string? Identifier { get; set; }

    /// <summary>
    /// Gets or sets Plugin Name.
    /// </summary>
    [JsonPropertyName("name")]
    public string? Name { get; set; }

    /// <summary>
    /// Gets or sets Plugin Version.
    /// </summary>
    [JsonPropertyName("version")]
    public string? Version { get; set; }
}
