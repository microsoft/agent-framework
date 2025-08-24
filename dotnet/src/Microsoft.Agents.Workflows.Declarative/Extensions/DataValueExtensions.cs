// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using Microsoft.Bot.ObjectModel;
using Microsoft.PowerFx.Types;

namespace Microsoft.Agents.Workflows.Declarative.Extensions;

internal static class DataValueExtensions
{
    public static FormulaValue ToFormulaValue(this DataValue? value) =>
        value switch
        {
            null => FormulaValue.NewBlank(),
            BlankDataValue blankValue => BlankValue.NewBlank(),
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

    public static FormulaType ToFormulaType(this DataValue? value) =>
        value switch
        {
            null => FormulaType.Blank,
            BlankDataValue => FormulaType.Blank,
            BooleanDataValue => FormulaType.Boolean,
            NumberDataValue numberValue => FormulaType.Number,
            FloatDataValue floatValue => FormulaType.Decimal,
            StringDataValue stringValue => FormulaType.String,
            DateTimeDataValue dateTimeValue => FormulaType.DateTime,
            DateDataValue dateValue => FormulaType.Date,
            TimeDataValue timeValue => FormulaType.Time,
            TableDataValue tableValue => tableValue.Values.FirstOrDefault()?.ParseRecordType() ?? RecordType.Empty(),
            RecordDataValue recordValue => recordValue.ParseRecordType(),
            OptionDataValue optionValue => FormulaType.String,
            _ => FormulaType.Unknown,
        };

    public static FormulaType ToFormulaType(this DataType? type) =>
        type switch
        {
            null => FormulaType.Blank,
            BooleanDataType => FormulaType.Boolean,
            NumberDataType => FormulaType.Number,
            FloatDataType => FormulaType.Decimal,
            StringDataType => FormulaType.String,
            DateTimeDataType => FormulaType.DateTime,
            DateDataType => FormulaType.Date,
            TimeDataType => FormulaType.Time,
            RecordDataType => RecordType.Empty(),
            TableDataType => TableType.Empty(),
            OptionSetDataType => FormulaType.String,
            _ => FormulaType.Unknown,
        };

    public static FormulaValue NewBlank(this DataType? type) => FormulaValue.NewBlank(type?.ToFormulaType() ?? FormulaType.Blank);

    public static RecordValue ToRecordValue(this RecordDataValue recordDataValue) =>
        FormulaValue.NewRecordFromFields(
            recordDataValue.Properties.Select(
                property => new NamedValue(property.Key, property.Value.ToFormulaValue())));

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
}
