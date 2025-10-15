// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Runtime.Serialization;
using System.Text.Json.Serialization;

namespace Microsoft.Extensions.AI.Agents.Purview.Models.Common;

/// <summary>
/// Access type performed on the resource.
/// </summary>
[Flags]
[DataContract]
[JsonConverter(typeof(JsonStringEnumConverter<ResourceAccessType>))]
internal enum ResourceAccessType : long
{
    [EnumMember(Value = "none")]
    None = 0,

    [EnumMember(Value = "read")]
    Read = 1 << 0,

    [EnumMember(Value = "write")]
    Write = 1 << 1,

    [EnumMember(Value = "create")]
    Create = 1 << 2,

    [EnumMember(Value = "unknownFutureValue")]
    UnknownFutureValue = 1 << 3
}
