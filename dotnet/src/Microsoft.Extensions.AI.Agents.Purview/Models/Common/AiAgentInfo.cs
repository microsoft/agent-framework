// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;

namespace Microsoft.Extensions.AI.Agents.Purview.Models.Common;

/// <summary>
/// Info about an AI agent associated with the content.
/// </summary>
internal sealed class AiAgentInfo
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
