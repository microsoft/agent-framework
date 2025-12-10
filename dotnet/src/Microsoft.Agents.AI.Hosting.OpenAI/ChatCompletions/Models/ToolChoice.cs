// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.Hosting.OpenAI.ChatCompletions.Models;

/// <summary>
/// Controls which (if any) tool is called by the model.
/// </summary>
[JsonConverter(typeof(ToolChoiceConverter))]
internal sealed record ToolChoice : IEquatable<ToolChoice>
{
    private ToolChoice(string mode)
    {
        this.Mode = mode ?? throw new ArgumentNullException(nameof(mode));
        this.AllowedTools = null;
        this.FunctionTool = null;
        this.CustomTool = null;
    }

    private ToolChoice(AllowedToolsChoice allowedTools)
    {
        this.AllowedTools = allowedTools ?? throw new ArgumentNullException(nameof(allowedTools));
        this.Mode = null;
        this.FunctionTool = null;
        this.CustomTool = null;
    }

    private ToolChoice(FunctionToolChoice functionTool)
    {
        this.FunctionTool = functionTool ?? throw new ArgumentNullException(nameof(functionTool));
        this.Mode = null;
        this.AllowedTools = null;
        this.CustomTool = null;
    }

    private ToolChoice(CustomToolChoice customTool)
    {
        this.CustomTool = customTool ?? throw new ArgumentNullException(nameof(customTool));
        this.Mode = null;
        this.AllowedTools = null;
        this.FunctionTool = null;
    }

    /// <summary>
    /// Creates a ToolChoice from a mode string ("none", "auto", or "required").
    /// </summary>
    public static ToolChoice FromMode(string mode) => new(mode);

    /// <summary>
    /// Creates a ToolChoice that constrains tools to a pre-defined set.
    /// </summary>
    public static ToolChoice FromAllowedTools(AllowedToolsChoice allowedTools) => new(allowedTools);

    /// <summary>
    /// Creates a ToolChoice that forces the model to call a specific function.
    /// </summary>
    public static ToolChoice FromFunction(FunctionToolChoice functionTool) => new(functionTool);

    /// <summary>
    /// Creates a ToolChoice that forces the model to call a specific custom tool.
    /// </summary>
    public static ToolChoice FromCustom(CustomToolChoice customTool) => new(customTool);

    /// <summary>
    /// Implicit conversion from string to ToolChoice.
    /// </summary>
    public static implicit operator ToolChoice(string mode) => FromMode(mode);

    /// <summary>
    /// Gets whether this is a mode string.
    /// </summary>
    [MemberNotNullWhen(true, nameof(Mode))]
    public bool IsMode => this.Mode is not null;

    /// <summary>
    /// Gets whether this is an allowed tools configuration.
    /// </summary>
    [MemberNotNullWhen(true, nameof(AllowedTools))]
    public bool IsAllowedTools => this.AllowedTools is not null;

    /// <summary>
    /// Gets whether this is a function tool choice.
    /// </summary>
    [MemberNotNullWhen(true, nameof(FunctionTool))]
    public bool IsFunctionTool => this.FunctionTool is not null;

    /// <summary>
    /// Gets whether this is a custom tool choice.
    /// </summary>
    [MemberNotNullWhen(true, nameof(CustomTool))]
    public bool IsCustomTool => this.CustomTool is not null;

    /// <summary>
    /// Gets the mode string, or null if this is not a mode.
    /// </summary>
    public string? Mode { get; }

    /// <summary>
    /// Gets the allowed tools configuration, or null if this is not an allowed tools choice.
    /// </summary>
    public AllowedToolsChoice? AllowedTools { get; }

    /// <summary>
    /// Gets the function tool choice, or null if this is not a function tool choice.
    /// </summary>
    public FunctionToolChoice? FunctionTool { get; }

    /// <summary>
    /// Gets the custom tool choice, or null if this is not a custom tool choice.
    /// </summary>
    public CustomToolChoice? CustomTool { get; }

    /// <inheritdoc/>
    public bool Equals(ToolChoice? other)
    {
        if (other is null)
        {
            return false;
        }

        if (ReferenceEquals(this, other))
        {
            return true;
        }

        if (this.Mode is not null && other.Mode is not null)
        {
            return this.Mode == other.Mode;
        }

        if (this.AllowedTools is not null && other.AllowedTools is not null)
        {
            return this.AllowedTools.Equals(other.AllowedTools);
        }

        if (this.FunctionTool is not null && other.FunctionTool is not null)
        {
            return this.FunctionTool.Equals(other.FunctionTool);
        }

        if (this.CustomTool is not null && other.CustomTool is not null)
        {
            return this.CustomTool.Equals(other.CustomTool);
        }

        return false;
    }

    /// <inheritdoc/>
    public override int GetHashCode()
    {
        if (this.Mode is not null)
        {
            return this.Mode.GetHashCode();
        }

        if (this.AllowedTools is not null)
        {
            return this.AllowedTools.GetHashCode();
        }

        if (this.FunctionTool is not null)
        {
            return this.FunctionTool.GetHashCode();
        }

        if (this.CustomTool is not null)
        {
            return this.CustomTool.GetHashCode();
        }

        return 0;
    }
}

/// <summary>
/// Constrains the tools available to the model to a pre-defined set.
/// </summary>
internal sealed record AllowedToolsChoice
{
    /// <summary>
    /// The type of tool choice. Always "allowed_tools".
    /// </summary>
    [JsonPropertyName("type")]
    public string Type => "allowed_tools";

