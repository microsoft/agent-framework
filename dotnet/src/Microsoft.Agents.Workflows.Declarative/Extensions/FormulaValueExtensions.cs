// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections;
using System.Collections.Generic;
using System.Collections.Immutable;
using System.Dynamic;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Nodes;
using Microsoft.Agents.Workflows.Declarative.PowerFx;
using Microsoft.Bot.ObjectModel;
using Microsoft.PowerFx.Types;
using BlankType = Microsoft.PowerFx.Types.BlankType;

namespace Microsoft.Agents.Workflows.Declarative.Extensions;

internal static class FormulaValueExtensions
{
    private static readonly JsonSerializerOptions s_options = new() { WriteIndented = true };

    public static FormulaValue NewBlank(this FormulaType? type) => FormulaValue.NewBlank(type ?? FormulaType.Blank);

    public static FormulaValue ToFormula(this object? value) =>
        value switch
        {
            null => FormulaValue.NewBlank(),
            UnassignedValue => FormulaValue.NewBlank(),
            FormulaValue formulaValue => formulaValue,
            bool booleanValue => FormulaValue.New(booleanValue),
            int decimalValue => FormulaValue.New(decimalValue),
            long decimalValue => FormulaValue.New(decimalValue),
            float decimalValue => FormulaValue.New(decimalValue),
            decimal decimalValue => FormulaValue.New(decimalValue),
            double numberValue => FormulaValue.New(numberValue),
            string stringValue => FormulaValue.New(stringValue),
            DateTime dateonlyValue when dateonlyValue.TimeOfDay == TimeSpan.Zero => FormulaValue.NewDateOnly(dateonlyValue),
            DateTime datetimeValue => FormulaValue.New(datetimeValue),
            TimeSpan timeValue => FormulaValue.New(timeValue),
            ExpandoObject expandoValue => expandoValue.ToRecord(),
            object when value is IDictionary dictionaryValue => dictionaryValue.ToRecord(),
            object when value is IEnumerable tableValue => tableValue.ToTable(),
            _ => throw new DeclarativeModelException($"Unsupported variable type: {value.GetType().Name}"),
        };

    public static FormulaType GetFormulaType(this object? value) =>
        value switch
        {
            null => FormulaType.Blank,
            bool => FormulaType.Boolean,
            int => FormulaType.Decimal,
            long => FormulaType.Decimal,
            float => FormulaType.Decimal,
            decimal => FormulaType.Decimal,
            double => FormulaType.Number,
            string => FormulaType.String,
            DateTime => FormulaType.DateTime,
            TimeSpan => FormulaType.Time,
            object when value is IEnumerable tableValue => tableValue.ToTableType(),
            ExpandoObject expandoValue => expandoValue.ToRecordType(),
            _ => FormulaType.Unknown,
        };

    public static DataValue ToDataValue(this FormulaValue value) =>
        value switch
        {
            BooleanValue booleanValue => BooleanDataValue.Create(booleanValue.Value),
            DecimalValue decimalValue => NumberDataValue.Create(decimalValue.Value),
            NumberValue numberValue => FloatDataValue.Create(numberValue.Value),
            DateValue dateValue => DateDataValue.Create(dateValue.GetConvertedValue(TimeZoneInfo.Utc)),
            DateTimeValue datetimeValue => DateTimeDataValue.Create(datetimeValue.GetConvertedValue(TimeZoneInfo.Utc)),
            TimeValue timeValue => TimeDataValue.Create(timeValue.Value),
            StringValue stringValue => StringDataValue.Create(stringValue.Value),
            BlankValue => DataValue.Blank(),
            VoidValue => DataValue.Blank(),
            RecordValue recordValue => recordValue.ToRecord(),
            TableValue tableValue => tableValue.ToTable(),
            _ => throw new DeclarativeModelException($"Unsupported variable type: {value.GetType().Name}"),
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
            ColorValue => DataType.Color,
            GuidValue => DataType.Guid,
            BlobValue => DataType.File,
            RecordValue recordValue => recordValue.Type.ToDataType(),
            TableValue tableValue => tableValue.Type.ToDataType(),
            UntypedObjectValue => DataType.Any,
            _ => DataType.Unspecified,
        };

