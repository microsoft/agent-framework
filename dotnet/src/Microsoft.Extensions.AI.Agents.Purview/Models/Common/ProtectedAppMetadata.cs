// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;

namespace Microsoft.Extensions.AI.Agents.Purview.Models.Common;
/// <summary>
/// Represents metadata for a protected application that is integrated with Purview.
/// </summary>
internal sealed class ProtectedAppMetadata : IntegratedAppMetadata
{
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
