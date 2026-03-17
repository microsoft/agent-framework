// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.DurableTask.Workflows;

/// <summary>
/// Pairs a JSON-serialized payload with its assembly-qualified type name
/// for type-safe deserialization across activity boundaries.
/// </summary>
internal sealed class TypedPayload
{
    /// <summary>
    /// Gets or sets the assembly-qualified type name of the payload.
    /// </summary>
    public string? TypeName { get; set; }

    /// <summary>
    /// Gets or sets the serialized payload data as JSON.
    /// </summary>
    public string? Data { get; set; }
}
