// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.Purview.Models.Common;

/// <summary>
/// Request execution mode
/// </summary>
[JsonConverter(typeof(JsonStringEnumConverter<ExecutionMode>))]
internal enum ExecutionMode : int
{
    /// <summary>
    /// Evaluate inline.
    /// </summary>
    EvaluateInline = 1,

    /// <summary>
    /// Evaluate offline.
    /// </summary>
    EvaluateOffline = 2,

    /// <summary>
    /// Unknown future value.
    /// </summary>
    UnknownFutureValue = 3
}
