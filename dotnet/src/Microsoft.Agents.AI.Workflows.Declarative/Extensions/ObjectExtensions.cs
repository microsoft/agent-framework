// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using Microsoft.Agents.AI.Workflows.Declarative.Kit;
using Microsoft.Bot.ObjectModel;
using Microsoft.Extensions.AI;
using Microsoft.PowerFx.Types;

namespace Microsoft.Agents.AI.Workflows.Declarative.Extensions;

internal static class ObjectExtensions
{
    public static IList<TElement>? AsList<TElement>(this object? value)
    {
        return value switch
        {
            null => null,
            UnassignedValue => null,
            BlankValue => null,
            BlankDataValue => null,
            IList<TElement> list => list,
            IEnumerable<TElement> enumerable => enumerable.ToList(),
            TElement element => [element],
            _ => TypedElements().ToList(),
        };

        IEnumerable<TElement> TypedElements()
        {
            if (value is not IEnumerable enumerable)
            {
                throw new DeclarativeActionException($"Value '{value.GetType().Name}' is not '{nameof(IEnumerable)}'.");
            }

            foreach (var item in enumerable)
            {
                if (item is not TElement element)
                {
                    throw new DeclarativeActionException($"Item '{item.GetType().Name}' is not of type '{typeof(TElement).Name}'");
                }

                yield return element;
            }
        }
    }

    public static object AsPortable(this object? value) =>
        value switch
        {
            null => UnassignedValue.Instance,
            string or
            bool or
            int or
            float or
            long or
            decimal or
            double or
            DateTime or
            TimeSpan =>
                value,
            ChatMessage messageValue => messageValue.ToRecord().AsPortable(),
            IDictionary<string, object?> objectValue => objectValue.AsPortable(),
            IDictionary recordValue => recordValue.AsPortable(),
            IEnumerable tableValue => tableValue.AsPortable(),
            _ => throw new DeclarativeModelException($"Unsupported data type: {value.GetType().Name}"),
        };

    public static object AsPortable(this IDictionary<string, object?> value) => value.ToDictionary(kvp => kvp.Key, kvp => new PortableValue(kvp.Value.AsPortable()));

    public static object AsPortable(this IDictionary value)
    {
        return GetEntries().ToDictionary(kvp => kvp.Key, kvp => new PortableValue(kvp.Value.AsPortable()));

        IEnumerable<KeyValuePair<string, object?>> GetEntries()
        {
            foreach (DictionaryEntry entry in value)
            {
                yield return new KeyValuePair<string, object?>((string)entry.Key, entry.Value);
            }
        }
    }

    public static object AsPortable(this IEnumerable value)
    {
        return GetValues().ToArray();

        IEnumerable<PortableValue> GetValues()
        {
            IEnumerator enumerator = value.GetEnumerator();
            while (enumerator.MoveNext())
            {
                yield return new PortableValue(enumerator.Current.AsPortable());
            }
        }
    }

    public static object? ConvertType(this object? sourceValue, VariableType targetType)
    {
        if (!targetType.IsValid())
        {
            throw new DeclarativeActionException($"Unsupported type: '{targetType.Type.Name}'.");
        }

        if (sourceValue != null && targetType.Type.IsAssignableFrom(sourceValue.GetType()))
        {
            return sourceValue;
        }

        return targetType switch
        {
            _ when typeof(string).IsAssignableFrom(targetType.Type) => ConvertToString(),
            _ when typeof(bool).IsAssignableFrom(targetType.Type) => ConvertToBool(),
            _ when targetType.IsRecord => ConvertToRecord(),
            _ when targetType.IsList => ConvertToList(),
            _ when typeof(int).IsAssignableFrom(targetType.Type) => ConvertToInt(),
            _ when typeof(long).IsAssignableFrom(targetType.Type) => ConvertToLong(),
            _ when typeof(decimal).IsAssignableFrom(targetType.Type) => ConvertToDecimal(),
            _ when typeof(double).IsAssignableFrom(targetType.Type) => ConvertToDouble(),
            _ when typeof(DateTime).IsAssignableFrom(targetType.Type) => ConvertToDateTime(),
            _ when typeof(TimeSpan).IsAssignableFrom(targetType.Type) => ConvertToTimeSpan(),
            _ => throw new DeclarativeActionException($"Unsupported type: '{targetType.Type.Name}'."),
        };

