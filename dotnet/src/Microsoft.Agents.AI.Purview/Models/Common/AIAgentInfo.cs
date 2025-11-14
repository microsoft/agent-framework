// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.Purview.Models.Common;

/// <summary>
/// Info about an AI agent associated with the content.
/// </summary>
internal sealed class AIAgentInfo
{
    /// <summary>
    /// Gets or sets agent id.
    /// </summary>
    [JsonPropertyName("identifier")]
    public string? Identifier { get; set; }

    /// <summary>
    /// Gets or sets agent name.
    /// </summary>
    [JsonPropertyName("name")]
    public string? Name { get; set; }

    /// <summary>
    /// Gets or sets agent version.
    /// </summary>
    [JsonPropertyName("version")]
    public string? Version { get; set; }
}
