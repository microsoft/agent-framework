// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Collections.Immutable;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Nodes;
using Microsoft.Bot.ObjectModel;
using Microsoft.PowerFx.Types;
using BlankType = Microsoft.PowerFx.Types.BlankType;

namespace Microsoft.Agents.Workflows.Declarative.Extensions;

internal static class FormulaValueExtensions
{
    private static readonly JsonSerializerOptions s_options = new() { WriteIndented = true };

    public static DataValue ToDataValue(this FormulaValue value) =>
        value switch
        {
            BooleanValue booleanValue => booleanValue.ToDataValue(),
            DecimalValue decimalValue => decimalValue.ToDataValue(),
            NumberValue numberValue => numberValue.ToDataValue(),
            DateValue dateValue => dateValue.ToDataValue(),
            DateTimeValue datetimeValue => datetimeValue.ToDataValue(),
            TimeValue timeValue => timeValue.ToDataValue(),
            StringValue stringValue => stringValue.ToDataValue(),
            BlankValue blankValue => blankValue.ToDataValue(),
            VoidValue voidValue => voidValue.ToDataValue(),
            TableValue tableValue => tableValue.ToDataValue(),
            RecordValue recordValue => recordValue.ToDataValue(),
            _ => throw new NotSupportedException($"Unsupported FormulaValue type: {value.GetType().Name}"),
        };

    public static DataType GetDataType(this FormulaValue value) =>
        value switch
        {
            null => DataType.Blank,
            BooleanValue => DataType.Boolean,
            DecimalValue => DataType.Number,
            NumberValue => DataType.Float,
            DateValue => DataType.Date,
            DateTimeValue => DataType.DateTime,
            TimeValue => DataType.Time,
            StringValue => DataType.String,
            BlankValue => DataType.Blank,
            RecordValue recordValue => recordValue.Type.ToDataType(),
            TableValue tableValue => tableValue.Type.ToDataType(),
            _ => DataType.Unspecified,
        };

    public static DataType GetDataType(this FormulaType type) =>
        type switch
        {
            null => DataType.Blank,
            BooleanType => DataType.Boolean,
            DecimalType => DataType.Number,
            NumberType => DataType.Float,
            DateType => DataType.Date,
            DateTimeType => DataType.DateTime,
            TimeType => DataType.Time,
            StringType => DataType.String,
            BlankType => DataType.Blank,
            RecordType recordType => recordType.ToDataType(),
            TableType tableType => tableType.ToDataType(),
            _ => DataType.Unspecified,
        };

    public static string Format(this FormulaValue value) =>
        value switch
        {
            BooleanValue booleanValue => $"{booleanValue.Value}",
            DecimalValue decimalValue => $"{decimalValue.Value}",
            NumberValue numberValue => $"{numberValue.Value}",
            DateValue dateValue => $"{dateValue.GetConvertedValue(TimeZoneInfo.Utc)}",
            DateTimeValue datetimeValue => $"{datetimeValue.GetConvertedValue(TimeZoneInfo.Utc)}",
            TimeValue timeValue => $"{timeValue.Value}",
            StringValue stringValue => stringValue.Value,
            GuidValue guidValue => $"{guidValue.Value}",
            BlankValue blankValue => string.Empty,
            VoidValue voidValue => string.Empty,
            TableValue tableValue => tableValue.ToJson().ToJsonString(s_options),
            RecordValue recordValue => recordValue.ToJson().ToJsonString(s_options),
            ErrorValue errorValue => $"Error:{Environment.NewLine}{string.Join(Environment.NewLine, errorValue.Errors.Select(error => $"{error.MessageKey}: {error.Message}"))}",
            _ => $"[{value.GetType().Name}]",
        };

    public static FormulaValue NewBlank(this FormulaType? type) => FormulaValue.NewBlank(type ?? FormulaType.Blank);

