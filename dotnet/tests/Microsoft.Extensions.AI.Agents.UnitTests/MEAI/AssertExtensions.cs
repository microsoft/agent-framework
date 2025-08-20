// Copyright (c) Microsoft. All rights reserved.

// WARNING:
// This class has been temporarily copied here from MEAI, to allow prototyping
// functionality that will be moved to MEAI in the future.
// This file is not intended to be modified.

using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Nodes;
using Xunit.Sdk;

namespace Microsoft.Extensions.AI;

internal static class AssertExtensions
{
    /// <summary>
    /// Asserts that the two function call parameters are equal, up to JSON equivalence.
    /// </summary>
    public static void EqualFunctionCallParameters(
        IDictionary<string, object?>? expected,
        IDictionary<string, object?>? actual,
        JsonSerializerOptions? options = null)
    {
        if (expected is null || actual is null)
        {
            Assert.Equal(expected, actual);
            return;
        }

        foreach (var expectedEntry in expected)
        {
            if (!actual.TryGetValue(expectedEntry.Key, out object? actualValue))
            {
                throw new XunitException($"Expected parameter '{expectedEntry.Key}' not found in actual value.");
            }

            AreJsonEquivalentValues(expectedEntry.Value, actualValue, options, propertyName: expectedEntry.Key);
        }

        if (expected.Count != actual.Count)
        {
            var extraParameters = actual
                .Where(e => !expected.ContainsKey(e.Key))
                .Select(e => $"'{e.Key}'")
                .First();

            throw new XunitException($"Actual value contains additional parameters {string.Join(", ", extraParameters)} not found in expected value.");
        }
    }

    /// <summary>
    /// Asserts that the two function call results are equal, up to JSON equivalence.
    /// </summary>
    public static void EqualFunctionCallResults(object? expected, object? actual, JsonSerializerOptions? options = null)
        => AreJsonEquivalentValues(expected, actual, options);

    /// <summary>
    /// Asserts that the two JSON values are equal.
    /// </summary>
    public static void EqualJsonValues(JsonElement expectedJson, JsonElement actualJson, string? propertyName = null)
    {
        if (!JsonNode.DeepEquals(
            JsonSerializer.SerializeToNode(expectedJson, AIJsonUtilities.DefaultOptions),
            JsonSerializer.SerializeToNode(actualJson, AIJsonUtilities.DefaultOptions)))
        {
            string message = propertyName is null
                ? $"JSON result does not match expected JSON.\r\nExpected: {expectedJson.GetRawText()}\r\nActual:   {actualJson.GetRawText()}"
                : $"Parameter '{propertyName}' does not match expected JSON.\r\nExpected: {expectedJson.GetRawText()}\r\nActual:   {actualJson.GetRawText()}";

            throw new XunitException(message);
        }
    }

    private static void AreJsonEquivalentValues(object? expected, object? actual, JsonSerializerOptions? options, string? propertyName = null)
    {
        options ??= AIJsonUtilities.DefaultOptions;
        JsonElement expectedElement = NormalizeToElement(expected, options);
        JsonElement actualElement = NormalizeToElement(actual, options);
        EqualJsonValues(expectedElement, actualElement, propertyName);

        static JsonElement NormalizeToElement(object? value, JsonSerializerOptions options)
            => value is JsonElement e ? e : JsonSerializer.SerializeToElement(value, options);
    }
}
