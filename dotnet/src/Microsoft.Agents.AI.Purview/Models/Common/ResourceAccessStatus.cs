// Copyright (c) Microsoft. All rights reserved.

using System.Runtime.Serialization;
using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.Purview.Models.Common;

/// <summary>
/// Status of the access operation.
/// </summary>
[DataContract]
[JsonConverter(typeof(JsonStringEnumConverter<ResourceAccessStatus>))]
internal enum ResourceAccessStatus
{
    /// <summary>
    /// Represents failed access to the resource.
    /// </summary>
    [EnumMember(Value = "failure")]
    Failure = 0,

    /// <summary>
    /// Represents successful access to the resource.
    /// </summary>
    [EnumMember(Value = "success")]
    Success = 1,

    /// <summary>
    /// Unknown future value.
    /// </summary>
    [EnumMember(Value = "unknownFutureValue")]
    UnknownFutureValue = 2
}
