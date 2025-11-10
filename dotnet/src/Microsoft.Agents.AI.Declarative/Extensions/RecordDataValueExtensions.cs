// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Bot.ObjectModel;

/// <summary>
/// Extension methods for <see cref="RecordDataValue"/>.
/// </summary>
public static class RecordDataValueExtensions
{
    /// <summary>
    /// Retrieves a 'number' property from a <see cref="RecordDataValue"/>
    /// </summary>
    /// <param name="recordData">Instance of <see cref="RecordDataValue"/></param>
    /// <param name="propertyPath">Path of the property to retrieve</param>
    public static decimal? GetNumber(this RecordDataValue recordData, string propertyPath)
    {
        Throw.IfNull(recordData);

        var numberValue = recordData.GetPropertyOrNull<NumberDataValue>(InitializablePropertyPath.Create(propertyPath));
        return numberValue?.Value;
    }

    /// <summary>
    /// Retrieves a nullable boolean value from the specified property path within the given record data.
    /// </summary>
    /// <param name="recordData">Instance of <see cref="RecordDataValue"/></param>
    /// <param name="propertyPath">Path of the property to retrieve</param>
    public static bool? GetBoolean(this RecordDataValue recordData, string propertyPath)
    {
        Throw.IfNull(recordData);

        var booleanValue = recordData.GetPropertyOrNull<BooleanDataValue>(InitializablePropertyPath.Create(propertyPath));
        return booleanValue?.Value;
    }

    /// <summary>
    /// Converts a <see cref="RecordDataValue"/> to a <see cref="IReadOnlyDictionary{TKey, TValue}"/>.
    /// </summary>
    /// <param name="recordData">Instance of <see cref="RecordDataValue"/></param>
    public static IReadOnlyDictionary<string, string> ToDictionary(this RecordDataValue recordData)
    {
        Throw.IfNull(recordData);

        return recordData.Properties.ToDictionary(
            kvp => kvp.Key,
            kvp => kvp.Value?.ToString() ?? string.Empty
        );
    }

    /// <summary>
    /// Retrieves the 'schema' property from a <see cref="RecordDataValue"/>.
    /// </summary>
    /// <param name="recordData">Instance of <see cref="RecordDataValue"/></param>
#pragma warning disable IL2026 // Members annotated with 'RequiresUnreferencedCodeAttribute' require dynamic access otherwise can break functionality when trimming application code
#pragma warning disable IL3050 // Calling members annotated with 'RequiresDynamicCodeAttribute' may break functionality when AOT compiling.
    public static JsonElement? GetSchema(this RecordDataValue recordData)
    {
        Throw.IfNull(recordData);

        try
        {
            var schemaStr = recordData.GetPropertyOrNull<StringDataValue>(InitializablePropertyPath.Create("json_schema.schema"));
            if (schemaStr?.Value is not null)
            {
                return JsonSerializer.Deserialize<JsonElement>(schemaStr.Value);
            }
        }
        catch (InvalidCastException)
        {
            // Ignore and try next
        }

        var responseFormRec = recordData.GetPropertyOrNull<RecordDataValue>(InitializablePropertyPath.Create("json_schema.schema"));
        if (responseFormRec is not null)
        {
            var json = JsonSerializer.Serialize(responseFormRec, ElementSerializer.CreateOptions());
            return JsonSerializer.Deserialize<JsonElement>(json);
        }

        return null;
    }
#pragma warning restore IL3050 // Calling members annotated with 'RequiresDynamicCodeAttribute' may break functionality when AOT compiling.
#pragma warning restore IL2026 // Members annotated with 'RequiresUnreferencedCodeAttribute' require dynamic access otherwise can break functionality when trimming application code

    internal static object? ToObject(this DataValue? value)
    {
        if (value is null)
        {
            return null;
        }
        return value switch
        {
            StringDataValue s => s.Value,
            NumberDataValue n => n.Value,
            BooleanDataValue b => b.Value,
            TableDataValue t => t.Values.Select(v => v.ToObject()).ToList(),
            RecordDataValue r => r.Properties.ToDictionary(kvp => kvp.Key, kvp => kvp.Value?.ToObject()),
            _ => throw new NotSupportedException($"Unsupported DataValue type: {value.GetType().FullName}"),
        };
    }
}
