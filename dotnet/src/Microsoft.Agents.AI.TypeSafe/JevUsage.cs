// Copyright (c) Microsoft. All rights reserved.

using System.ComponentModel;
using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.TypeSafe;

/// <summary>
/// Represents the token usage of a Jev call. This type mirrors <c>Usage</c> of the official TypeSafe SDK.
/// </summary>
public sealed class JevUsage
{
    /// <summary>
    /// Gets or sets the number of input tokens.
    /// </summary>
    [JsonPropertyName("input_tokens")]
    [Description("The number of input tokens.")]
    public required long InputTokens { get; set; }

    /// <summary>
    /// Gets or sets the number of output tokens.
    /// </summary>
    [JsonPropertyName("output_tokens")]
    [Description("The number of output tokens.")]
    public required long OutputTokens { get; set; }
}
