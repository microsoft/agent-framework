// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using Microsoft.Bot.ObjectModel;
using Microsoft.PowerFx.Types;

namespace Microsoft.Agents.Workflows.Declarative.Extensions;

internal static class RecordDataTypeExtensions
{
    public static RecordValue ParseRecord(this RecordDataType recordType, JsonElement currentElement)
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
                        StringDataType => StringValue.New(propertyElement.GetString()),
                        NumberDataType => NumberValue.New(propertyElement.GetDecimal()),
                        BooleanDataType => BooleanValue.New(propertyElement.GetBoolean()),
                        DateTimeDataType => DateTimeValue.New(propertyElement.GetDateTime()),
                        DateDataType => DateValue.New(propertyElement.GetDateTime()),
                        TimeDataType => TimeValue.New(propertyElement.GetDateTimeOffset().TimeOfDay),
                        RecordDataType recordType => recordType.ParseRecord(propertyElement),
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
                        propertyElement.EnumerateArray().Select(tableElement => ParseRecord(recordType, tableElement)));
            }
        }
    }
}
