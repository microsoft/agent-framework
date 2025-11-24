// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections;
using System.Collections.Generic;
using System.Collections.Immutable;
using System.Dynamic;
using System.Linq;
using Microsoft.Agents.AI.Workflows.Declarative.Kit;
using Microsoft.Agents.AI.Workflows.Declarative.PowerFx;
using Microsoft.Bot.ObjectModel;
using Microsoft.Extensions.AI;
using Microsoft.PowerFx.Types;

namespace Microsoft.Agents.AI.Workflows.Declarative.Extensions;

internal static class DataValueExtensions
{
    public static DataValue ToDataValue(this object? value) =>
        value switch
        {
            null => DataValue.Blank(),
            UnassignedValue => DataValue.Blank(),
            FormulaValue formulaValue => formulaValue.ToDataValue(),
            DataValue dataValue => dataValue,
            bool booleanValue => BooleanDataValue.Create(booleanValue),
            int decimalValue => NumberDataValue.Create(decimalValue),
            long decimalValue => NumberDataValue.Create(decimalValue),
            float decimalValue => FloatDataValue.Create(decimalValue),
            decimal decimalValue => NumberDataValue.Create(decimalValue),
            double numberValue => FloatDataValue.Create(numberValue),
            string stringValue => StringDataValue.Create(stringValue),
            DateTime dateonlyValue when dateonlyValue.TimeOfDay == TimeSpan.Zero => DateDataValue.Create(dateonlyValue),
            DateTime datetimeValue => DateTimeDataValue.Create(datetimeValue),
            TimeSpan timeValue => TimeDataValue.Create(timeValue),
            object when value is IDictionary dictionaryValue => dictionaryValue.ToRecordValue(),
            object when value is IEnumerable tableValue => tableValue.ToTableValue(),
            _ => throw new DeclarativeModelException($"Unsupported variable type: {value.GetType().Name}"),
        };

    public static FormulaValue ToFormula(this DataValue? value) =>
        value switch
        {
            null => FormulaValue.NewBlank(),
            BlankDataValue => FormulaValue.NewBlank(),
            BooleanDataValue boolValue => FormulaValue.New(boolValue.Value),
            NumberDataValue numberValue => FormulaValue.New(numberValue.Value),
            FloatDataValue floatValue => FormulaValue.New(floatValue.Value),
            StringDataValue stringValue => FormulaValue.New(stringValue.Value),
            DateTimeDataValue dateTimeValue => FormulaValue.New(dateTimeValue.Value.DateTime),
            DateDataValue dateValue => FormulaValue.NewDateOnly(dateValue.Value),
            TimeDataValue timeValue => FormulaValue.New(timeValue.Value),
            TableDataValue tableValue =>
                FormulaValue.NewTable(
                    tableValue.Values.FirstOrDefault()?.ParseRecordType() ?? RecordType.Empty(),
                    tableValue.Values.Select(value => value.ToRecordValue())),
            RecordDataValue recordValue => recordValue.ToRecordValue(),
            OptionDataValue optionValue => FormulaValue.New(optionValue.Value.Value),
            _ => FormulaValue.NewError(new Microsoft.PowerFx.ExpressionError { Message = $"Unknown literal type: {value.GetType().Name}" }),
        };

    public static FormulaType ToFormulaType(this DataValue? value) => value?.GetDataType().ToFormulaType() ?? FormulaType.Blank;

    public static FormulaType ToFormulaType(this DataType? type) =>
        type switch
        {
            null => FormulaType.Blank,
            BooleanDataType => FormulaType.Boolean,
            NumberDataType => FormulaType.Decimal,
            FloatDataType => FormulaType.Number,
            StringDataType => FormulaType.String,
            DateTimeDataType => FormulaType.DateTime,
            DateDataType => FormulaType.Date,
            TimeDataType => FormulaType.Time,
            ColorDataType => FormulaType.Color,
            GuidDataType => FormulaType.Guid,
            FileDataType => FormulaType.Blob,
            RecordDataType => RecordType.Empty(),
            TableDataType => TableType.Empty(),
            OptionSetDataType => FormulaType.String,
            AnyType => FormulaType.UntypedObject,
            _ => FormulaType.Unknown,
        };

    public static object? ToObject(this DataValue? value) =>
        value switch
        {
            null => null,
            BlankDataValue => null,
            BooleanDataValue boolValue => boolValue.Value,
            NumberDataValue numberValue => numberValue.Value,
            FloatDataValue floatValue => floatValue.Value,
            StringDataValue stringValue => stringValue.Value,
            DateTimeDataValue dateTimeValue => dateTimeValue.Value.DateTime,
            DateDataValue dateValue => dateValue.Value,
            TimeDataValue timeValue => timeValue.Value,
            TableDataValue tableValue => tableValue.ToObject(),
            RecordDataValue recordValue => recordValue.ToObject(),
            OptionDataValue optionValue => optionValue.Value.Value,
            _ => throw new DeclarativeModelException($"Unsupported {nameof(DataValue)} type: {value.GetType().Name}"),
        };

