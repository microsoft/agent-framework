// Copyright (c) Microsoft. All rights reserved.

using System.Runtime.Serialization;
using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.Purview.Models.Common;

/// <summary>
/// Request for metadata information
/// </summary>
[DataContract]
internal sealed class ActivityMetadata
{
    /// <summary>
    /// Initializes a new instance of the <see cref="ActivityMetadata"/> class.
    /// </summary>
    /// <param name="activity">The activity performed with the content.</param>
    public ActivityMetadata(Activity activity)
    {
        this.Activity = activity;
    }

    /// <summary>
    /// The activity performed with the content.
    /// </summary>
    [DataMember]
    [JsonConverter(typeof(JsonStringEnumConverter<Activity>))]
    [JsonPropertyName("activity")]
    public Activity Activity { get; }
}
