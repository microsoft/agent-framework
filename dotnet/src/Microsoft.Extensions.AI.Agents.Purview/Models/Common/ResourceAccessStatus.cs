// Copyright (c) Microsoft. All rights reserved.

using System.Runtime.Serialization;
using System.Text.Json.Serialization;

namespace Microsoft.Extensions.AI.Agents.Purview.Models.Common;

/// <summary>
/// Status of the access operation.
/// </summary>
[DataContract]
[JsonConverter(typeof(JsonStringEnumConverter<ResourceAccessStatus>))]
internal enum ResourceAccessStatus
{
    [EnumMember(Value = "failure")]
    Failure = 0,

    [EnumMember(Value = "success")]
    Success = 1,

    [EnumMember(Value = "unknownFutureValue")]
    UnknownFutureValue = 2
}
