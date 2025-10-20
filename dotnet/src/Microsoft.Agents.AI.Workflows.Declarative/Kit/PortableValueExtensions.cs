// Copyright (c) Microsoft. All rights reserved.

using System.Collections;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using Microsoft.Agents.AI.Workflows.Declarative.Extensions;
using Microsoft.PowerFx.Types;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Workflows.Declarative.Kit;

/// <summary>
/// Extension helpers for converting <see cref="PortableValue"/> instances (and collections containing them)
/// into their normalized runtime representations (primarily <see cref="FormulaValue"/> primitives) ready for evaluation.
/// </summary>
public static class PortableValueExtensions
{
    /// <summary>
    /// Normalizes all values in the provided dictionary. Each entry whose value is a <see cref="PortableValue"/>
    /// is converted to its underlying normalized representation; non-PortableValue entries are preserved as-is.
    /// </summary>
    /// <param name="source">The source dictionary whose values may contain <see cref="PortableValue"/> instances; may be null.</param>
    /// <returns>
    /// A new dictionary with normalized values, or null if <paramref name="source"/> is null.
    /// Keys are copied unchanged.
    /// </returns>
    public static IDictionary<string, object?>? NormalizePortableValues(this IDictionary<string, object?>? source)
    {
        if (source is null)
        {
            return null;
        }

        return source.ToDictionary(kvp => kvp.Key, kvp => kvp.Value.NormalizePortableValue());
    }

    /// <summary>
    /// Normalizes an arbitrary value if it is a <see cref="PortableValue"/>; otherwise returns the value unchanged.
    /// </summary>
    /// <param name="value">The value to normalize; may be null or already a primitive/object.</param>
    /// <returns>
    /// Null if <paramref name="value"/> is null; the normalized result if it is a <see cref="PortableValue"/>;
    /// otherwise the original <paramref name="value"/>.
    /// </returns>
    public static object? NormalizePortableValue(this object? value) =>
        Throw.IfNull(value, nameof(value)) switch
        {
            null => null,
            JsonElement jsonValue => jsonValue.GetValue(),
            PortableValue portableValue => portableValue.Normalize(),
            _ => value,
        };

    /// <summary>
    /// Converts a <see cref="PortableValue"/> into a concrete representation suitable for evaluation.
    /// </summary>
    /// <param name="value">The portable value to normalize; cannot be null.</param>
    /// <returns>
    /// A <see cref="object"/> instance representing the underlying value.
    /// </returns>
    public static object? Normalize(this PortableValue value) =>
        Throw.IfNull(value, nameof(value)).TypeId switch
        {
            _ when value.IsType(out string? stringValue) => stringValue,
            _ when value.IsSystemType(out bool? boolValue) => boolValue.Value,
            _ when value.IsSystemType(out int? intValue) => intValue.Value,
            _ when value.IsSystemType(out long? longValue) => longValue.Value,
            _ when value.IsSystemType(out decimal? decimalValue) => decimalValue.Value,
            _ when value.IsSystemType(out float? floatValue) => floatValue.Value,
            _ when value.IsSystemType(out double? doubleValue) => doubleValue.Value,
            _ when value.IsParentType(out IDictionary? recordValue) => recordValue.NormalizePortableValues(),
            _ when value.IsParentType(out IEnumerable? listValue) => listValue.NormalizePortableValues(),
            _ => throw new DeclarativeActionException($"Unsupported portable type: {value.TypeId.TypeName}"),
        };

    private static Dictionary<string, object?> NormalizePortableValues(this IDictionary source)
    {
        return GetValues().ToDictionary(kvp => kvp.Key, kvp => kvp.Value);

        IEnumerable<KeyValuePair<string, object?>> GetValues()
        {
            foreach (DictionaryEntry entry in source)
            {
                yield return new KeyValuePair<string, object?>((string)entry.Key, entry.Value.NormalizePortableValue());
            }
        }
    }

    private static object?[] NormalizePortableValues(this IEnumerable source) =>
        source.Cast<object?>().Select(NormalizePortableValue).ToArray();

    private static object? GetValue(this JsonElement element) =>
        element.ValueKind switch
        {
            JsonValueKind.String => element.GetString(),
            JsonValueKind.True => true,
            JsonValueKind.False => false,
            JsonValueKind.Null => null,
            JsonValueKind.Number => element.TryGetInt64(out long longValue) ? longValue : element.GetDouble(),
            JsonValueKind.Object => element.EnumerateObject().ToDictionary(p => p.Name, p => p.Value.GetValue()),
            JsonValueKind.Array => element.EnumerateArray().Select(e => e.GetValue()).ToArray(),
            _ => throw new DeclarativeActionException($"Unsupported JSON value kind: {element.ValueKind}"),
        };
}
