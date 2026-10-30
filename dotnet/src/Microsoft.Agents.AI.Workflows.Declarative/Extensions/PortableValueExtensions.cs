// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Linq;
using Microsoft.Agents.AI.Workflows.Declarative.Kit;
using Microsoft.Extensions.AI;
using Microsoft.PowerFx.Types;

namespace Microsoft.Agents.AI.Workflows.Declarative.Extensions;

internal static class PortableValueExtensions
{
    public static FormulaValue ToFormula(this PortableValue value) =>
        value.ToPortableObject() switch
        {
            Dictionary<string, PortableValue> recordValue => recordValue.ToRecord(),
            IDictionary recordValue => recordValue.ToRecord(),
            PortableValue[] tableValue => tableValue.ToTable(),
            var nativeValue => nativeValue.ToFormula(),
        };

    public static object ToPortableObject(this PortableValue value) =>
        value.TypeId switch
        {
            null => UnassignedValue.Instance,
            _ when value.TypeId.IsMatch<UnassignedValue>() => UnassignedValue.Instance,
            _ when value.IsType(out string? stringValue) => stringValue,
            _ when value.IsSystemType(out bool? boolValue) => boolValue.Value,
            _ when value.IsSystemType(out int? intValue) => intValue.Value,
            _ when value.IsSystemType(out long? longValue) => longValue.Value,
            _ when value.IsSystemType(out decimal? decimalValue) => decimalValue.Value,
            _ when value.IsSystemType(out float? floatValue) => floatValue.Value,
            _ when value.IsSystemType(out double? doubleValue) => doubleValue.Value,
            _ when value.IsParentType(out Dictionary<string, PortableValue>? recordValue) => recordValue,
            _ when value.IsParentType(out IDictionary? recordValue) => recordValue,
            _ when value.IsType(out PortableValue[]? tableValue) => tableValue,
            _ when value.IsType(out ChatMessage? messageValue) => messageValue,
            _ when value.IsType(out DateTime dateValue) => dateValue,
            _ when value.IsType(out TimeSpan timeValue) => timeValue,
            _ => throw new DeclarativeModelException($"Unsupported portable type: {value.TypeId.TypeName}"),
        };

    private static TableValue ToTable(this PortableValue[] values)
    {
        FormulaValue[] formulaValues = values.Select(value => value.ToFormula()).ToArray();

        if (formulaValues.Length == 0)
        {
            return FormulaValue.NewTable(RecordType.Empty());
        }

        if (formulaValues[0] is RecordValue recordValue)
        {
            return FormulaValue.NewTable(ParseRecordType(recordValue), formulaValues.OfType<RecordValue>().ToArray());
        }

        FormulaType elementType = formulaValues[0] switch
        {
            PrimitiveValue<bool>
                or PrimitiveValue<string>
                or PrimitiveValue<int>
                or PrimitiveValue<long>
                or PrimitiveValue<decimal>
                or PrimitiveValue<float>
                or PrimitiveValue<double>
                or PrimitiveValue<TimeSpan>
                or PrimitiveValue<DateTime> => formulaValues[0].Type,
            _ => throw new DeclarativeModelException($"Unsupported table element type: {formulaValues[0].Type.GetType().Name}"),
        };

        RecordType singleColumnType = RecordType.Empty().Add("Value", elementType);
        RecordValue[] rows =
        [
            .. formulaValues.Select(
                value =>
                    FormulaValue.NewRecordFromFields(
                        singleColumnType,
                        new NamedValue("Value", value))),
        ];
        return FormulaValue.NewTable(singleColumnType, rows);
    }

    public static bool IsSystemType<TValue>(this PortableValue value, [NotNullWhen(true)] out TValue? typedValue) where TValue : struct
    {
        if (value.TypeId.IsMatch<TValue>() || value.TypeId.IsMatch(typeof(TValue).UnderlyingSystemType))
        {
            return value.Is(out typedValue);
        }

        typedValue = default;
        return false;
    }

    public static bool IsType<TValue>(this PortableValue value, [NotNullWhen(true)] out TValue? typedValue)
    {
        if (value.TypeId.IsMatch<TValue>())
        {
            return value.Is(out typedValue);
        }

        typedValue = default;
        return false;
    }

    public static bool IsParentType<TValue>(this PortableValue value, [NotNullWhen(true)] out TValue? typedValue)
    {
        if (value.TypeId.IsMatchPolymorphic(typeof(TValue)))
        {
            return value.Is(out typedValue);
        }

        typedValue = default;
        return false;
    }

    private static RecordType ParseRecordType(this RecordValue record)
    {
        RecordType recordType = RecordType.Empty();
        foreach (NamedValue property in record.Fields)
        {
            recordType = recordType.Add(property.Name, property.Value.Type);
        }
        return recordType;
    }
}