        bool? ConvertToBool() =>
            sourceValue switch
            {
                null => null,
                string s => bool.Parse(s),
                int i => i != 0,
                long l => l != 0,
                decimal c => c != 0,
                double d => d != 0,
                DateTime dt => dt > DateTime.MinValue,
                TimeSpan ts => ts > TimeSpan.MinValue,
                _ => sourceValue != null,
            };

        int? ConvertToInt() =>
            sourceValue switch
            {
                null => null,
                string s => int.Parse(s),
                int i => i,
                long l => Convert.ToInt32(l),
                decimal c => Convert.ToInt32(c),
                double d => Convert.ToInt32(d),
                DateTime dt => Convert.ToInt32(dt),
                TimeSpan ts => Convert.ToInt32(ts),
                _ => throw new DeclarativeActionException($"Unsupported target type for '{sourceValue.GetType().Name}': '{targetType.Type.Name}'."),
            };

        long? ConvertToLong() =>
            sourceValue switch
            {
                null => null,
                string s => long.Parse(s),
                int i => i,
                long l => l,
                decimal c => Convert.ToInt64(c),
                double d => Convert.ToInt64(d),
                DateTime dt => Convert.ToInt64(dt),
                TimeSpan ts => Convert.ToInt64(ts),
                _ => throw new DeclarativeActionException($"Unsupported target type for '{sourceValue.GetType().Name}': '{targetType.Type.Name}'."),
            };

        decimal? ConvertToDecimal() =>
            sourceValue switch
            {
                null => null,
                string s => decimal.Parse(s),
                int i => i,
                long l => l,
                decimal c => c,
                double d => Convert.ToDecimal(d),
                DateTime dt => Convert.ToDecimal(dt),
                TimeSpan ts => Convert.ToDecimal(ts),
                _ => throw new DeclarativeActionException($"Unsupported target type for '{sourceValue.GetType().Name}': '{targetType.Type.Name}'."),
            };

        double? ConvertToDouble() =>
            sourceValue switch
            {
                null => null,
                string s => double.Parse(s),
                int i => i,
                long l => l,
                decimal c => Convert.ToDouble(c),
                double d => d,
                DateTime dt => dt.Ticks,
                TimeSpan ts => ts.Ticks,
                _ => throw new DeclarativeActionException($"Unsupported target type for '{sourceValue.GetType().Name}': '{targetType.Type.Name}'."),
            };

        DateTime? ConvertToDateTime() =>
            sourceValue switch
            {
                null => null,
                string s => DateTime.Parse(s),
                int i => new DateTime(i),
                long l => new DateTime(l),
                decimal c => new DateTime(Convert.ToInt64(c)),
                double d => new DateTime(Convert.ToInt64(d)),
                DateTime dt => dt,
                TimeSpan ts => DateTime.Now.Date.AddTicks(ts.Ticks),
                _ => throw new DeclarativeActionException($"Unsupported target type for '{sourceValue.GetType().Name}': '{targetType.Type.Name}'."),
            };

        TimeSpan? ConvertToTimeSpan() =>
            sourceValue switch
            {
                null => null,
                string s => TimeSpan.Parse(s),
                int i => TimeSpan.FromTicks(i),
                long l => TimeSpan.FromTicks(l),
                decimal c => TimeSpan.FromTicks(Convert.ToInt64(c)),
                double d => TimeSpan.FromTicks(Convert.ToInt64(d)),
                DateTime dt => dt.TimeOfDay,
                TimeSpan ts => ts,
                _ => throw new DeclarativeActionException($"Unsupported target type for '{sourceValue.GetType().Name}': '{targetType.Type.Name}'."),
            };

        object? ConvertToList() =>
            sourceValue switch
            {
                null => null,
                //string jsonText => JsonDocument.Parse(jsonText.TrimJsonDelimiter()).ParseRecord(targetType),
                _ => throw new DeclarativeActionException($"Cannot convert '{sourceValue?.GetType().Name}' to 'Record' (expected JSON string)."),
            };

        object? ConvertToRecord() =>
            sourceValue switch
            {
                null => null,
                string jsonText => JsonDocument.Parse(jsonText.TrimJsonDelimiter()).ParseRecord(targetType),
                _ => throw new DeclarativeActionException($"Cannot convert '{sourceValue?.GetType().Name}' to 'Record' (expected JSON string)."),
            };

        string? ConvertToString() =>
            sourceValue switch
            {
                null => null,
                string sourceText => sourceText,
                DateTime dateTime => dateTime.ToString("o"), // ISO 8601
                TimeSpan timeSpan => timeSpan.ToString("c"), // Constant ("c") format
                _ => $"{sourceValue}",
            };
    }
}
