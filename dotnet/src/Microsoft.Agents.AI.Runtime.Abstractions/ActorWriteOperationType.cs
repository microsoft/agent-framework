// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.Runtime;

/// <summary>
/// Specifies the type of actor write operation.
/// </summary>
public enum ActorWriteOperationType
{
    /// <summary>
    /// Represents a set key-value operation.
    /// </summary>
    [JsonStringEnumMemberName("set_value")]
    SetValue,

    /// <summary>
    /// Represents a remove key operation.
    /// </summary>
    [JsonStringEnumMemberName("remove_key")]
    RemoveKey,

    /// <summary>
    /// Represents a send request operation.
    /// </summary>
    [JsonStringEnumMemberName("send_request")]
    SendRequest,

    /// <summary>
    /// Represents an update request operation.
    /// </summary>
    [JsonStringEnumMemberName("update_request")]
    UpdateRequest
}
