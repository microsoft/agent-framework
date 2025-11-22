// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Runtime.Serialization;
using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.Purview.Models.Common;

/// <summary>
/// Access type performed on the resource.
/// </summary>
[Flags]
[DataContract]
[JsonConverter(typeof(JsonStringEnumConverter<ResourceAccessType>))]
internal enum ResourceAccessType : long
{
    /// <summary>
    /// No access type.
    /// </summary>
    [EnumMember(Value = "none")]
    None = 0,

    /// <summary>
    /// Read access.
    /// </summary>
    [EnumMember(Value = "read")]
    Read = 1 << 0,

    /// <summary>
    /// Write access.
    /// </summary>
    [EnumMember(Value = "write")]
    Write = 1 << 1,

    /// <summary>
    /// Create access.
    /// </summary>
    [EnumMember(Value = "create")]
    Create = 1 << 2,

    /// <summary>
    /// Unknown future value.
    /// </summary>
    [EnumMember(Value = "unknownFutureValue")]
    UnknownFutureValue = 1 << 3
}
