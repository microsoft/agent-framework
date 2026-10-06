// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Text;
using System.Text.Json;

namespace Microsoft.Agents.AI.TypeSafe;

/// <summary>
/// Reads the JSON schemas of tool parameters for <see cref="JevToolCallCompiler"/>: which keywords are allowed where,
/// how references and nullable forms resolve, and how values are described to Jev.
/// </summary>
internal static class JevToolSchema
{
    // A schema definition may refer to itself; without a limit its resolution would never end.
    private const int MaxResolutionDepth = 16;

    private static readonly string[] s_annotationKeys = ["$comment", "$id", "$schema", "default", "deprecated", "description", "examples", "readOnly", "title", "writeOnly"];

    /// <summary>Gets the keywords that do not constrain a value, so they are allowed anywhere.</summary>
    public static HashSet<string> AnnotationKeys { get; } = new(s_annotationKeys, StringComparer.Ordinal);

    /// <summary>Gets the keywords allowed on the object schema of a tool's parameters.</summary>
    public static HashSet<string> RootKeys { get; } = new(s_annotationKeys.Concat(["$defs", "additionalProperties", "properties", "required", "type"]), StringComparer.Ordinal);

    /// <summary>Gets the keywords allowed on the schema of one argument.</summary>
    public static HashSet<string> ArgumentKeys { get; } = new(s_annotationKeys.Concat(["const", "enum", "items", "type"]), StringComparer.Ordinal);

    /// <summary>Gets the keywords allowed on the item schema of an array argument.</summary>
    public static HashSet<string> ArrayItemKeys { get; } = new(s_annotationKeys.Concat(["enum", "type"]), StringComparer.Ordinal);

    public static Dictionary<string, JsonElement> ToMap(JsonElement schema)
    {
        var map = new Dictionary<string, JsonElement>(StringComparer.Ordinal);
        foreach (JsonProperty property in schema.EnumerateObject())
        {
            map[property.Name] = property.Value;
        }

        return map;
    }

    /// <summary>
    /// Resolves a local <c>$ref</c>, an <c>anyOf</c> of one schema and <c>null</c>, and the nullable forms that
    /// System.Text.Json writes, which are a type array that includes <c>"null"</c> and an enum that lists
    /// <see langword="null"/>.
    /// </summary>
    /// <returns>The schema without its <see langword="null"/> alternative, and whether it allowed <see langword="null"/>.</returns>
    public static (Dictionary<string, JsonElement> Schema, bool Nullable) Resolve(Dictionary<string, JsonElement> schema, Dictionary<string, JsonElement> root, int depth = 0)
    {
        if (depth > MaxResolutionDepth)
        {
            throw new JevUnsupportedToolSchemaException("schema references are nested too deeply");
        }

        var resolved = new Dictionary<string, JsonElement>(schema, StringComparer.Ordinal);

        // A definition can itself be a reference, such as an alias of another definition, so references are followed
        // until a schema without one. A cycle would never end, so the chain is bounded like nested resolution.
        for (int hops = 0; resolved.Remove("$ref", out JsonElement reference); hops++)
        {
            if (depth + hops >= MaxResolutionDepth)
            {
                throw new JevUnsupportedToolSchemaException("schema references are nested too deeply");
            }

            RejectCompositionSiblings(resolved, "$ref");
            string? path = reference.ValueKind == JsonValueKind.String ? reference.GetString() : null;
            const string DefinitionsPrefix = "#/$defs/";
            if (path?.StartsWith(DefinitionsPrefix, StringComparison.Ordinal) is not true)
            {
                throw new JevUnsupportedToolSchemaException("only local $defs references are supported");
            }

            if (!root.TryGetValue("$defs", out JsonElement definitions) ||
                definitions.ValueKind != JsonValueKind.Object ||
                !definitions.TryGetProperty(path.Substring(DefinitionsPrefix.Length), out JsonElement definition) ||
                definition.ValueKind != JsonValueKind.Object)
            {
                throw new JevUnsupportedToolSchemaException($"unresolved schema reference '{path}'");
            }

            // Annotations next to the reference, such as a description, override those of the definition, so the
            // annotations closest to the argument win along a chain. An anyOf inside the definition is resolved below,
            // together with the rest of the merged schema.
            resolved = Merge(ToMap(definition), resolved);
        }

        bool nullable = false;
        if (resolved.Remove("anyOf", out JsonElement anyOf))
        {
            RejectCompositionSiblings(resolved, "anyOf");
            if (anyOf.ValueKind != JsonValueKind.Array)
            {
                throw new JevUnsupportedToolSchemaException("anyOf must be an array");
            }

            List<JsonElement> arms = [.. anyOf.EnumerateArray()];
            List<JsonElement> nullArms = [.. arms.Where(arm => arm.ValueKind == JsonValueKind.Object && IsNullSchema(arm))];
            List<JsonElement> valueArms = [.. arms.Where(arm => arm.ValueKind == JsonValueKind.Object && !IsNullSchema(arm))];
            if (arms.Count != 2 || nullArms.Count != 1 || valueArms.Count != 1)
            {
                throw new JevUnsupportedToolSchemaException("only a single schema combined with null is supported");
            }

            (Dictionary<string, JsonElement> nested, _) = Resolve(ToMap(valueArms[0]), root, depth + 1);
            resolved = Merge(nested, resolved);
            nullable = true;
        }

        if (resolved.TryGetValue("type", out JsonElement type) && type.ValueKind == JsonValueKind.Array && type.EnumerateArray().Any(IsNullName))
        {
            List<JsonElement> valueTypes = [.. type.EnumerateArray().Where(item => !IsNullName(item))];
            resolved["type"] = valueTypes.Count == 1 ? valueTypes[0] : JevJsonUtilities.CreateArray(valueTypes);
            nullable = true;
        }

        if (resolved.TryGetValue("enum", out JsonElement values) && values.ValueKind == JsonValueKind.Array && values.EnumerateArray().Any(value => value.ValueKind == JsonValueKind.Null))
        {
            resolved["enum"] = JevJsonUtilities.CreateArray(values.EnumerateArray().Where(value => value.ValueKind != JsonValueKind.Null));
            nullable = true;
        }

        return (resolved, nullable);
    }

