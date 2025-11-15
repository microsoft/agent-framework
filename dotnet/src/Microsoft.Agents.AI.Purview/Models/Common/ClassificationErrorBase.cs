// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.Purview.Models.Common;

/// <summary>
/// Base error contract returned when some exception occurs.
/// </summary>
[JsonDerivedType(typeof(ProcessingError))]
internal class ClassificationErrorBase
{
    /// <summary>
    /// Gets or sets the error code.
    /// </summary>
    [JsonPropertyName("code")]
    public string? ErrorCode { get; set; }

    /// <summary>
    /// Gets or sets the message.
    /// </summary>
    [JsonPropertyName("message")]
    public string? Message { get; set; }

    /// <summary>
    /// Gets or sets target of error.
    /// </summary>
    [JsonPropertyName("target")]
    public string? Target { get; set; }

    /// <summary>
    /// Gets or sets an object containing more specific information than the current object about the error.
    /// It can't be a Dictionary because OData will make ClassificationErrorBase open type. It's not expected behavior.
    /// </summary>
    [JsonPropertyName("innerError")]
    public ClassificationInnerError? InnerError { get; set; }
}
