// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Text.Json;
using Microsoft.Extensions.AI;

namespace A2A;

/// <summary>
/// Extension methods for A2A metadata dictionary.
/// </summary>
internal static class A2AMetadataExtensions
{
    /// <summary>
    /// Converts a dictionary of metadata to an <see cref="AdditionalPropertiesDictionary"/>.
    /// </summary>
    /// <remarks>
    /// This method can be replaced by the one from A2A SDK once it is public.
    /// </remarks>
    /// <param name="metadata">The metadata dictionary to convert.</param>
    /// <returns>The converted <see cref="AdditionalPropertiesDictionary"/>, or null if the input is null or empty.</returns>
    internal static AdditionalPropertiesDictionary? ToAdditionalProperties(this Dictionary<string, JsonElement>? metadata)
    {
        if (metadata is not { Count: > 0 })
        {
            return null;
        }

        var additionalProperties = new AdditionalPropertiesDictionary();
        foreach (var kvp in metadata)
        {
            additionalProperties[kvp.Key] = kvp.Value;
        }
        return additionalProperties;
    }
}
