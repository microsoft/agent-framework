// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Frozen;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using Microsoft.Agents.AI.Workflows.Declarative.Kit;
using Microsoft.Bot.ObjectModel;
using Microsoft.PowerFx.Types;

namespace Microsoft.Agents.AI.Workflows.Declarative.Extensions;

internal static class JsonDocumentExtensions
{
    public static FrozenDictionary<string, object?> ParseRecord(this JsonDocument jsonDocument, VariableType recordType) => jsonDocument.RootElement.ParseRecord(recordType);

    public static RecordValue ParseRecord(this JsonDocument jsonDocument, RecordDataType recordType) => jsonDocument.RootElement.ParseRecord(recordType);

    private static FrozenDictionary<string, object?> ParseRecord(this JsonElement currentElement, VariableType recordType)
    {
        if (!recordType.IsRecord || recordType.Schema is null)
        {
            throw new DeclarativeActionException($"Unable to parse JSON element as {recordType.Type.Name}.");
        }

        return ParseValues().ToFrozenDictionary(kvp => kvp.Key, kvp => kvp.Value);

        IEnumerable<KeyValuePair<string, object?>> ParseValues()
        {
            foreach (KeyValuePair<string, VariableType?> property in recordType.Schema)
            {
                JsonElement propertyElement = currentElement.GetProperty(property.Key);
                object? parsedValue =
                    property.Value?.Type switch
                    {
                        null => null,
                        _ when property.Value.Type == typeof(string) => propertyElement.GetString(),
                        _ when property.Value.Type == typeof(int) => propertyElement.GetInt32(),
                        _ when property.Value.Type == typeof(long) => propertyElement.GetInt64(),
                        _ when property.Value.Type == typeof(decimal) => propertyElement.GetDecimal(),
                        _ when property.Value.Type == typeof(double) => propertyElement.GetDouble(),
                        _ when property.Value.Type == typeof(bool) => propertyElement.GetBoolean(),
                        _ when property.Value.Type == typeof(DateTime) => propertyElement.GetDateTime(),
                        _ when property.Value.Type == typeof(TimeSpan) => propertyElement.GetDateTimeOffset().TimeOfDay,
                        _ when property.Value.IsRecord => propertyElement.ParseRecord(property.Value),
                        //TableDataType tableType => ParseTable(tableType, propertyElement),
                        _ => throw new InvalidOperationException($"Unsupported data type '{property.Value.Type}' for property '{property.Key}'"),
                    };
                yield return new KeyValuePair<string, object?>(property.Key, parsedValue);
            }

            //static TableValue ParseTable(TableDataType tableType, JsonElement propertyElement)
            //{
            //    RecordDataType recordType = tableType.ToRecord();
            //    return
            //        FormulaValue.NewTable(
            //            recordType.ToRecordType(),
            //            propertyElement.EnumerateArray().Select(tableElement => tableElement.ParseRecord(recordType)));
            //}
        }
    }

    private static RecordValue ParseRecord(this JsonElement currentElement, RecordDataType recordType)
    {
        return FormulaValue.NewRecordFromFields(ParseValues());

        IEnumerable<NamedValue> ParseValues()
        {
            foreach (KeyValuePair<string, PropertyInfo> property in recordType.Properties)
            {
                JsonElement propertyElement = currentElement.GetProperty(property.Key);
                FormulaValue? parsedValue =
                    property.Value.Type switch
                    {
                        StringDataType => FormulaValue.New(propertyElement.GetString()),
                        NumberDataType => FormulaValue.New(propertyElement.GetDecimal()),
                        BooleanDataType => FormulaValue.New(propertyElement.GetBoolean()),
                        DateTimeDataType => FormulaValue.New(propertyElement.GetDateTime()),
                        DateDataType => FormulaValue.New(propertyElement.GetDateTime()),
                        TimeDataType => FormulaValue.New(propertyElement.GetDateTimeOffset().TimeOfDay),
                        RecordDataType recordType => propertyElement.ParseRecord(recordType),
                        TableDataType tableType => ParseTable(tableType, propertyElement),
                        _ => throw new InvalidOperationException($"Unsupported data type '{property.Value.Type}' for property '{property.Key}'"),
                    };
                yield return new NamedValue(property.Key, parsedValue);
            }

            static TableValue ParseTable(TableDataType tableType, JsonElement propertyElement)
            {
                RecordDataType recordType = tableType.ToRecord();
                return
                    FormulaValue.NewTable(
                        recordType.ToRecordType(),
                        propertyElement.EnumerateArray().Select(tableElement => tableElement.ParseRecord(recordType)));
            }
        }
    }
}
