// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using Microsoft.Bot.ObjectModel;
using Microsoft.PowerFx.Types;

namespace Microsoft.Agents.Workflows.Declarative.Extensions;

internal static class DataValueExtensions
{
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
            TableDataValue tableValue => tableValue.Values.Select(value => value.ToDictionary()).ToArray(),
            RecordDataValue recordValue => recordValue.ToDictionary(),
            OptionDataValue optionValue => optionValue.Value.Value,
            _ => throw new DeclarativeModelException($"Unsupported {nameof(DataValue)} type: {value.GetType().Name}"),
        };

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

    private static RecordType ParseRecordType(this RecordDataValue record)
    {
        RecordType recordType = RecordType.Empty();
        foreach (KeyValuePair<string, DataValue> property in record.Properties)
        {
            recordType = recordType.Add(property.Key, property.Value.ToFormulaType());
        }
        return recordType;
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