    public static void RejectUnsupportedKeys(Dictionary<string, JsonElement> schema, HashSet<string> supportedKeys, string location)
    {
        List<string> unsupported = [.. schema.Keys.Where(key => !supportedKeys.Contains(key)).OrderBy(key => key, StringComparer.Ordinal)];
        if (unsupported.Count > 0)
        {
            throw new JevUnsupportedToolSchemaException($"unsupported {location} schema constraints: {string.Join(", ", unsupported)}");
        }
    }

    /// <summary>
    /// Reads a <c>type</c> keyword, which is a type name or a non-empty array of type names.
    /// </summary>
    public static IReadOnlyList<string> GetTypes(JsonElement? type, string location)
    {
        if (type is not { } value || value.ValueKind == JsonValueKind.Null)
        {
            return [];
        }

        if (value.ValueKind == JsonValueKind.String)
        {
            return [value.GetString()!];
        }

        if (value.ValueKind == JsonValueKind.Array && value.GetArrayLength() > 0 && value.EnumerateArray().All(item => item.ValueKind == JsonValueKind.String))
        {
            return [.. value.EnumerateArray().Select(item => item.GetString()!)];
        }

        throw new JevUnsupportedToolSchemaException($"{location} type must be a string or non-empty string array");
    }

    public static bool MatchesType(JsonElement value, string type) =>
        type switch
        {
            "string" => value.ValueKind == JsonValueKind.String,

            // An integer has no fraction or exponent, as a JSON parser that separates integers from floats reads it,
            // and may be of any size, like a Python int; a long would reject valid unsigned 64-bit values.
            "integer" => value.ValueKind == JsonValueKind.Number && value.GetRawText().AsSpan().IndexOfAny('.', 'e', 'E') < 0,
            "number" => value.ValueKind == JsonValueKind.Number,
            "boolean" => value.ValueKind is JsonValueKind.True or JsonValueKind.False,
            "null" => value.ValueKind == JsonValueKind.Null,
            "array" => value.ValueKind == JsonValueKind.Array,
            "object" => value.ValueKind == JsonValueKind.Object,
            _ => false,
        };

    /// <summary>
    /// Checks that every <c>const</c> or <c>enum</c> value of a schema matches its declared <c>type</c>.
    /// </summary>
    /// <remarks>
    /// A value of another type can never be a valid argument, for example <c>"fast"</c> for an integer. Jev would
    /// still choose it, and the call would fail only when the function binds its arguments, so such a tool is left out
    /// of routing instead. A schema without a <c>type</c> is not checked.
    /// </remarks>
    /// <param name="schema">The resolved schema whose <c>type</c> applies.</param>
    /// <param name="values">The values to check.</param>
    /// <param name="location">Where the schema is, for the message about an invalid <c>type</c> keyword.</param>
    /// <param name="valueName">How a value is named in the message, such as <c>enum value</c>.</param>
    /// <param name="typeName">How the type is named in the message, such as <c>type</c>.</param>
    public static void EnsureValuesMatchType(Dictionary<string, JsonElement> schema, IEnumerable<JsonElement> values, string location, string valueName, string typeName)
    {
        IReadOnlyList<string> types = GetTypes(schema.TryGetValue("type", out JsonElement type) ? type : null, location);
        if (types.Count == 0)
        {
            return;
        }

        foreach (JsonElement value in values)
        {
            if (!types.Any(candidate => MatchesType(value, candidate)))
            {
                string declared = types.Count == 1 ? $"\"{types[0]}\"" : Describe(types.Select(candidate => JevJsonUtilities.ToElement(candidate)));
                throw new JevUnsupportedToolSchemaException($"{valueName} {Describe(value)} does not match declared {typeName} {declared}");
            }
        }
    }

