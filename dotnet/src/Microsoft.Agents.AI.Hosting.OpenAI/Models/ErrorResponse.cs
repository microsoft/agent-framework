// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Models;

/// <summary>
/// Represents an error response from the OpenAI APIs.
/// </summary>
internal sealed class ErrorResponse
{
    /// <summary>
    /// Gets the error details.
    /// </summary>
    [JsonPropertyName("error")]
    public required ErrorDetails Error { get; init; }
}

/// <summary>
/// Represents the details of an error.
/// </summary>
internal sealed class ErrorDetails
{
    /// <summary>
    /// Gets the error message.
    /// </summary>
    [JsonPropertyName("message")]
    public required string Message { get; init; }

    /// <summary>
    /// Gets the error type.
    /// </summary>
    [JsonPropertyName("type")]
    public required string Type { get; init; }

    /// <summary>
    /// Gets the error code.
    /// </summary>
    [JsonPropertyName("code")]
    public string? Code { get; init; }

    /// <summary>
    /// Gets the parameter that caused the error.
    /// </summary>
    [JsonPropertyName("param")]
    public string? Param { get; init; }
}
