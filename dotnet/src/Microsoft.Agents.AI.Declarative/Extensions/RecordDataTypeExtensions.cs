// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Text.Json;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Bot.ObjectModel;

/// <summary>
/// Extension methods for <see cref="RecordDataType"/>.
/// </summary>
public static class RecordDataTypeExtensions
{
    /// <summary>
    /// Creates a <see cref="ChatResponseFormat"/> from a <see cref="RecordDataType"/>.
    /// </summary>
    /// <param name="recordDataType">Instance of <see cref="RecordDataType"/></param>
    public static ChatResponseFormat? AsResponseFormat(this RecordDataType recordDataType)
    {
        Throw.IfNull(recordDataType);

        return ChatResponseFormat.ForJsonSchema(
            schema: recordDataType.GetSchema(),
            schemaName: null,
            schemaDescription: null);
    }

    /// <summary>
    /// Converts a <see cref="RecordDataType"/> to a <see cref="JsonElement"/>.
    /// </summary>
    /// <param name="recordDataType">Instance of <see cref="RecordDataType"/></param>
#pragma warning disable IL2026 // Members annotated with 'RequiresUnreferencedCodeAttribute' require dynamic access otherwise can break functionality when trimming application code
#pragma warning disable IL3050 // Calling members annotated with 'RequiresDynamicCodeAttribute' may break functionality when AOT compiling.
    public static JsonElement GetSchema(this RecordDataType recordDataType)
    {
        Throw.IfNull(recordDataType);

        var schemaObject = new Dictionary<string, object>
        {
            ["type"] = "object",
            ["properties"] = BuildProperties(recordDataType.Properties),
            ["additionalProperties"] = false
        };

        var json = JsonSerializer.Serialize(schemaObject, ElementSerializer.CreateOptions());
        return JsonSerializer.Deserialize<JsonElement>(json);
    }
#pragma warning restore IL3050 // Calling members annotated with 'RequiresDynamicCodeAttribute' may break functionality when AOT compiling.
#pragma warning restore IL2026 // Members annotated with 'RequiresUnreferencedCodeAttribute' require dynamic access otherwise can break functionality when trimming application code

    #region private
    private static Dictionary<string, object> BuildProperties(IReadOnlyDictionary<string, PropertyInfo> properties)
    {
        var result = new Dictionary<string, object>();

        foreach (var property in properties)
        {
            result[property.Key] = BuildPropertySchema(property.Value);
        }

        return result;
    }

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
                    ["properties"] = BuildProperties(tableType.Properties),
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
