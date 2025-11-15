// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.Purview.Models.Common;

/// <summary>
/// Type of error that occurred during content processing.
/// </summary>
[JsonConverter(typeof(JsonStringEnumConverter<ContentProcessingErrorType>))]
internal enum ContentProcessingErrorType
{
    /// <summary>
    /// Error is transient.
    /// </summary>
    Transient,

    /// <summary>
    /// Error is permanent.
    /// </summary>
    Permanent,

    /// <summary>
    /// Unknown future value placeholder.
    /// </summary>
    UnknownFutureValue
}
