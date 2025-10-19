// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using Microsoft.Agents.AI.Workflows.Declarative.Kit;

namespace Microsoft.Agents.AI.Workflows.Declarative.Extensions;

internal static class JsonDocumentExtensions
{
    public static List<object?> ParseList(this JsonDocument jsonDocument, VariableType targetType)
    {
        if (!targetType.IsList)
        {
            throw new DeclarativeActionException($"Unable to convert JSON to list with requested type {targetType.Type.Name}.");
        }

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
        if (targetType.Schema is null)
        {
            throw new DeclarativeActionException($"Object schema not defined for. {targetType.Type.Name}.");
        }

        return ParseValues().ToDictionary(kvp => kvp.Key, kvp => kvp.Value);

        IEnumerable<KeyValuePair<string, object?>> ParseValues()
        {
            foreach (KeyValuePair<string, VariableType> property in targetType.Schema)
            {
                JsonElement propertyElement = currentElement.GetProperty(property.Key);
                if (!propertyElement.TryParseValue(property.Value, out object? parsedValue))
                {
                    throw new InvalidOperationException($"Unsupported data type '{property.Value.Type}' for property '{property.Key}'");
                }
                yield return new KeyValuePair<string, object?>(property.Key, parsedValue);
            }
        }
    }

    private static List<object?> ParseTable(this JsonElement currentElement, VariableType targetType)
    {
        return
            currentElement
                .EnumerateArray()
                .Select(element => element.ParseValue(targetType))
                .ToList();
    }

    private static object? ParseValue(this JsonElement propertyElement, VariableType targetType)
    {
        if (!propertyElement.TryParseValue(targetType, out object? value))
        {
            throw new InvalidOperationException($"Unsupported data type '{targetType.Type}'");
        }

        return value;
    }

    private static readonly Dictionary<Type, Func<JsonElement, object?>> s_keyValuePairs = new()
    {
        [typeof(string)] = e => e.GetString(),
        [typeof(int)] = e => e.GetInt32(),
        [typeof(long)] = e => e.GetInt64(),
        [typeof(decimal)] = e => e.GetDecimal(),
        [typeof(double)] = e => e.GetDouble(),
        [typeof(bool)] = e => e.GetBoolean(),
        [typeof(DateTime)] = e => e.GetDateTime(),
        [typeof(TimeSpan)] = e => e.GetDateTimeOffset().TimeOfDay,
    };

    private static bool TryParseValue(this JsonElement propertyElement, VariableType targetType, out object? value)
    {
        Type? elementType =
            targetType.Type.GetElementType() ??
            propertyElement.ValueKind switch
            {
                JsonValueKind.String => typeof(string),
                JsonValueKind.Number => typeof(double),
                JsonValueKind.True or JsonValueKind.False => typeof(bool),
                _ => null,
            };

        if (elementType is null)
        {
            value = null;
            return true;
        }

        if (s_keyValuePairs.TryGetValue(elementType, out Func<JsonElement, object?>? parser))
        {
            value = parser.Invoke(propertyElement);
            return true;
        }

        if (targetType.IsRecord)
        {
            value = propertyElement.ParseRecord(targetType);
            return true;
        }

        if (targetType.IsList)
        {
            value = propertyElement.ParseTable(targetType);
            return true;
        }

        value = null;
        return false;
    }
}