    public static BooleanDataValue ToDataValue(this BooleanValue value) => BooleanDataValue.Create(value.Value);
    public static NumberDataValue ToDataValue(this DecimalValue value) => NumberDataValue.Create(value.Value);
    public static FloatDataValue ToDataValue(this NumberValue value) => FloatDataValue.Create(value.Value);
    public static DateTimeDataValue ToDataValue(this DateTimeValue value) => DateTimeDataValue.Create(value.GetConvertedValue(TimeZoneInfo.Utc));
    public static DateDataValue ToDataValue(this DateValue value) => DateDataValue.Create(value.GetConvertedValue(TimeZoneInfo.Utc));
    public static TimeDataValue ToDataValue(this TimeValue value) => TimeDataValue.Create(value.Value);
    public static DataValue ToDataValue(this BlankValue _) => BlankDataValue.Blank();
    public static DataValue ToDataValue(this VoidValue _) => BlankDataValue.Blank();
    public static StringDataValue ToDataValue(this StringValue value) => StringDataValue.Create(value.Value);

    public static TableDataValue ToDataValue(this TableValue value) =>
        TableDataValue.TableFromRecords(value.Rows.Select(row => row.Value.ToDataValue()).ToImmutableArray());

    public static RecordDataValue ToDataValue(this RecordValue value) =>
        RecordDataValue.RecordFromFields(value.OriginalFields.Select(field => field.GetKeyValuePair()).ToImmutableArray());

    public static RecordDataType ToDataType(this RecordType record)
    {
        RecordDataType recordType = new();
        foreach (string fieldName in record.FieldNames)
        {
            recordType.Properties.Add(fieldName, PropertyInfo.Create(record.GetFieldType(fieldName).GetDataType()));
        }
        return recordType;
    }

    public static TableDataType ToDataType(this TableType table)
    {
        TableDataType tableType = new();
        foreach (string fieldName in table.FieldNames)
        {
            tableType.Properties.Add(fieldName, PropertyInfo.Create(table.GetFieldType(fieldName).GetDataType()));
        }
        return tableType;
    }

    private static KeyValuePair<string, DataValue> GetKeyValuePair(this NamedValue value) => new(value.Name, value.Value.ToDataValue());

    public static JsonNode ToJson(this FormulaValue value) =>
        value switch
        {
            BooleanValue booleanValue => JsonValue.Create(booleanValue.Value),
            DecimalValue decimalValue => JsonValue.Create(decimalValue.Value),
            NumberValue numberValue => JsonValue.Create(numberValue.Value),
            DateValue dateValue => JsonValue.Create(dateValue.GetConvertedValue(TimeZoneInfo.Utc)),
            DateTimeValue datetimeValue => JsonValue.Create(datetimeValue.GetConvertedValue(TimeZoneInfo.Utc)),
            TimeValue timeValue => JsonValue.Create($"{timeValue.Value}"),
            StringValue stringValue => JsonValue.Create(stringValue.Value),
            GuidValue guidValue => JsonValue.Create(guidValue.Value),
            RecordValue recordValue => recordValue.ToJson(),
            TableValue tableValue => tableValue.ToJson(),
            BlankValue blankValue => JsonValue.Create(string.Empty),
            //VoidValue voidValue => JsonValue.Create(),
            //ErrorValue errorValue => $"Error:{Environment.NewLine}{string.Join(Environment.NewLine, errorValue.Errors.Select(error => $"{error.MessageKey}: {error.Message}"))}",
            _ => $"[{value.GetType().Name}]",
        };

    public static JsonArray ToJson(this TableValue value)
    {
        return new([.. GetJsonElements()]);

        IEnumerable<JsonNode> GetJsonElements()
        {
            foreach (DValue<RecordValue> row in value.Rows)
            {
                RecordValue recordValue = row.Value;
                yield return recordValue.ToJson();
            }
        }
    }

    public static JsonObject ToJson(this RecordValue value)
    {
        JsonObject jsonObject = [];
        foreach (NamedValue field in value.OriginalFields)
        {
            jsonObject.Add(field.Name, field.Value.ToJson());
        }
        return jsonObject;
    }
}
