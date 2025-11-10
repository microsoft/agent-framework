// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Responses.Models;

/// <summary>
/// Configuration options for a text response from the model.
/// </summary>
internal sealed class TextConfiguration
{
    /// <summary>
    /// The format configuration for the text response.
    /// Can specify plain text, JSON object, or JSON schema for structured outputs.
    /// </summary>
    [JsonPropertyName("format")]
    public ResponseTextFormatConfiguration? Format { get; init; }

    /// <summary>
    /// Constrains the verbosity of the model's response.
    /// Lower values will result in more concise responses, while higher values will result in more verbose responses.
    /// Supported values are "low", "medium", and "high". Defaults to "medium".
    /// </summary>
    [JsonPropertyName("verbosity")]
    public string? Verbosity { get; init; }
}

/// <summary>
/// Base class for response text format configurations.
/// This is a discriminated union based on the "type" property.
/// </summary>
[JsonPolymorphic(TypeDiscriminatorPropertyName = "type", UnknownDerivedTypeHandling = JsonUnknownDerivedTypeHandling.FailSerialization)]
[JsonDerivedType(typeof(ResponseTextFormatConfigurationText), "text")]
[JsonDerivedType(typeof(ResponseTextFormatConfigurationJsonObject), "json_object")]
[JsonDerivedType(typeof(ResponseTextFormatConfigurationJsonSchema), "json_schema")]
internal abstract class ResponseTextFormatConfiguration
{
    /// <summary>
    /// The type of response format.
    /// </summary>
    [JsonIgnore]
    public abstract string Type { get; }
}

/// <summary>
/// Plain text response format configuration.
/// </summary>
internal sealed class ResponseTextFormatConfigurationText : ResponseTextFormatConfiguration
{
    /// <summary>
    /// Gets the type of response format. Always "text".
    /// </summary>
    [JsonIgnore]
    public override string Type => "text";
}

/// <summary>
/// JSON object response format configuration.
/// Ensures the message the model generates is valid JSON.
/// </summary>
internal sealed class ResponseTextFormatConfigurationJsonObject : ResponseTextFormatConfiguration
{
    /// <summary>
    /// Gets the type of response format. Always "json_object".
    /// </summary>
    [JsonIgnore]
    public override string Type => "json_object";
}

/// <summary>
/// JSON schema response format configuration with structured output schema.
/// </summary>
internal sealed class ResponseTextFormatConfigurationJsonSchema : ResponseTextFormatConfiguration
{
    /// <summary>
    /// Gets the type of response format. Always "json_schema".
    /// </summary>
    [JsonIgnore]
    public override string Type => "json_schema";

    /// <summary>
    /// The name of the response format. Must be a-z, A-Z, 0-9, or contain
    /// underscores and dashes, with a maximum length of 64.
    /// </summary>
    [JsonPropertyName("name")]
    public required string Name { get; init; }

    /// <summary>
    /// A description of what the response format is for, used by the model to
    /// determine how to respond in the format.
    /// </summary>
    [JsonPropertyName("description")]
    public string? Description { get; init; }

    /// <summary>
    /// The JSON schema for structured outputs.
    /// </summary>
    [JsonPropertyName("schema")]
    public required JsonElement Schema { get; init; }

    /// <summary>
    /// Whether to enable strict schema adherence when generating the output.
    /// If set to true, the model will always follow the exact schema defined in the schema field.
    /// </summary>
    [JsonPropertyName("strict")]
    public bool? Strict { get; init; }
}
