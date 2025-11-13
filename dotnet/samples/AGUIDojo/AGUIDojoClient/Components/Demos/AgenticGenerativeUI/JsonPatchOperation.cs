// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;

namespace AGUIDojoClient.Components.Demos.AgenticGenerativeUI;

/// <summary>
/// Represents a JSON Patch operation (RFC 6902).
/// </summary>
public sealed class JsonPatchOperation
{
    /// <summary>
    /// The operation to perform (e.g., "replace", "add", "remove").
    /// </summary>
    [JsonPropertyName("op")]
    public string Op { get; set; } = string.Empty;

    /// <summary>
    /// The JSON Pointer path to the target location.
    /// </summary>
    [JsonPropertyName("path")]
    public string Path { get; set; } = string.Empty;

    /// <summary>
    /// The value for the operation (used with "replace", "add", "test").
    /// </summary>
    [JsonPropertyName("value")]
    public object? Value { get; set; }
}
