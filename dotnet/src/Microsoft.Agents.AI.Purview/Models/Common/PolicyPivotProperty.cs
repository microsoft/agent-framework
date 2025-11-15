// Copyright (c) Microsoft. All rights reserved.

using System.Runtime.Serialization;
using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.Purview.Models.Common;

/// <summary>
/// Property for policy scoping response to aggregate on
/// </summary>
[DataContract]
[JsonConverter(typeof(JsonStringEnumConverter<PolicyPivotProperty>))]
internal enum PolicyPivotProperty : int
{
    /// <summary>
    /// Unknown activity
    /// </summary>
    [EnumMember]
    [JsonPropertyName("none")]
    None = 0,

    /// <summary>
    /// Pivot on Activity
    /// </summary>
    [EnumMember]
    [JsonPropertyName("activity")]
    Activity = 1,

    /// <summary>
    /// Pivot on location
    /// </summary>
    [EnumMember]
    [JsonPropertyName("location")]
    Location = 2,

    /// <summary>
    /// Pivot on location
    /// </summary>
    [EnumMember]
    [JsonPropertyName("unknownFutureValue")]
    UnknownFutureValue = 3,
}
