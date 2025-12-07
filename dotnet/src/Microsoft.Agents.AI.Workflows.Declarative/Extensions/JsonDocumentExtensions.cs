// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Frozen;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Text.Json;
using Microsoft.Agents.AI.Workflows.Declarative.Kit;

namespace Microsoft.Agents.AI.Workflows.Declarative.Extensions;

internal static class JsonDocumentExtensions
{
    public static List<object?> ParseList(this JsonDocument jsonDocument, VariableType targetType)
    {
        return
            jsonDocument.RootElement.ValueKind switch
            {
                JsonValueKind.Array => jsonDocument.RootElement.ParseTable(targetType),
                JsonValueKind.Object when targetType.HasSchema => [jsonDocument.RootElement.ParseRecord(targetType)],
                JsonValueKind.Null => [],
                _ => [jsonDocument.RootElement.ParseValue(targetType)],
            };
    }

    public static Dictionary<string, object?> ParseRecord(this JsonDocument jsonDocument, VariableType targetType)
    {
        if (!targetType.IsRecord)
        {
            throw new DeclarativeActionException($"Unable to convert JSON to object with requested type {targetType.Type.Name}.");
        }

        return
            jsonDocument.RootElement.ValueKind switch
            {
                JsonValueKind.Array when targetType.HasSchema =>
                    ((Dictionary<string, object?>?)jsonDocument.RootElement.ParseTable(targetType).Single()) ?? [],
                JsonValueKind.Object => jsonDocument.RootElement.ParseRecord(targetType),
                JsonValueKind.Null => [],
                _ => throw new DeclarativeActionException($"Unable to convert JSON to object with requested type {targetType.Type.Name}."),
            };
    }

    private static Dictionary<string, object?> ParseRecord(this JsonElement currentElement, VariableType targetType)
    {
        IEnumerable<KeyValuePair<string, object?>> keyValuePairs =
            targetType.Schema is null ?
            ParseValues() :
            ParseSchema(targetType.Schema);

        return keyValuePairs.ToDictionary(kvp => kvp.Key, kvp => kvp.Value);

        IEnumerable<KeyValuePair<string, object?>> ParseValues()
        {
            foreach (JsonProperty objectProperty in currentElement.EnumerateObject())
            {
                if (!objectProperty.Value.TryParseValue(targetType: null, out object? parsedValue))
                {
                    throw new DeclarativeActionException($"Unsupported data type '{objectProperty.Value.ValueKind}' for property '{objectProperty.Name}'");
                }
                yield return new KeyValuePair<string, object?>(objectProperty.Name, parsedValue);
            }
        }

        IEnumerable<KeyValuePair<string, object?>> ParseSchema(FrozenDictionary<string, VariableType> schema)
        {
            foreach (KeyValuePair<string, VariableType> property in schema)
            {
                object? parsedValue = null;
                if (!currentElement.TryGetProperty(property.Key, out JsonElement propertyElement))
                {
                    if (!property.Value.Type.IsNullable())
                    {
                        throw new DeclarativeActionException($"Property '{property.Key}' undefined and not nullable.");
                    }
                }
                else if (!propertyElement.TryParseValue(property.Value, out parsedValue))
                {
                    throw new DeclarativeActionException($"Unsupported data type '{property.Value.Type}' for property '{property.Key}'");
                }

                yield return new KeyValuePair<string, object?>(property.Key, parsedValue);
            }
        }
    }

    private static List<object?> ParseTable(this JsonElement currentElement, VariableType targetType)
    {
        if (!targetType.IsList)
        {
            throw new DeclarativeActionException($"Unable to convert JSON to list as requested type {targetType.Type.Name}.");
        }

        VariableType listType = DetermineElementType();

        return
            currentElement
                .EnumerateArray()
                .Select(element => element.ParseValue(listType))
                .ToList();

        VariableType DetermineElementType()
        {
            Type? targetElementType = targetType.Type.GetElementType();
            VariableType? elementType = targetElementType is not null ? new(targetElementType) : null;
            if (elementType is null)
            {
                foreach (JsonElement element in currentElement.EnumerateArray())
                {
                    VariableType? currentType =
                        element.ValueKind switch
                        {
                            JsonValueKind.Object => VariableType.Record(targetType.Schema?.Select(kvp => (kvp.Key, kvp.Value)) ?? []),
                            JsonValueKind.String => typeof(string),
                            JsonValueKind.True => typeof(bool),
                            JsonValueKind.False => typeof(bool),
                            JsonValueKind.Number => typeof(decimal),
                            _ => null,
                        };

                    if (elementType is not null && currentType is not null && !elementType.Equals(currentType))
                    {
                        throw new DeclarativeActionException("Inconsistent element types in list.");
                    }

                    elementType ??= currentType;
                }
            }

            return
                elementType ??
                throw new DeclarativeActionException("Unable to determine element type for list.");
        }
    }

