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
        value.TypeId switch
        {
            null => FormulaValue.NewBlank(),
            _ when value.TypeId.IsMatch<UnassignedValue>() => FormulaValue.NewBlank(),
            _ when value.IsType(out string? stringValue) => FormulaValue.New(stringValue),
            _ when value.IsSystemType(out bool? boolValue) => FormulaValue.New(boolValue.Value),
            _ when value.IsSystemType(out int? intValue) => FormulaValue.New(intValue.Value),
            _ when value.IsSystemType(out long? longValue) => FormulaValue.New(longValue.Value),
            _ when value.IsSystemType(out decimal? decimalValue) => FormulaValue.New(decimalValue.Value),
            _ when value.IsSystemType(out float? floatValue) => FormulaValue.New(floatValue.Value),
            _ when value.IsSystemType(out double? doubleValue) => FormulaValue.New(doubleValue.Value),
            _ when value.IsParentType(out Dictionary<string, PortableValue>? recordValue) => recordValue.ToRecord(),
            _ when value.IsParentType(out IDictionary? recordValue) => recordValue.ToRecord(),
            _ when value.IsType(out PortableValue[]? tableValue) => tableValue.ToTable(),
            _ when value.IsType(out ChatMessage? messageValue) => messageValue.ToRecord(),
            _ when value.IsType(out DateTime dateValue) =>
                dateValue.TimeOfDay == TimeSpan.Zero ?
                    FormulaValue.NewDateOnly(dateValue.Date) :
                    FormulaValue.New(dateValue),
            _ when value.IsType(out TimeSpan timeValue) => FormulaValue.New(timeValue),
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
            return FormulaValue.NewTable(ParseRecordType(recordValue), formulaValues.OfType<RecordValue>());
        }

        return
            formulaValues[0] switch
            {
                PrimitiveValue<bool> => NewSingleColumnTable<bool>(),
                PrimitiveValue<string> => NewSingleColumnTable<string>(),
                PrimitiveValue<int> => NewSingleColumnTable<int>(),
                PrimitiveValue<long> => NewSingleColumnTable<long>(),
                PrimitiveValue<float> => NewSingleColumnTable<float>(),
                PrimitiveValue<decimal> => NewSingleColumnTable<decimal>(),
                PrimitiveValue<double> => NewSingleColumnTable<double>(),
                PrimitiveValue<TimeSpan> => NewSingleColumnTable<TimeSpan>(),
                PrimitiveValue<DateTime> => NewSingleColumnTable<DateTime>(),
                _ => throw new DeclarativeModelException($"Unsupported table element type: {formulaValues[0].Type.GetType().Name}"),
            };

        TableValue NewSingleColumnTable<TValue>() =>
            FormulaValue.NewSingleColumnTable(formulaValues.OfType<PrimitiveValue<TValue>>());
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
