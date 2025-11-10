// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Responses.Models;

/// <summary>
/// Reference to a prompt template and its variables.
/// </summary>
internal sealed class PromptReference
{
    /// <summary>
    /// The ID of the prompt template to use.
    /// </summary>
    [JsonPropertyName("id")]
    public required string Id { get; init; }

    /// <summary>
    /// Variables to substitute in the prompt template.
    /// </summary>
    [JsonPropertyName("variables")]
    public Dictionary<string, string>? Variables { get; init; }
}
