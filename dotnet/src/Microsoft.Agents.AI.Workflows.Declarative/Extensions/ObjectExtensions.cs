// Copyright (c) Microsoft. All rights reserved.

using System.Collections;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using Microsoft.Agents.AI.Workflows.Declarative.Kit;
using Microsoft.Bot.ObjectModel;
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
            _ => Convert().ToList(),
        };

        IEnumerable<TElement> Convert()
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

    public static object? Convert(this object? sourceValue, VariableType targetType)
    {
        if (sourceValue is string sourceText)
        {
            JsonDocument? document = JsonDocument.Parse(sourceText);
            return document.ParseRecord(targetType);
        }

        return sourceValue;
    }
}
