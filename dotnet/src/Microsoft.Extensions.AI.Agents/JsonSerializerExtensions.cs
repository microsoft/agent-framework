// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using System.Text.Json.Serialization;
using System.Text.Json.Serialization.Metadata;

namespace Microsoft.Extensions.AI.Agents;

/// <summary>
/// Provides extension methods for JSON serialization with source generation support.
/// </summary>
internal static class JsonSerializerExtensions
{
    /// <summary>
    /// Gets the JsonTypeInfo for a type, preferring the one from options if available,
    /// otherwise falling back to the source-generated context.
    /// </summary>
    /// <typeparam name="T">The type to get JsonTypeInfo for.</typeparam>
    /// <param name="options">The JsonSerializerOptions to check first.</param>
    /// <param name="fallbackContext">The fallback JsonSerializerContext to use if not found in options.</param>
    /// <returns>The JsonTypeInfo for the requested type.</returns>
    public static JsonTypeInfo<T> GetTypeInfo<T>(this JsonSerializerOptions options, JsonSerializerContext fallbackContext)
    {
        // Try to get from the options first (if a context is configured)
        if (options.TypeInfoResolver?.GetTypeInfo(typeof(T), options) is JsonTypeInfo<T> typeInfo)
        {
            return typeInfo;
        }

        // Fall back to the provided source-generated context
        return (JsonTypeInfo<T>)fallbackContext.GetTypeInfo(typeof(T))!;
    }
}
