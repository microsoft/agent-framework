// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Text.Json;
using System.Text.Json.Serialization;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Declarative.AzureAI;

/// <summary>
/// A class to describe the parameters of an <see cref="AIFunction"/> in a JSON Schema friendly way.
/// </summary>
internal sealed class JsonSchemaFunctionParameters
{
    /// <summary>
    /// The type of schema which is always "object" when describing function parameters.
    /// </summary>
    [JsonPropertyName("type")]
    public string Type => "object";

    /// <summary>
    /// The list of required properties.
    /// </summary>
    [JsonPropertyName("required")]
    public List<string> Required { get; set; } = [];

    /// <summary>
    /// A dictionary of properties, keyed by name => JSON Schema.
    /// </summary>
    [JsonPropertyName("properties")]
    public Dictionary<string, JsonElement> Properties { get; set; } = [];
}
