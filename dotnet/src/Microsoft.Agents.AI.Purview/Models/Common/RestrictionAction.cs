// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.Purview.Models.Common;

/// <summary>
/// Restriction actions for devices.
/// </summary>
[JsonConverter(typeof(JsonStringEnumConverter<RestrictionAction>))]
internal enum RestrictionAction
{
    /// <summary>
    /// Warn Action.
    /// </summary>
    Warn,

    /// <summary>
    /// Audit action.
    /// </summary>
    Audit,

    /// <summary>
    /// Block action.
    /// </summary>
    Block,

    /// <summary>
    /// Allow action
    /// </summary>
    Allow
}
