// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics.CodeAnalysis;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.Hosting.OpenAI.ChatCompletions.Models;

/// <summary>
/// Specifies the format that the model must output.
/// </summary>
[JsonConverter(typeof(ResponseFormatConverter))]
internal sealed record ResponseFormat : IEquatable<ResponseFormat>
{
    private ResponseFormat(TextResponseFormat text)
    {
        this.Text = text ?? throw new ArgumentNullException(nameof(text));
        this.JsonSchema = null;
        this.JsonObject = null;
    }

    private ResponseFormat(JsonSchemaResponseFormat jsonSchema)
    {
        this.JsonSchema = jsonSchema ?? throw new ArgumentNullException(nameof(jsonSchema));
        this.Text = null;
        this.JsonObject = null;
    }

    private ResponseFormat(JsonObjectResponseFormat jsonObject)
    {
        this.JsonObject = jsonObject ?? throw new ArgumentNullException(nameof(jsonObject));
        this.Text = null;
        this.JsonSchema = null;
    }

    /// <summary>
    /// Creates a ResponseFormat for text output (default).
    /// </summary>
    public static ResponseFormat FromText() => new(new TextResponseFormat());

    /// <summary>
    /// Creates a ResponseFormat for JSON Schema output with Structured Outputs.
    /// </summary>
    public static ResponseFormat FromJsonSchema(JsonSchemaResponseFormat jsonSchema) => new(jsonSchema);

    /// <summary>
    /// Creates a ResponseFormat for JSON object output (older JSON mode).
    /// </summary>
    public static ResponseFormat FromJsonObject() => new(new JsonObjectResponseFormat());

    /// <summary>
    /// Gets whether this is a text response format.
    /// </summary>
    [MemberNotNullWhen(true, nameof(Text))]
    public bool IsText => this.Text is not null;

    /// <summary>
    /// Gets whether this is a JSON schema response format.
    /// </summary>
    [MemberNotNullWhen(true, nameof(JsonSchema))]
    public bool IsJsonSchema => this.JsonSchema is not null;

    /// <summary>
    /// Gets whether this is a JSON object response format.
    /// </summary>
    [MemberNotNullWhen(true, nameof(JsonObject))]
    public bool IsJsonObject => this.JsonObject is not null;

    /// <summary>
    /// Gets the text response format, or null if this is not a text format.
    /// </summary>
    public TextResponseFormat? Text { get; }

    /// <summary>
    /// Gets the JSON schema response format, or null if this is not a JSON schema format.
    /// </summary>
    public JsonSchemaResponseFormat? JsonSchema { get; }

    /// <summary>
    /// Gets the JSON object response format, or null if this is not a JSON object format.
    /// </summary>
    public JsonObjectResponseFormat? JsonObject { get; }

    /// <inheritdoc/>
    public bool Equals(ResponseFormat? other)
    {
        if (other is null)
        {
            return false;
        }

        if (ReferenceEquals(this, other))
        {
            return true;
        }

        if (this.Text is not null && other.Text is not null)
        {
            return this.Text.Equals(other.Text);
        }

        if (this.JsonSchema is not null && other.JsonSchema is not null)
        {
            return this.JsonSchema.Equals(other.JsonSchema);
        }

        if (this.JsonObject is not null && other.JsonObject is not null)
        {
            return this.JsonObject.Equals(other.JsonObject);
        }

        return false;
    }

    /// <inheritdoc/>
    public override int GetHashCode()
    {
        if (this.Text is not null)
        {
            return this.Text.GetHashCode();
        }

        if (this.JsonSchema is not null)
        {
            return this.JsonSchema.GetHashCode();
        }

        if (this.JsonObject is not null)
        {
            return this.JsonObject.GetHashCode();
        }

        return 0;
    }
}

/// <summary>
/// Text response format. Default response format used to generate text responses.
/// </summary>
internal sealed record TextResponseFormat
{
    /// <summary>
    /// The type of response format. Always "text".
    /// </summary>
    [JsonPropertyName("type")]
    public string Type => "text";
}

/// <summary>
/// JSON Schema response format. Used to generate structured JSON responses with Structured Outputs.
/// </summary>
internal sealed record JsonSchemaResponseFormat
{
    /// <summary>
    /// The type of response format. Always "json_schema".
    /// </summary>
    [JsonPropertyName("type")]
    public string Type => "json_schema";

    /// <summary>
    /// Structured Outputs configuration options, including a JSON Schema.
    /// </summary>
    [JsonPropertyName("json_schema")]
    [JsonRequired]
    public required JsonSchemaConfiguration JsonSchema { get; init; }
}

/// <summary>
/// Configuration for JSON Schema Structured Outputs.
/// </summary>
internal sealed record JsonSchemaConfiguration
{
    /// <summary>
    /// The name of the schema.
    /// </summary>
    [JsonPropertyName("name")]
    [JsonRequired]
    public required string Name { get; init; }

    /// <summary>
    /// A description of the schema.
    /// </summary>
    [JsonPropertyName("description")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? Description { get; init; }

    /// <summary>
    /// The JSON Schema definition.
    /// </summary>
    [JsonPropertyName("schema")]
    [JsonRequired]
    public required JsonElement Schema { get; init; }

    /// <summary>
    /// Whether to enable strict schema adherence.
    /// </summary>
    [JsonPropertyName("strict")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public bool? Strict { get; init; }
}

/// <summary>
/// JSON object response format. An older method of generating JSON responses.
/// Using json_schema is recommended for models that support it.
/// </summary>
internal sealed record JsonObjectResponseFormat
{
    /// <summary>
    /// The type of response format. Always "json_object".
    /// </summary>
    [JsonPropertyName("type")]
    public string Type => "json_object";
}

/// <summary>
/// JSON converter for <see cref="ResponseFormat"/> that handles different response format types.
/// </summary>
internal sealed class ResponseFormatConverter : JsonConverter<ResponseFormat>
{
    /// <inheritdoc/>
    public override ResponseFormat? Read(ref Utf8JsonReader reader, Type typeToConvert, JsonSerializerOptions options)
    {
        if (reader.TokenType == JsonTokenType.Null)
        {
            return null;
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
                    "text" => ResponseFormat.FromText(),

                    "json_schema" => ResponseFormat.FromJsonSchema(
                        JsonSerializer.Deserialize(root.GetRawText(), ChatCompletionsJsonContext.Default.JsonSchemaResponseFormat)!),

                    "json_object" => ResponseFormat.FromJsonObject(),

                    _ => throw new JsonException($"Unknown response format type: {type}")
                };
            }

            throw new JsonException("Response format object must have a 'type' property.");
        }

        throw new JsonException($"Unexpected token type '{reader.TokenType}' when deserializing ResponseFormat.");
    }

    /// <inheritdoc/>
    public override void Write(Utf8JsonWriter writer, ResponseFormat? value, JsonSerializerOptions options)
    {
        if (value is null)
        {
            writer.WriteNullValue();
            return;
        }

        if (value.IsText)
        {
            JsonSerializer.Serialize(writer, value.Text, ChatCompletionsJsonContext.Default.TextResponseFormat);
        }
        else if (value.IsJsonSchema)
        {
            JsonSerializer.Serialize(writer, value.JsonSchema, ChatCompletionsJsonContext.Default.JsonSchemaResponseFormat);
        }
        else if (value.IsJsonObject)
        {
            JsonSerializer.Serialize(writer, value.JsonObject, ChatCompletionsJsonContext.Default.JsonObjectResponseFormat);
        }
        else
        {
            writer.WriteNullValue();
        }
    }
}