    public static DataType ToDataType(this FormulaType type) =>
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
            ColorType => DataType.Color,
            GuidType => DataType.Guid,
            BlobType => DataType.File,
            RecordType recordType => recordType.ToDataType(),
            TableType tableType => tableType.ToDataType(),
            UntypedObjectType => DataType.Any,
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
            BlankValue blankValue => string.Empty,
            VoidValue voidValue => string.Empty,
            ColorValue colorValue => colorValue.Value.ToString(),
            GuidValue guidValue => guidValue.Value.ToString("N"),
            TableValue tableValue => tableValue.ToJson().ToJsonString(s_options),
            RecordValue recordValue => recordValue.ToJson().ToJsonString(s_options),
            ErrorValue errorValue => $"Error:{Environment.NewLine}{string.Join(Environment.NewLine, errorValue.Errors.Select(error => $"{error.MessageKey}: {error.Message}"))}",
            _ => $"[{value.GetType().Name}]",
        };

    public static TableDataValue ToTable(this TableValue value) =>
        DataValue.TableFromRecords(value.Rows.Select(row => row.Value.ToRecord()).ToImmutableArray());

    public static RecordDataValue ToRecord(this RecordValue value) =>
        DataValue.RecordFromFields(value.OriginalFields.Select(field => field.GetKeyValuePair()));

    public static RecordValue ToRecord(this IDictionary value)
    {
        return FormulaValue.NewRecordFromFields(GetFields());

        IEnumerable<NamedValue> GetFields()
        {
            foreach (string key in value.Keys)
            {
                yield return new NamedValue(key, value[key].ToFormula());
            }
        }
    }

    private static RecordDataType ToDataType(this RecordType record)
    {
        RecordDataType recordType = new();
        foreach (string fieldName in record.FieldNames)
        {
            recordType.Properties.Add(fieldName, PropertyInfo.Create(record.GetFieldType(fieldName).ToDataType()));
        }
        return recordType;
    }

    private static TableDataType ToDataType(this TableType table)
    {
        TableDataType tableType = new();
        foreach (string fieldName in table.FieldNames)
        {
            tableType.Properties.Add(fieldName, PropertyInfo.Create(table.GetFieldType(fieldName).ToDataType()));
        }
        return tableType;
    }

    private static RecordType ToRecordType(this ExpandoObject value)
    {
        RecordType recordType = RecordType.Empty();
        foreach (KeyValuePair<string, object?> property in value)
        {
            recordType.Add(property.Key, property.Value.GetFormulaType());
        }
        return recordType;
    }

    private static RecordValue ToRecord(this ExpandoObject value) =>
        FormulaValue.NewRecordFromFields(
            value.Select(
                property => new NamedValue(property.Key, property.Value.ToFormula())));

    private static TableType ToTableType(this IEnumerable value)
    {
        foreach (object? element in value)
        {
            if (element is not ExpandoObject expandoElement)
            {
                throw new DeclarativeModelException($"Invalid table element: {element.GetType().Name}");
            }

            return expandoElement.ToRecordType().ToTable(); // Return first element
        }

        return TableType.Empty();
    }

    private static TableValue ToTable(this IEnumerable value) =>
        FormulaValue.NewTable(
            value.ToTableType().ToRecord(),
            [.. value.OfType<ExpandoObject>().Select(element => element.ToRecord())]);

    private static KeyValuePair<string, DataValue> GetKeyValuePair(this NamedValue value) => new(value.Name, value.Value.ToDataValue());

    private static JsonNode ToJson(this FormulaValue value) =>
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
            BlankValue => JsonValue.Create(string.Empty),
            _ => $"[{value.GetType().Name}]",
        };

    private static JsonArray ToJson(this TableValue value)
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

    private static JsonObject ToJson(this RecordValue value)
    {
        JsonObject jsonObject = [];
        foreach (NamedValue field in value.OriginalFields)
        {
            jsonObject.Add(field.Name, field.Value.ToJson());
        }
        return jsonObject;
    }
}
