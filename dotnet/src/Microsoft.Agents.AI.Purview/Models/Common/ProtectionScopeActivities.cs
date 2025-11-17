// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Runtime.Serialization;
using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.Purview.Models.Common;

/// <summary>
/// Activities that can be protected by the Purview Protection Scopes API.
/// </summary>
[Flags]
[DataContract]
[JsonConverter(typeof(JsonStringEnumConverter<ProtectionScopeActivities>))]
internal enum ProtectionScopeActivities
{
    /// <summary>
    /// None.
    /// </summary>
    [EnumMember(Value = "none")]
    None = 0,

    /// <summary>
    /// Upload text activity.
    /// </summary>
    [EnumMember(Value = "uploadText")]
    UploadText = 1,

    /// <summary>
    /// Upload file activity.
    /// </summary>
    [EnumMember(Value = "uploadFile")]
    UploadFile = 2,

    /// <summary>
    /// Download text activity.
    /// </summary>
    [EnumMember(Value = "downloadText")]
    DownloadText = 4,

    /// <summary>
    /// Download file activity.
    /// </summary>
    [EnumMember(Value = "downloadFile")]
    DownloadFile = 8,

    /// <summary>
    /// Unknown future value.
    /// </summary>
    [EnumMember(Value = "unknownFutureValue")]
    UnknownFutureValue = 16
}