    /// <summary>
    /// Constrains the tools available to the model to a pre-defined set.
    /// </summary>
    [JsonPropertyName("allowed_tools")]
    [JsonRequired]
    public required AllowedToolsConfiguration AllowedTools { get; init; }
}

/// <summary>
/// Configuration for allowed tools.
/// </summary>
internal sealed record AllowedToolsConfiguration
{
    /// <summary>
    /// Constrains the tools available to the model to a pre-defined set.
    /// auto allows the model to pick from among the allowed tools and generate a message.
    /// required requires the model to call one or more of the allowed tools.
    /// </summary>
    [JsonPropertyName("mode")]
    [JsonRequired]
    public required string Mode { get; init; }

    /// <summary>
    /// A list of tool definitions that the model should be allowed to call.
    /// </summary>
    [JsonPropertyName("tools")]
    [JsonRequired]
    public required IList<ToolDefinition> Tools { get; init; }
}

/// <summary>
/// A tool definition in the allowed tools list.
/// </summary>
internal sealed record ToolDefinition
{
    /// <summary>
    /// The type of tool (e.g., "function" or "custom").
    /// </summary>
    [JsonPropertyName("type")]
    [JsonRequired]
    public required string Type { get; init; }

    /// <summary>
    /// The function details if type is "function".
    /// </summary>
    [JsonPropertyName("function")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public FunctionReference? Function { get; init; }
}

/// <summary>
/// A reference to a function by name.
/// </summary>
internal sealed record FunctionReference
{
    /// <summary>
    /// The name of the function.
    /// </summary>
    [JsonPropertyName("name")]
    [JsonRequired]
    public required string Name { get; init; }
}

/// <summary>
/// Specifies a function tool the model should use.
/// </summary>
internal sealed record FunctionToolChoice
{
    /// <summary>
    /// The type of tool. Always "function".
    /// </summary>
    [JsonPropertyName("type")]
    public string Type => "function";

    /// <summary>
    /// The function to call.
    /// </summary>
    [JsonPropertyName("function")]
    [JsonRequired]
    public required FunctionReference Function { get; init; }
}

/// <summary>
/// Specifies a custom tool the model should use.
/// </summary>
internal sealed record CustomToolChoice
{
    /// <summary>
    /// The type of tool. Always "custom".
    /// </summary>
    [JsonPropertyName("type")]
    public string Type => "custom";

    /// <summary>
    /// The custom tool configuration.
    /// </summary>
    [JsonPropertyName("custom")]
    [JsonRequired]
    public required CustomToolObject Custom { get; init; }
}

/// <summary>
/// A reference to a custom tool object.
/// </summary>
internal sealed record CustomToolObject
{
    /// <summary>
    /// The name of the function.
    /// </summary>
    [JsonPropertyName("name")]
    [JsonRequired]
    public required string Name { get; init; }
}

/// <summary>
/// JSON converter for <see cref="ToolChoice"/> that handles string and object representations.
/// </summary>
internal sealed class ToolChoiceConverter : JsonConverter<ToolChoice>
{
    /// <inheritdoc/>
    public override ToolChoice? Read(ref Utf8JsonReader reader, Type typeToConvert, JsonSerializerOptions options)
    {
        if (reader.TokenType == JsonTokenType.Null)
        {
            return null;
        }

        if (reader.TokenType == JsonTokenType.String)
        {
            string? mode = reader.GetString();
            return mode is not null ? ToolChoice.FromMode(mode) : null;
        }

        if (reader.TokenType == JsonTokenType.StartObject)
        {
            using var doc = JsonDocument.ParseValue(ref reader);
            var root = doc.RootElement;

            if (root.TryGetProperty("type", out var typeProperty))
            {
                var type = typeProperty.GetString();
                return type switch
                {
                    "allowed_tools" => ToolChoice.FromAllowedTools(
                        JsonSerializer.Deserialize(root.GetRawText(), ChatCompletionsJsonContext.Default.AllowedToolsChoice)!),

                    "function" => ToolChoice.FromFunction(
                        JsonSerializer.Deserialize(root.GetRawText(), ChatCompletionsJsonContext.Default.FunctionToolChoice)!),

                    "custom" => ToolChoice.FromCustom(
                        JsonSerializer.Deserialize(root.GetRawText(), ChatCompletionsJsonContext.Default.CustomToolChoice)!),

                    _ => throw new JsonException($"Unknown tool choice type: {type}")
                };
            }

            throw new JsonException("Tool choice object must have a 'type' property.");
        }

        throw new JsonException($"Unexpected token type '{reader.TokenType}' when deserializing ToolChoice.");
    }

    /// <inheritdoc/>
    public override void Write(Utf8JsonWriter writer, ToolChoice? value, JsonSerializerOptions options)
    {
        if (value is null)
        {
            writer.WriteNullValue();
            return;
        }

        if (value.IsMode)
        {
            writer.WriteStringValue(value.Mode);
        }
        else if (value.IsAllowedTools)
        {
            JsonSerializer.Serialize(writer, value.AllowedTools, ChatCompletionsJsonContext.Default.AllowedToolsChoice);
        }
        else if (value.IsFunctionTool)
        {
            JsonSerializer.Serialize(writer, value.FunctionTool, ChatCompletionsJsonContext.Default.FunctionToolChoice);
        }
        else if (value.IsCustomTool)
        {
            JsonSerializer.Serialize(writer, value.CustomTool, ChatCompletionsJsonContext.Default.CustomToolChoice);
        }
        else
        {
            writer.WriteNullValue();
        }
    }
}
