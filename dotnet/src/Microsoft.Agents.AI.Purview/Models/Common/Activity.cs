// Copyright (c) Microsoft. All rights reserved.

using System.Runtime.Serialization;
using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.Purview.Models.Common;

/// <summary>
/// Activity definitions
/// </summary>
[DataContract]
[JsonConverter(typeof(JsonStringEnumConverter<Activity>))]
internal enum Activity : int
{
    /// <summary>
    /// Unknown activity
    /// </summary>
    [EnumMember(Value = "unknown")]
    Unknown = 0,

    /// <summary>
    /// Upload text
    /// </summary>
    [EnumMember(Value = "uploadText")]
    UploadText = 1,

    /// <summary>
    /// Upload file
    /// </summary>
    [EnumMember(Value = "uploadFile")]
    UploadFile = 2,

    /// <summary>
    /// Download text
    /// </summary>
    [EnumMember(Value = "downloadText")]
    DownloadText = 3,

    /// <summary>
    /// Download file
    /// </summary>
    [EnumMember(Value = "downloadFile")]
    DownloadFile = 4,
}
