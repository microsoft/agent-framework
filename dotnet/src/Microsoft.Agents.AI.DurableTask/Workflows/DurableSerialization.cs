// Copyright (c) Microsoft. All rights reserved.

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
}