    public static Type ToClrType(this DataType type) =>
        type switch
        {
            BooleanDataType => typeof(bool),
            NumberDataType => typeof(decimal),
            FloatDataType => typeof(double),
            StringDataType => typeof(string),
            DateTimeDataType => typeof(DateTime),
            DateDataType => typeof(DateTime),
            TimeDataType => typeof(TimeSpan),
            TableDataType tableType => VariableType.ListType,
            RecordDataType recordValue => VariableType.RecordType,
            _ => throw new DeclarativeModelException($"Unsupported {nameof(DataValue)} type: {type.GetType().Name}"),
        };

    public static IList<TElement>? AsList<TElement>(this DataValue? value)
    {
        if (value is null or BlankDataValue)
        {
            return null;
        }

        return value.ToObject().AsList<TElement>();
    }

    public static FormulaValue NewBlank(this DataType? type) => FormulaValue.NewBlank(type?.ToFormulaType() ?? FormulaType.Blank);

    public static RecordValue ToRecordValue(this RecordDataValue recordDataValue) =>
        FormulaValue.NewRecordFromFields(
            recordDataValue.Properties.Select(
                property => new NamedValue(property.Key, property.Value.ToFormula())));

    public static RecordType ToRecordType(this RecordDataType record)
    {
        RecordType recordType = RecordType.Empty();
        foreach (KeyValuePair<string, PropertyInfo> property in record.Properties)
        {
            recordType = recordType.Add(property.Key, property.Value.Type.ToFormulaType());
        }
        return recordType;
    }

    public static RecordDataValue ToRecordValue(this IDictionary value)
    {
        return DataValue.RecordFromFields(GetFields());

        IEnumerable<KeyValuePair<string, DataValue>> GetFields()
        {
            foreach (DictionaryEntry entry in value)
            {
                yield return new KeyValuePair<string, DataValue>((string)entry.Key, entry.Value.ToDataValue());
            }
        }
    }

    public static TableDataValue ToTableValue(this IEnumerable values)
    {
        IEnumerator enumerator = values.GetEnumerator();
        if (!enumerator.MoveNext())
        {
            return DataValue.EmptyTable;
        }

        if (enumerator.Current is IDictionary)
        {
            DataValue.TableFromRecords(GetFields().ToImmutableArray());
        }

        return DataValue.TableFromValues(GetValues().ToImmutableArray());

        IEnumerable<RecordDataValue> GetFields()
        {
            foreach (IDictionary value in values)
            {
                yield return value.ToRecordValue();
            }
        }

        IEnumerable<DataValue> GetValues()
        {
            foreach (object value in values)
            {
                yield return value.ToDataValue();
            }
        }
    }

    private static RecordType ParseRecordType(this RecordDataValue record)
    {
        RecordType recordType = RecordType.Empty();
        foreach (KeyValuePair<string, DataValue> property in record.Properties)
        {
            recordType = recordType.Add(property.Key, property.Value.ToFormulaType());
        }
        return recordType;
    }

    private static object ToObject(this TableDataValue table)
    {
        DataValue? firstElement = table.Values.FirstOrDefault();
        if (firstElement is null)
        {
            return Array.Empty<object>();
        }

        if (firstElement is RecordDataValue record)
        {
            if (record.Properties.Count == 1 && record.Properties.TryGetValue("Value", out DataValue? singleColumn))
            {
                record = singleColumn as RecordDataValue ?? record;
            }

            if (record.Properties.TryGetValue(TypeSchema.Discriminator, out DataValue? value) && value is StringDataValue typeValue)
            {
                if (string.Equals(nameof(ChatMessage), typeValue.Value, StringComparison.Ordinal))
                {
                    return table.ToChatMessages().ToArray();
                }

                if (string.Equals(nameof(ExpandoObject), typeValue.Value, StringComparison.Ordinal))
                {
                    return table.Values.Select(dataValue => dataValue.ToDictionary()).ToArray();
                }
            }
        }

        return table.Values.Select(value => value.ToObject()).ToArray();
    }

    private static object ToObject(this RecordDataValue record)
    {
        if (record.Properties.TryGetValue(TypeSchema.Discriminator, out DataValue? value) && value is StringDataValue typeValue)
        {
            if (string.Equals(nameof(ChatMessage), typeValue.Value, StringComparison.Ordinal))
            {
                return record.ToChatMessage();
            }

            if (string.Equals(nameof(ExpandoObject), typeValue.Value, StringComparison.Ordinal))
            {
                return record.ToDictionary();
            }
        }

        return record.ToDictionary();
    }

    private static Dictionary<string, object?> ToDictionary(this RecordDataValue record)
    {
        Dictionary<string, object?> result = [];
        foreach (KeyValuePair<string, DataValue> property in record.Properties)
        {
            result[property.Key] = property.Value.ToObject();
        }
        return result;
    }
}
