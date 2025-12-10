// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics.CodeAnalysis;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Text.Json.Serialization.Metadata;

namespace Microsoft.Agents.AI.Workflows.Checkpointing;

/// <summary>
/// Provides support for using <typeparamref name="T"/> values as dictionary keys when serializing and deserializing JSON.
/// It chains to the provided <see cref="JsonTypeInfo{T}"/> for serialization and deserialization when not used as a property
/// name.
/// </summary>
/// <typeparam name="T"></typeparam>
internal abstract class JsonConverterDictionarySupportBase<T> : JsonConverterBase<T>
{
    protected abstract string Stringify([DisallowNull] T value);
    protected abstract T Parse(string propertyName);

    [return: NotNull]
    protected static string Escape(string? value, char escapeChar = '|', bool allowNullAndPad = false, [CallerArgumentExpression(nameof(value))] string? componentName = null)
    {
        if (!allowNullAndPad && value is null)
        {
            throw new JsonException($"Invalid {componentName} '{value}'. Expecting non-null string.");
        }

        if (value is null)
        {
            return string.Empty;
        }

        string unescaped = escapeChar.ToString();
        string escaped = new(escapeChar, 2);

        if (allowNullAndPad)
        {
            return $"@{value.Replace(unescaped, escaped)}";
        }

        return $"{value.Replace(unescaped, escaped)}";
    }

    protected static string? Unescape([DisallowNull] string value, char escapeChar = '|', bool allowNullAndPad = false, [CallerArgumentExpression(nameof(value))] string? componentName = null)
    {
        if (value.Length == 0)
        {
            if (!allowNullAndPad)
            {
                throw new JsonException($"Invalid {componentName} '{value}'. Expecting empty string or a value that is prefixed with '@'.");
            }

            return null;
        }

        if (allowNullAndPad && value[0] != '@')
        {
            throw new JsonException($"Invalid {componentName} component '{value}'. Expecting empty string or a value that is prefixed with '@'.");
        }

        if (allowNullAndPad)
        {
            value = value.Substring(1);
        }

        string unescaped = escapeChar.ToString();
        string escaped = new(escapeChar, 2);
        return value.Replace(escaped, unescaped);
    }

    public override T ReadAsPropertyName(ref Utf8JsonReader reader, Type typeToConvert, JsonSerializerOptions options)
    {
        SequencePosition position = reader.Position;

        string? propertyName = reader.GetString() ??
            throw new JsonException($"Got null trying to read property name at position {position}");

        return this.Parse(propertyName);
    }

    public override void WriteAsPropertyName(Utf8JsonWriter writer, [DisallowNull] T value, JsonSerializerOptions options)
    {
        string propertyName = this.Stringify(value);
        writer.WritePropertyName(propertyName);
    }
}
