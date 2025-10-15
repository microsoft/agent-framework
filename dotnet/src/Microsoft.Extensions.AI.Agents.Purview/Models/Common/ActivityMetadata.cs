// Copyright (c) Microsoft. All rights reserved.

using System.Runtime.Serialization;
using System.Text.Json.Serialization;

namespace Microsoft.Extensions.AI.Agents.Purview.Models.Common;

/// <summary>
/// Request for meta data information
/// </summary>
[DataContract]
internal sealed class ActivityMetadata
{
    /// <summary>
    /// Initializes a new instance of the <see cref="ActivityMetadata"/> class.
    /// </summary>
    /// <param name="activity"></param>
    public ActivityMetadata(Activity activity)
    {
        this.Activity = activity;
    }

    /// <summary>
    /// Content name
    /// </summary>
    [DataMember]
    [JsonConverter(typeof(JsonStringEnumConverter<Activity>))]
    [JsonPropertyName("activity")]
    public Activity Activity { get; }
}
