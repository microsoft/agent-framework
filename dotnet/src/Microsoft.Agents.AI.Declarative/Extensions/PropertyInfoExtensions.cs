// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Text.Json;

namespace Microsoft.Bot.ObjectModel;

/// <summary>
/// Extension methods for <see cref="PropertyInfo"/>.
/// </summary>
public static class PropertyInfoExtensions
{
    /// <summary>
    ///  Creates a <see cref="Dictionary{TKey, TValue}"/> of <see cref="string"/> and <see cref="object"/>
    ///  from an <see cref="IReadOnlyDictionary{TKey, TValue}"/> of <see cref="string"/> and <see cref="PropertyInfo"/>.
    /// </summary>
    /// <param name="properties">A read-only dictionary of property names and their corresponding <see cref="PropertyInfo"/> objects.</param>
    public static Dictionary<string, object> AsObjectDictionary(this IReadOnlyDictionary<string, PropertyInfo> properties)
    {
        var result = new Dictionary<string, object>();

        foreach (var property in properties)
        {
            result[property.Key] = BuildPropertySchema(property.Value);
        }

        return result;
    }

    #region private
    private static Dictionary<string, object> BuildPropertySchema(PropertyInfo propertyInfo)
    {
        var propertySchema = new Dictionary<string, object>();

        // Map the DataType to JSON schema type and add type-specific properties
        switch (propertyInfo.Type)
        {
            case StringDataType:
                propertySchema["type"] = "string";
                break;
            case NumberDataType:
                propertySchema["type"] = "number";
                break;
            case BooleanDataType:
                propertySchema["type"] = "boolean";
                break;
            case DateTimeDataType:
                propertySchema["type"] = "string";
                propertySchema["format"] = "date-time";
                break;
            case DateDataType:
                propertySchema["type"] = "string";
                propertySchema["format"] = "date";
                break;
            case TimeDataType:
                propertySchema["type"] = "string";
                propertySchema["format"] = "time";
                break;
            case RecordDataType nestedRecordType:
#pragma warning disable IL2026, IL3050
                // For nested records, recursively build the schema
                var nestedSchema = nestedRecordType.GetSchema();
                var nestedJson = JsonSerializer.Serialize(nestedSchema, ElementSerializer.CreateOptions());
                var nestedDict = JsonSerializer.Deserialize<Dictionary<string, object>>(nestedJson, ElementSerializer.CreateOptions());
#pragma warning restore IL2026, IL3050
                if (nestedDict != null)
                {
                    return nestedDict;
                }
                propertySchema["type"] = "object";
                break;
            case TableDataType tableType:
                propertySchema["type"] = "array";
                // TableDataType has Properties like RecordDataType
                propertySchema["items"] = new Dictionary<string, object>
                {
                    ["type"] = "object",
                    ["properties"] = AsObjectDictionary(tableType.Properties),
                    ["additionalProperties"] = false
                };
                break;
            default:
                propertySchema["type"] = "string";
                break;
        }

        // Add description if available
        if (!string.IsNullOrEmpty(propertyInfo.Description))
        {
            propertySchema["description"] = propertyInfo.Description;
        }

        return propertySchema;
    }
    #endregion
}
