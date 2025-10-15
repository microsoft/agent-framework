// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;

namespace Microsoft.Extensions.AI.Agents.Purview.Models.Common;

/// <summary>
/// Indicates status of protection scope changes.
/// </summary>
[JsonConverter(typeof(JsonStringEnumConverter<ProtectionScopeState>))]
internal enum ProtectionScopeState
{
    /// <summary>
    /// Scope state hasn't changed.
    /// </summary>
    NotModified,

    /// <summary>
    /// Scope state has changed.
    /// </summary>
    Modified,

    /// <summary>
    /// Unknown value placeholder for future use.
    /// </summary>
    UnknownFutureValue = 2
}
