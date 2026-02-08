// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.Purview.Models.Common;

/// <summary>
/// Inner classification error.
/// </summary>
internal sealed class ClassificationInnerError
{
    /// <summary>
    /// Gets or sets date of error.
    /// </summary>
    [JsonPropertyName("date")]
    public DateTime? Date { get; set; }

    /// <summary>
    /// Gets or sets error code.
    /// </summary>
    [JsonPropertyName("code")]
    public string? ErrorCode { get; set; }

    /// <summary>
    /// Gets or sets client request ID.
    /// </summary>
    [JsonPropertyName("clientRequestId")]
    public string? ClientRequestId { get; set; }

    /// <summary>
    /// Gets or sets Activity ID.
    /// </summary>
    [JsonPropertyName("activityId")]
    public string? ActivityId { get; set; }
}
