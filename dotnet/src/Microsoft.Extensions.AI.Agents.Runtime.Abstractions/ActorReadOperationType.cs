// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;

namespace Microsoft.Extensions.AI.Agents.Runtime;

/// <summary>
/// Specifies the type of actor read operation.
/// </summary>
public enum ActorReadOperationType
{
    /// <summary>
    /// Represents a list keys operation.
    /// </summary>
    [JsonStringEnumMemberName("list_keys")]
    ListKeys,

    /// <summary>
    /// Represents a get value operation.
    /// </summary>
    [JsonStringEnumMemberName("get_value")]
    GetValue
}
