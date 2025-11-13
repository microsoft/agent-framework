// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Runtime.Serialization;
using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.Purview.Models.Common;

/// <summary>
/// Content to be processed by process content.
/// </summary>
internal sealed class ContentToProcess
{
    /// <summary>
    /// Creates a new instance of ContentToProcess.
    /// </summary>
    /// <param name="contentEntries">The content to send and its associated ids.</param>
    /// <param name="activityMetadata">Metadata about the activity performed with the content.</param>
    /// <param name="deviceMetadata">Metadata about the device that produced the content.</param>
    /// <param name="integratedAppMetadata">Metadata about the application integrating with Purview.</param>
    /// <param name="protectedAppMetadata">Metadata about the application being protected by Purview.</param>
    public ContentToProcess(
        List<ProcessContentMetadataBase> contentEntries,
        ActivityMetadata activityMetadata,
        DeviceMetadata deviceMetadata,
        IntegratedAppMetadata integratedAppMetadata,
        ProtectedAppMetadata protectedAppMetadata)
    {
        this.ContentEntries = contentEntries;
        this.ActivityMetadata = activityMetadata;
        this.DeviceMetadata = deviceMetadata;
        this.IntegratedAppMetadata = integratedAppMetadata;
        this.ProtectedAppMetadata = protectedAppMetadata;
    }

    /// <summary>
    /// Gets or sets the content entries.
    /// List of activities supported by caller. It is used to trim response to activities interesting to the caller.
    /// </summary>
    [JsonPropertyName("contentEntries")]
    public List<ProcessContentMetadataBase> ContentEntries { get; set; }

    /// <summary>
    /// Activity metadata
    /// </summary>
    [DataMember]
    [JsonPropertyName("activityMetadata")]
    public ActivityMetadata ActivityMetadata { get; set; }

    /// <summary>
    /// Device metadata
    /// </summary>
    [DataMember]
    [JsonPropertyName("deviceMetadata")]
    public DeviceMetadata DeviceMetadata { get; set; }

    /// <summary>
    /// Integrated app metadata
    /// </summary>
    [DataMember]
    [JsonPropertyName("integratedAppMetadata")]
    public IntegratedAppMetadata IntegratedAppMetadata { get; set; }

    /// <summary>
    /// Protected app metadata
    /// </summary>
    [DataMember]
    [JsonPropertyName("protectedAppMetadata")]
    public ProtectedAppMetadata ProtectedAppMetadata { get; set; }
}
