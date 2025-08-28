// Copyright (c) Microsoft. All rights reserved.
using System;
using System.Collections.Generic;

namespace Microsoft.Extensions.AI.Agents;

/// <summary>
/// Utilities for retrieving property values.
/// </summary>
internal static class Utils
{
    public static T? GetValueOrDefault<T>(this IDictionary<string, object> dict, string key)
    {
        if (dict.TryGetValue(key, out var value))
        {
            if (value is null)
            {
                return default;
            }

            // Handle direct type match
            if (value is T directMatch)
            {
                return directMatch;
            }

            // Handle nullable types
            var underlyingType = Nullable.GetUnderlyingType(typeof(T));
            if (underlyingType != null)
            {
                return (T?)Convert.ChangeType(value, underlyingType);
            }

            // Handle non-nullable types
            return (T)Convert.ChangeType(value, typeof(T));
        }
        return default;
    }
}
