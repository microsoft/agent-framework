// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.Purview.Models.Common;

/// <summary>
/// Represents metadata for a protected application that is integrated with Purview.
/// </summary>
internal sealed class ProtectedAppMetadata : IntegratedAppMetadata
{
    /// <summary>
    /// Creates a new instance of the <see cref="ProtectedAppMetadata"/> class.
    /// </summary>
    /// <param name="applicationLocation">The location information of the protected app's data.</param>
    public ProtectedAppMetadata(PolicyLocation applicationLocation)
    {
        this.ApplicationLocation = applicationLocation;
    }

    /// <summary>
    /// The location of the application.
    /// </summary>
    [JsonPropertyName("applicationLocation")]
    public PolicyLocation ApplicationLocation { get; set; }
}
