// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;

namespace Microsoft.Extensions.AI.Agents.Purview.Models.Common;

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
