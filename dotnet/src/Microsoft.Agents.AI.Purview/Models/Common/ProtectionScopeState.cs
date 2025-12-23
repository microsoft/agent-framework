// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.Purview.Models.Common;

/// <summary>
/// Indicates status of protection scope changes.
/// </summary>
[JsonConverter(typeof(JsonStringEnumConverter<ProtectionScopeState>))]
internal enum ProtectionScopeState
{
    /// <summary>
    /// Scope state hasn't changed.
    /// </summary>
    NotModified = 0,

    /// <summary>
    /// Scope state has changed.
    /// </summary>
    Modified = 1,

    /// <summary>
    /// Unknown value placeholder for future use.
    /// </summary>
    UnknownFutureValue = 2
}
