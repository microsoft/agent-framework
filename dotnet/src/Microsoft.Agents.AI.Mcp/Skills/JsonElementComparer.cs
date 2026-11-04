// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Globalization;
using System.Text.Json;

namespace Microsoft.Agents.AI;

/// <summary>
/// Compares JSON values and identifies the first difference.
/// </summary>
/// <remarks>
/// Object key order and number formatting do not affect equality. Key casing, string whitespace,
/// array order, and the difference between a missing field and null are significant.
/// Duplicate object keys are rejected because they make field comparison ambiguous.
/// </remarks>
internal static class JsonElementComparer
{
    /// <summary>
    /// Returns true and a null difference path when the values match; otherwise, returns false and the JSON pointer of the first difference.
    /// An empty pointer identifies a difference at the root value.
    /// </summary>
    internal static bool DeepEquals(JsonElement expected, JsonElement actual, [NotNullWhen(false)] out string? differencePath)
    {
        differencePath = FindDifference(expected, actual, "");
        return differencePath is null;
    }

    private static string? FindDifference(JsonElement expected, JsonElement actual, string path)
    {
        if (expected.ValueKind != actual.ValueKind)
        {
            return path;
        }

        switch (expected.ValueKind)
        {
            case JsonValueKind.Object:
                // Exact keys prevent case variants from hiding missing or additional fields.
                Dictionary<string, JsonElement> expectedProperties = new(StringComparer.Ordinal);
                foreach (JsonProperty property in expected.EnumerateObject())
                {
                    if (!expectedProperties.TryAdd(property.Name, property.Value))
                    {
                        return AppendProperty(path, property.Name);
                    }
                }

                HashSet<string> seen = new(StringComparer.Ordinal);
                foreach (JsonProperty property in actual.EnumerateObject())
                {
                    string propertyPath = AppendProperty(path, property.Name);
                    if (!seen.Add(property.Name) || !expectedProperties.TryGetValue(property.Name, out JsonElement expectedValue))
                    {
                        return propertyPath;
                    }

                    string? mismatch = FindDifference(expectedValue, property.Value, propertyPath);
                    if (mismatch is not null)
                    {
                        return mismatch;
                    }
                }

                foreach (string key in expectedProperties.Keys)
                {
                    if (!seen.Contains(key))
                    {
                        return AppendProperty(path, key);
                    }
                }

                return null;

            case JsonValueKind.Array:
                int commonLength = Math.Min(expected.GetArrayLength(), actual.GetArrayLength());
                var expectedItems = expected.EnumerateArray();
                var actualItems = actual.EnumerateArray();
                for (int i = 0; i < commonLength; i++)
                {
                    expectedItems.MoveNext();
                    actualItems.MoveNext();
                    string? mismatch = FindDifference(expectedItems.Current, actualItems.Current, AppendIndex(path, i));
                    if (mismatch is not null)
                    {
                        return mismatch;
                    }
                }

                return expected.GetArrayLength() == actual.GetArrayLength() ? null : AppendIndex(path, commonLength);

            default:
                // DeepEquals compares numbers without rounding through double or decimal.
                return JsonElement.DeepEquals(expected, actual) ? null : path;
        }
    }

    /// <summary>
    /// Escapes property names using JSON pointer rules so slashes and tildes cannot make the path ambiguous.
    /// </summary>
    private static string AppendProperty(string path, string name) => path + "/" + name.Replace("~", "~0").Replace("/", "~1");

    private static string AppendIndex(string path, int index) => path + "/" + index.ToString(CultureInfo.InvariantCulture);
}