    private static object? ParseValue(this JsonElement propertyElement, VariableType targetType)
    {
        if (!propertyElement.TryParseValue(targetType, out object? value))
        {
            throw new DeclarativeActionException($"Unable to parse {propertyElement.ValueKind} as '{targetType.Type.Name}'");
        }

        return value;
    }

    private static bool TryParseValue(this JsonElement propertyElement, VariableType? targetType, out object? value) =>
        propertyElement.ValueKind switch
        {
            JsonValueKind.String => TryParseString(propertyElement, targetType?.Type, out value),
            JsonValueKind.Number => TryParseNumber(propertyElement, targetType?.Type, out value),
            JsonValueKind.True or JsonValueKind.False => TryParseBoolean(propertyElement, out value),
            JsonValueKind.Object => TryParseObject(propertyElement, targetType, out value),
            JsonValueKind.Array => TryParseList(propertyElement, targetType, out value),
            JsonValueKind.Null => TryParseNull(targetType?.Type, out value),
            _ => throw new DeclarativeActionException($"JSON element of type {propertyElement.ValueKind} is not supported."),
        };

    private static bool TryParseNull(Type? valueType, out object? value)
    {
        // If the target type is not nullable, we cannot assign null to it
        if (valueType?.IsNullable() == false)
        {
            value = null;
            return false;
        }

        value = null;
        return true;
    }

    private static bool TryParseBoolean(JsonElement propertyElement, out object? value)
    {
        try
        {
            value = propertyElement.GetBoolean();
            return true;
        }
        catch
        {
            value = null;
            return false;
        }
    }

    private static bool TryParseString(JsonElement propertyElement, Type? valueType, out object? value)
    {
        try
        {
            string? propertyValue = propertyElement.GetString();
            if (propertyValue is null)
            {
                value = null;
                return valueType?.IsNullable() ?? false; // Parse fails if value is null and requested type is not.
            }

            if (valueType is null)
            {
                value = propertyValue;
            }
            else
            {
                switch (valueType)
                {
                    case Type targetType when targetType == typeof(string):
                        value = propertyValue;
                        break;
                    case Type targetType when targetType == typeof(DateTime):
                        value = DateTime.Parse(propertyValue, provider: null, styles: DateTimeStyles.RoundtripKind);
                        break;
                    case Type targetType when targetType == typeof(TimeSpan):
                        value = TimeSpan.Parse(propertyValue);
                        break;
                    default:
                        value = null;
                        return false;
                }
            }

            return true;
        }
        catch
        {
            value = null;
            return false;
        }
    }

    private static bool TryParseNumber(JsonElement element, Type? valueType, out object? value)
    {
        // Try parsing as integer types first (most precise representation)
        if (element.TryGetInt32(out int intValue))
        {
            return ConvertToExpectedType(valueType, intValue, out value);
        }

        if (element.TryGetInt64(out long longValue))
        {
            return ConvertToExpectedType(valueType, longValue, out value);
        }

        // Try decimal for precise decimal values
        if (element.TryGetDecimal(out decimal decimalValue))
        {
            return ConvertToExpectedType(valueType, decimalValue, out value);
        }

        // Fall back to double for other numeric values
        if (element.TryGetDouble(out double doubleValue))
        {
            return ConvertToExpectedType(valueType, doubleValue, out value);
        }

        value = null;
        return false;

        static bool ConvertToExpectedType(Type? valueType, object sourceValue, out object? value)
        {
            if (valueType is null)
            {
                value = sourceValue;
                return true;
            }

            try
            {
                value = Convert.ChangeType(sourceValue, valueType);
                return true;
            }
            catch
            {
                value = null;
                return false;
            }
        }
    }

    private static bool TryParseObject(JsonElement propertyElement, VariableType? targetType, out object? value)
    {
        value = propertyElement.ParseRecord(targetType ?? VariableType.RecordType);
        return true;
    }

    private static bool TryParseList(JsonElement propertyElement, VariableType? targetType, out object? value)
    {
        try
        {
            value = ParseTable(propertyElement, targetType ?? VariableType.ListType);
            return true;
        }
        catch
        {
            value = null;
            return false;
        }
    }
}
