// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Text.Json;
using System.Text.Json.Serialization;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.OpenAI.ChatCompletions.Models;

/// <summary>
/// Represents a tool that the model may call. Can be either a function tool or a custom tool.
/// </summary>
[JsonPolymorphic(TypeDiscriminatorPropertyName = "type")]
[JsonDerivedType(typeof(FunctionTool), "function")]
[JsonDerivedType(typeof(CustomTool), "custom")]
internal abstract record Tool
{
    /// <summary>
    /// The type of the tool.
    /// </summary>
    [JsonIgnore]
    public abstract string Type { get; }
}

/// <summary>
/// A function tool that can be used to generate a response.
/// </summary>
internal sealed record FunctionTool : Tool
{
    /// <summary>
    /// The type of the tool. Always "function".
    /// </summary>
    [JsonIgnore]
    public override string Type => "function";

    /// <summary>
    /// The function definition.
    /// </summary>
    [JsonPropertyName("function")]
    [JsonRequired]
    public required FunctionDefinition Function { get; init; }
}

/// <summary>
/// Definition of a function that can be called by the model.
/// </summary>
internal sealed record FunctionDefinition
{
    /// <summary>
    /// The name of the function to be called.
    /// Must be a-z, A-Z, 0-9, or contain underscores and dashes, with a maximum length of 64.
    /// </summary>
    [JsonPropertyName("name")]
    [JsonRequired]
    public required string Name { get; init; }

    /// <summary>
    /// A description of what the function does, used by the model to choose when and how to call the function.
    /// </summary>
    [JsonPropertyName("description")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? Description { get; init; }

    /// <summary>
    /// The parameters the function accepts, described as a JSON Schema object.
    /// Omitting parameters defines a function with an empty parameter list.
    /// </summary>
    [JsonPropertyName("parameters")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public JsonElement? Parameters { get; init; }

    /// <summary>
    /// Whether to enable strict schema adherence when generating the function call.
    /// If set to true, the model will follow the exact schema defined in the parameters field.
    /// Only a subset of JSON Schema is supported when strict is true.
    /// Defaults to false.
    /// </summary>
    [JsonPropertyName("strict")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public bool? Strict { get; init; }
}

/// <summary>
/// A custom tool that processes input using a specified format.
/// </summary>
internal sealed record CustomTool : Tool
{
    /// <summary>
    /// The type of the tool. Always "custom".
    /// </summary>
    [JsonIgnore]
    public override string Type => "custom";

    /// <summary>
    /// Properties of the custom tool.
    /// </summary>
    [JsonPropertyName("custom")]
    [JsonRequired]
    public required CustomToolProperties Custom { get; init; }
}

/// <summary>
/// A wrapper for MEAI <see cref="AITool"/>
/// </summary>
internal sealed class CustomAITool : AITool
{
    public CustomAITool(string name, string? description, IReadOnlyDictionary<string, object?>? additionalProperties)
        : base()
    {
        this.Name = name;
        this.Description = description ?? string.Empty;
        this.AdditionalProperties = additionalProperties ?? new Dictionary<string, object?>();
    }

    public override string Name { get; }
    public override string Description { get; }
    public override IReadOnlyDictionary<string, object?> AdditionalProperties { get; }
}

/// <summary>
/// Properties of a custom tool.
/// </summary>
internal sealed record CustomToolProperties
{
    /// <summary>
    /// The name of the custom tool, used to identify it in tool calls.
    /// </summary>
    [JsonPropertyName("name")]
    [JsonRequired]
    public required string Name { get; init; }

    /// <summary>
    /// Optional description of the custom tool, used to provide more context.
    /// </summary>
    [JsonPropertyName("description")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? Description { get; init; }

    /// <summary>
    /// The input format for the custom tool. Default is unconstrained text.
    /// </summary>
    [JsonPropertyName("format")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public CustomToolFormat? Format { get; init; }
}

/// <summary>
/// The input format for a custom tool.
/// </summary>
internal sealed record CustomToolFormat
{
    /// <summary>
    /// The type of format. Can be various schema types.
    /// </summary>
    [JsonPropertyName("type")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? Type { get; init; }

    /// <summary>
    /// Additional format properties (schema definition).
    /// </summary>
    [JsonExtensionData]
    public Dictionary<string, object?>? AdditionalProperties { get; set; }
}