    /// <summary>
    /// Writes a value the way the Python connector does with <c>json.dumps(value, ensure_ascii=False, sort_keys=True)</c>:
    /// sorted object keys, <c>", "</c> and <c>": "</c> separators, and unescaped text. Jev reads these values in
    /// criteria and instructions, so both connectors send the same words.
    /// </summary>
    public static string Describe(JsonElement value)
    {
        var builder = new StringBuilder();
        AppendValue(builder, value);
        return builder.ToString();
    }

    /// <summary>Writes values as a JSON array, like <see cref="Describe(JsonElement)"/>.</summary>
    public static string Describe(IEnumerable<JsonElement> values)
    {
        var builder = new StringBuilder();
        AppendArray(builder, values, AppendValue);
        return builder.ToString();
    }

    /// <summary>Writes the argument sets of earlier calls as a JSON array of objects, like <see cref="Describe(JsonElement)"/>.</summary>
    public static string Describe(IEnumerable<IReadOnlyDictionary<string, JsonElement>> calls)
    {
        var builder = new StringBuilder();
        AppendArray(builder, calls, static (target, call) => AppendObject(target, call.Select(argument => new KeyValuePair<string, JsonElement>(argument.Key, argument.Value))));
        return builder.ToString();
    }

    private static void RejectCompositionSiblings(Dictionary<string, JsonElement> schema, string keyword)
    {
        List<string> siblings = [.. schema.Keys.Where(key => !AnnotationKeys.Contains(key)).OrderBy(key => key, StringComparer.Ordinal)];
        if (siblings.Count > 0)
        {
            throw new JevUnsupportedToolSchemaException($"{keyword} sibling constraints are not supported: {string.Join(", ", siblings)}");
        }
    }

    private static Dictionary<string, JsonElement> Merge(Dictionary<string, JsonElement> target, Dictionary<string, JsonElement> overrides)
    {
        foreach (KeyValuePair<string, JsonElement> entry in overrides)
        {
            target[entry.Key] = entry.Value;
        }

        return target;
    }

    private static bool IsNullSchema(JsonElement schema) =>
        schema.TryGetProperty("type", out JsonElement type) && IsNullName(type);

    private static bool IsNullName(JsonElement type) =>
        type.ValueKind == JsonValueKind.String && type.ValueEquals("null");

    private static void AppendValue(StringBuilder builder, JsonElement value)
    {
        switch (value.ValueKind)
        {
            case JsonValueKind.Object:
                AppendObject(builder, value.EnumerateObject().Select(property => new KeyValuePair<string, JsonElement>(property.Name, property.Value)));
                break;

            case JsonValueKind.Array:
                AppendArray(builder, value.EnumerateArray(), AppendValue);
                break;

            case JsonValueKind.String:
                AppendString(builder, value.GetString()!);
                break;

            case JsonValueKind.Null or JsonValueKind.Undefined:
                builder.Append("null");
                break;

            default:
                // Numbers keep their original text, and true and false are already written as JSON.
                builder.Append(value.GetRawText());
                break;
        }
    }

    private static void AppendObject(StringBuilder builder, IEnumerable<KeyValuePair<string, JsonElement>> properties)
    {
        builder.Append('{');
        bool first = true;
        foreach (KeyValuePair<string, JsonElement> property in properties.OrderBy(property => property.Key, StringComparer.Ordinal))
        {
            builder.Append(first ? string.Empty : ", ");
            first = false;
            AppendString(builder, property.Key);
            builder.Append(": ");
            AppendValue(builder, property.Value);
        }

        builder.Append('}');
    }

    private static void AppendArray<T>(StringBuilder builder, IEnumerable<T> items, Action<StringBuilder, T> append)
    {
        builder.Append('[');
        bool first = true;
        foreach (T item in items)
        {
            builder.Append(first ? string.Empty : ", ");
            first = false;
            append(builder, item);
        }

        builder.Append(']');
    }

    /// <summary>
    /// Writes a JSON string with the escapes of Python's <c>ensure_ascii=False</c>: quotes, backslashes, and control
    /// characters only.
    /// </summary>
    private static void AppendString(StringBuilder builder, string text)
    {
        builder.Append('"');
        foreach (char c in text)
        {
            switch (c)
            {
                case '"': builder.Append("\\\""); break;
                case '\\': builder.Append("\\\\"); break;
                case '\n': builder.Append("\\n"); break;
                case '\r': builder.Append("\\r"); break;
                case '\t': builder.Append("\\t"); break;
                case '\b': builder.Append("\\b"); break;
                case '\f': builder.Append("\\f"); break;
                case < ' ': builder.Append("\\u").Append(((int)c).ToString("x4", CultureInfo.InvariantCulture)); break;
                default: builder.Append(c); break;
            }
        }

        builder.Append('"');
    }
}
