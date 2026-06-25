// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using System.Text.Json;

namespace Microsoft.Agents.AI.DurableTask.Workflows;

/// <summary>
/// Shared serialization options for user-defined workflow types that are not known at compile time
/// and therefore cannot use the source-generated <see cref="DurableWorkflowJsonContext"/>.
/// </summary>
internal static class DurableSerialization
{
    /// <summary>
    /// Gets the shared <see cref="JsonSerializerOptions"/> for workflow serialization
    /// with camelCase naming and case-insensitive deserialization.
    /// </summary>
    internal static JsonSerializerOptions Options { get; } = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
        PropertyNameCaseInsensitive = true
    };

    /// <summary>
    /// Deserializes a workflow message's JSON to the source executor's output type so an edge condition or
    /// fan-out selector can evaluate it as a strongly-typed value. Falls back to a generic object when the
    /// type is unknown, and returns <c>null</c> for empty input.
    /// </summary>
    /// <param name="json">The serialized message.</param>
    /// <param name="targetType">The source executor's output type, or <c>null</c> if unknown.</param>
    /// <returns>The deserialized object, or <c>null</c> if the JSON is empty.</returns>
    /// <exception cref="JsonException">Thrown when the JSON is invalid or cannot be deserialized to the target type.</exception>
    [UnconditionalSuppressMessage("AOT", "IL3050", Justification = "Deserializing workflow types registered at startup.")]
    [UnconditionalSuppressMessage("Trimming", "IL2026", Justification = "Deserializing workflow types registered at startup.")]
    internal static object? DeserializeMessage(string json, Type? targetType)
    {
        if (string.IsNullOrEmpty(json))
        {
            return null;
        }

        return targetType is null
            ? JsonSerializer.Deserialize<object>(json, Options)
            : JsonSerializer.Deserialize(json, targetType, Options);
    }
}
