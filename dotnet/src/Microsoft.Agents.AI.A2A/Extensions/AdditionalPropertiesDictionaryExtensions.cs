// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Text.Json;
using Microsoft.Agents.AI;

namespace Microsoft.Extensions.AI;

/// <summary>
/// Extension methods for AdditionalPropertiesDictionary.
/// </summary>
internal static class AdditionalPropertiesDictionaryExtensions
{
    /// <summary>
    /// Converts an <see cref="AdditionalPropertiesDictionary"/> to a dictionary of <see cref="JsonElement"/> values suitable for A2A metadata.
    /// </summary>
    /// <remarks>
    /// This method can be replaced by the one from A2A SDK once it is available.
    /// </remarks>
    /// <param name="additionalProperties">The additional properties dictionary to convert, or <c>null</c>.</param>
    /// <returns>A dictionary of JSON elements representing the metadata, or <c>null</c> if the input is null or empty.</returns>
    internal static Dictionary<string, JsonElement>? ToA2AMetadata(this AdditionalPropertiesDictionary? additionalProperties)
    {
        if (additionalProperties is not { Count: > 0 })
        {
            return null;
        }

        var metadata = new Dictionary<string, JsonElement>();

        foreach (var kvp in additionalProperties)
        {
            if (kvp.Value is JsonElement)
            {
                metadata[kvp.Key] = (JsonElement)kvp.Value!;
                continue;
            }

            metadata[kvp.Key] = JsonSerializer.SerializeToElement(kvp.Value, A2AJsonUtilities.DefaultOptions.GetTypeInfo(typeof(object)));
        }

        return metadata;
    }
}
