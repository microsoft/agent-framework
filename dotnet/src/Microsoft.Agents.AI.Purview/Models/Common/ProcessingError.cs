// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.Purview.Models.Common;

/// <summary>
/// Contains information about a processing error.
/// </summary>
internal sealed class ProcessingError : ClassificationErrorBase
{
    /// <summary>
    /// Details about the error.
    /// </summary>
    [JsonPropertyName("details")]
    public List<ClassificationErrorBase>? Details { get; set; }

    /// <summary>
    /// Gets or sets the error type.
    /// </summary>
    [JsonPropertyName("type")]
    public ContentProcessingErrorType? Type { get; set; }
}
