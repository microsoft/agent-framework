// Copyright (c) Microsoft. All rights reserved.
using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;

namespace Microsoft.Extensions.AI.Agents;

/// <summary>
/// Utilities for retrieving property values.
/// </summary>
[ExcludeFromCodeCoverage]
internal static class Utils
{
    public static T? GetValueOrDefault<T>(this IDictionary<string, object> dict, string key)
    {
        // check if T is a class and use .ctor recursively
        if (dict.TryGetValue(key, out var value))
        {
            return (T?)Convert.ChangeType(value, typeof(T));
        }
        return default;
    }
}
