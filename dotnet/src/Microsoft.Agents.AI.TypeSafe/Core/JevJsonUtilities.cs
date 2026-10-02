// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Buffers;
using System.Collections.Generic;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.Json.Serialization.Metadata;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.TypeSafe;

/// <summary>
/// Serializer options, JSON schemas, and JSON value helpers shared by the Jev tool and chat client.
/// </summary>
internal static class JevJsonUtilities
{
    private static readonly JsonElement s_true = Parse("true");
    private static readonly JsonElement s_false = Parse("false");
    private static readonly JsonElement s_null = Parse("null");
    private static readonly AIJsonSchemaCreateOptions s_schemaOptions = new() { TransformSchemaNode = DescribeEntries };
    private static readonly Lazy<JsonElement> s_requestSchema = new(static () => AIJsonUtilities.CreateJsonSchema(typeof(JevRequest), serializerOptions: Options, inferenceOptions: s_schemaOptions));
    private static readonly Lazy<JsonElement> s_resultSchema = new(static () => AIJsonUtilities.CreateJsonSchema(typeof(JevResult), serializerOptions: Options, inferenceOptions: s_schemaOptions));

    /// <summary>
    /// Gets the options that resolve the Jev contract types first and every other type through
    /// <see cref="AIJsonUtilities.DefaultOptions"/>.
    /// </summary>
    public static JsonSerializerOptions Options { get; } = CreateOptions();

    /// <summary>Gets the JSON schema of the tool arguments, which is the schema of <see cref="JevRequest"/>.</summary>
    public static JsonElement RequestSchema => s_requestSchema.Value;

    /// <summary>Gets the JSON schema of the tool result, which is the schema of <see cref="JevResult"/>.</summary>
    public static JsonElement ResultSchema => s_resultSchema.Value;

    /// <summary>
    /// Converts one tool argument into a JSON node. Chat clients pass arguments as <see cref="JsonElement"/> values;
    /// callers that invoke the function directly may pass .NET objects instead.
    /// </summary>
    public static JsonNode? ToNode(object? value) =>
        value switch
        {
            null => null,
            JsonNode node => node.DeepClone(),
            JsonElement element => element.ValueKind switch
            {
                JsonValueKind.Object => JsonObject.Create(element),
                JsonValueKind.Array => JsonArray.Create(element),
                JsonValueKind.Null or JsonValueKind.Undefined => null,
                _ => JsonValue.Create(element),
            },
            _ => JsonSerializer.SerializeToNode(value, Options.GetTypeInfo(value.GetType())),
        };

    /// <summary>
    /// Converts a value from a chat message, such as a function argument or result, into a JSON node. A value that
    /// cannot be serialized, for example a type without metadata under native AOT, becomes its text.
    /// </summary>
    public static JsonNode? ToNodeOrText(object? value)
    {
        try
        {
            return ToNode(value);
        }
        catch (Exception ex) when (ex is NotSupportedException or InvalidOperationException or JsonException or ArgumentException)
        {
            // Chat history is informational for Jev, so an unserializable value is described rather than failing
            // the whole request.
            return JsonValue.Create(value?.ToString());
        }
    }

    /// <summary>Converts a value from a chat message into a detached <see cref="JsonElement"/>, like <see cref="ToNodeOrText"/>.</summary>
    public static JsonElement ToElement(object? value) =>
        value switch
        {
            JsonElement element => element.ValueKind == JsonValueKind.Undefined ? s_null : element.Clone(),
            null => s_null,
            _ => Parse(ToNodeOrText(value)?.ToJsonString() ?? "null"),
        };

    /// <summary>Gets the JSON <see langword="true"/> or <see langword="false"/> value.</summary>
    public static JsonElement CreateBoolean(bool value) => value ? s_true : s_false;

    /// <summary>Writes values into a new JSON array.</summary>
    public static JsonElement CreateArray(IEnumerable<JsonElement> values)
    {
        var buffer = new ArrayBufferWriter<byte>();
        using (var writer = new Utf8JsonWriter(buffer))
        {
            writer.WriteStartArray();
            foreach (JsonElement value in values)
            {
                value.WriteTo(writer);
            }

            writer.WriteEndArray();
        }

        using JsonDocument document = JsonDocument.Parse(buffer.WrittenMemory);
        return document.RootElement.Clone();
    }

    /// <summary>Parses JSON text into a detached <see cref="JsonElement"/>.</summary>
    public static JsonElement Parse(string json)
    {
        using JsonDocument document = JsonDocument.Parse(json);
        return document.RootElement.Clone();
    }

    private static JsonSerializerOptions CreateOptions()
    {
        var options = new JsonSerializerOptions(JevJsonContext.Default.Options)
        {
            TypeInfoResolver = JsonTypeInfoResolver.Combine(JevJsonContext.Default, AIJsonUtilities.DefaultOptions.TypeInfoResolver),
        };

        options.MakeReadOnly();
        return options;
    }

    /// <summary>
    /// Gives <see cref="JevEntry"/> the schema of the SDK's <c>EntryType</c>, narrowed to what the API accepts. Its
    /// custom converter hides the shape from the schema generator, which would otherwise allow any JSON value, and
    /// entries inside collections are only reachable from the collection's node.
    /// </summary>
    /// <remarks>
    /// The API rejects a <see langword="null"/> state and <see langword="null"/> Score rubric entries even though the
    /// SDK types allow them, so those schemas leave <see langword="null"/> out; the size limits tell the model how many
    /// alternatives and scores it may send.
    /// </remarks>
    private static JsonNode DescribeEntries(AIJsonSchemaCreateContext context, JsonNode schema)
    {
        Type type = context.TypeInfo.Type;
        if (type == typeof(JevEntry))
        {
            // JevRequest.State is the only non-nullable single entry.
            return WithEntryType(schema, allowNull: false);
        }

        if (type == typeof(JevEntry?))
        {
            return WithEntryType(schema, allowNull: true);
        }

        if (type == typeof(IReadOnlyList<JevEntry>) && schema is JsonObject rubric)
        {
            rubric["items"] = WithEntryType(new JsonObject(), allowNull: false);
            rubric["minItems"] = JevContractValidator.MinScoreCriteria;
            rubric["maxItems"] = JevContractValidator.MaxScoreCriteria;
            return rubric;
        }

        if (type == typeof(IReadOnlyDictionary<string, JevEntry>) && schema is JsonObject map)
        {
            // Choice criteria may leave an alternative undescribed; a Score legend echoes the rubric, which may not.
            bool isChoiceCriteria = context.PropertyInfo?.Name == "criteria";
            map["additionalProperties"] = WithEntryType(new JsonObject(), allowNull: isChoiceCriteria);
            if (isChoiceCriteria)
            {
                map["minProperties"] = 1;
                map["maxProperties"] = JevContractValidator.MaxChoiceCriteria;
            }

            return map;
        }

        return schema;
    }

    private static JsonObject WithEntryType(JsonNode schema, bool allowNull)
    {
        JsonObject entry = schema as JsonObject ?? [];
        entry["type"] = allowNull
            ? new JsonArray("string", "object", "array", "null")
            : new JsonArray("string", "object", "array");
        return entry;
    }
}
