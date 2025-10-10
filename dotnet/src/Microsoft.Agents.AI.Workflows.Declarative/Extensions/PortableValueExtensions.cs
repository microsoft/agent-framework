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
            _ => throw new DeclarativeModelException($"Unsupported variable type: {value.TypeId.TypeName}"),
        };

    private static TableValue ToTable(this PortableValue[] values) => FormulaValue.NewTable(RecordType.Empty(), values.Select(value => (RecordValue)value.ToFormula())); // %%% HAXX: EMPTY / CAST

    private static bool IsParentType<TValue>(this PortableValue value, [NotNullWhen(true)] out TValue? typedValue)
    {
        if (value.TypeId.IsMatchPolymorphic(typeof(TValue)))
        {
            return value.Is(out typedValue);
        }

        typedValue = default;
        return false;
    }

    private static bool IsSystemType<TValue>(this PortableValue value, [NotNullWhen(true)] out TValue? typedValue) where TValue : struct
    {
        if (value.TypeId.IsMatch<TValue>() || value.TypeId.IsMatch(typeof(TValue).UnderlyingSystemType))
        {
            return value.Is(out typedValue);
        }

        typedValue = default;
        return false;
    }

    private static bool IsType<TValue>(this PortableValue value, [NotNullWhen(true)] out TValue? typedValue)
    {
        if (value.TypeId.IsMatch<TValue>())
        {
            return value.Is(out typedValue);
        }

        typedValue = default;
        return false;
    }
}
