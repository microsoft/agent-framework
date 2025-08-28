// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections;
using System.Collections.Generic;
using System.Collections.Immutable;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Nodes;
using Microsoft.Bot.ObjectModel;
using Microsoft.PowerFx.Types;
using BindingFlags = System.Reflection.BindingFlags;
using BlankType = Microsoft.PowerFx.Types.BlankType;

namespace Microsoft.Agents.Workflows.Declarative.Extensions;

internal static class FormulaValueExtensions
{
    private static readonly JsonSerializerOptions s_options = new() { WriteIndented = true };

    public static FormulaValue NewBlank(this FormulaType? type) => FormulaValue.NewBlank(type ?? FormulaType.Blank);

    public static FormulaValue ToFormulaValue(this object? value)
    {
        Type? type = value?.GetType();
        return value switch
        {
            null => FormulaValue.NewBlank(),
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
            object when typeof(IEnumerable).IsAssignableFrom(type) => ((IEnumerable)value).ToTableValue(type),
            _ => value.ToRecordValue(type),
        };
    }

    public static FormulaType ToFormulaType(this Type? type) =>
        type switch
        {
            null => FormulaType.Blank,
            Type when type == typeof(bool) => FormulaType.Boolean,
            Type when type == typeof(int) => FormulaType.Decimal,
            Type when type == typeof(long) => FormulaType.Decimal,
            Type when type == typeof(float) => FormulaType.Decimal,
            Type when type == typeof(decimal) => FormulaType.Decimal,
            Type when type == typeof(double) => FormulaType.Number,
            Type when type == typeof(string) => FormulaType.String,
            Type when type == typeof(DateTime) => FormulaType.DateTime,
            Type when type == typeof(TimeSpan) => FormulaType.Time,
            Type when typeof(IEnumerable).IsAssignableFrom(type) => type.ToTableType(),
            _ => type.ToRecordType(),
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
            BlankValue blankValue => DataValue.Blank(),
            VoidValue voidValue => DataValue.Blank(),
            RecordValue recordValue => recordValue.ToRecord(),
            TableValue tableValue => tableValue.ToTable(),
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
        TableDataValue.TableFromRecords(value.Rows.Select(row => row.Value.ToRecord()).ToImmutableArray());

    public static RecordDataValue ToRecord(this RecordValue value) =>
        RecordDataValue.RecordFromFields(value.OriginalFields.Select(field => field.GetKeyValuePair()).ToImmutableArray());

    public static RecordDataType ToDataType(this RecordType record)
    {
        RecordDataType recordType = new();
        foreach (string fieldName in record.FieldNames)
        {
            recordType.Properties.Add(fieldName, PropertyInfo.Create(record.GetFieldType(fieldName).ToDataType()));
        }
        return recordType;
    }

    public static TableDataType ToDataType(this TableType table)
    {
        TableDataType tableType = new();
        foreach (string fieldName in table.FieldNames)
        {
            tableType.Properties.Add(fieldName, PropertyInfo.Create(table.GetFieldType(fieldName).ToDataType()));
        }
        return tableType;
    }

    private static RecordType ToRecordType(this Type? type)
    {
        RecordType recordType = RecordType.Empty();

        if (type is not null)
        {
#pragma warning disable IL2070 // might not behave correctly in a trimmed deployment. // %%% REFLECTION
            foreach ((string Name, Type Type) property in
                     type.GetProperties(BindingFlags.Public | BindingFlags.Instance)
                        .Select(property => (property.Name, property.PropertyType)))
#pragma warning restore IL2070 // might not behave correctly in a trimmed deployment.
            {
                recordType.Add(property.Name, property.Type.ToFormulaType());
            }
        }

        return recordType;
    }

    private static RecordValue ToRecordValue(this object value, Type? type)
    {
        type ??= value.GetType();

        if (value is not RecordValue recordValue)
        {
#pragma warning disable IL2070 // might not behave correctly in a trimmed deployment. // %%% REFLECTION
            IEnumerable<NamedValue> propertyValues =
                type.GetProperties(BindingFlags.Public | BindingFlags.Instance)
                    .Select(property => new NamedValue(property.Name, property.GetValue(value).ToFormulaValue()));
#pragma warning restore IL2070 // might not behave correctly in a trimmed deployment.
            recordValue = FormulaValue.NewRecordFromFields(propertyValues);
        }

        return recordValue;
    }

    private static TableType ToTableType(this Type type)
    {
        TableType tableType = TableType.Empty();

        Type? elementType = type.GetElementType() ?? type.GetGenericArguments().FirstOrDefault();
        if (elementType is not null)
        {
#pragma warning disable IL2070 // might not behave correctly in a trimmed deployment. // %%% REFLECTION
            foreach ((string Name, Type Type) property in
                     type.GetProperties(BindingFlags.Public | BindingFlags.Instance)
                        .Select(property => (property.Name, property.PropertyType)))
#pragma warning restore IL2070 // might not behave correctly in a trimmed deployment.
            {
                tableType.Add(property.Name, property.Type.ToFormulaType());
            }
        }

        return tableType;
    }

    private static TableValue ToTableValue(this IEnumerable value, Type type)
    {
        Type? elementType = type.GetElementType() ?? type.GetGenericArguments().FirstOrDefault();

        if (type is null)
        {
            return FormulaValue.NewTable(RecordType.EmptySealed());
        }

        return FormulaValue.NewTable(elementType.ToRecordType(), GetRecords());

        IEnumerable<RecordValue> GetRecords()
        {
            foreach (object elementValue in value)
            {
                yield return elementValue.ToRecordValue(elementType);
            }
        }
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
