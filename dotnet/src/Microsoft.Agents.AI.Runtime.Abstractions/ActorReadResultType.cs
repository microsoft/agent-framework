// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.Runtime;

/// <summary>
/// Specifies the type of actor read result operation.
/// </summary>
public enum ActorReadResultType
{
    /// <summary>
    /// Represents a list keys operation result.
    /// </summary>
    [JsonStringEnumMemberName("list_keys")]
    ListKeys,

    /// <summary>
    /// Represents a get value operation result.
    /// </summary>
    [JsonStringEnumMemberName("get_value")]
    GetValue
}
