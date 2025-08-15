// Copyright (c) Microsoft. All rights reserved.

// WARNING:
// This class has been temporarily copied here from MEAI, to allow prototyping
// functionality that will be moved to MEAI in the future.
// This file is not intended to be modified.

#pragma warning disable CA1031 // Do not catch general exception types
#pragma warning disable S108 // Nested blocks of code should not be left empty
#pragma warning disable S2486 // Generic exceptions should not be ignored

using System.Diagnostics.CodeAnalysis;
using System.Text.Json;

namespace Microsoft.Extensions.AI;

/// <summary>Provides internal helpers for implementing logging.</summary>
[ExcludeFromCodeCoverage]
internal static class LoggingHelpers
{
    /// <summary>Serializes <paramref name="value"/> as JSON for logging purposes.</summary>
    public static string AsJson<T>(T value, JsonSerializerOptions? options)
    {
        if (options?.TryGetTypeInfo(typeof(T), out var typeInfo) is true ||
            AIJsonUtilities.DefaultOptions.TryGetTypeInfo(typeof(T), out typeInfo))
        {
            try
            {
                return JsonSerializer.Serialize(value, typeInfo);
            }
            catch
            {
            }
        }

        // If we're unable to get a type info for the value, or if we fail to serialize,
        // return an empty JSON object. We do not want lack of type info to disrupt application behavior with exceptions.
        return "{}";
    }
}
