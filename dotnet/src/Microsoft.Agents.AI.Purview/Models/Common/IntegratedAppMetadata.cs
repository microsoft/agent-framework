// Copyright (c) Microsoft. All rights reserved.

using System.Runtime.Serialization;
using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.Purview.Models.Common;

/// <summary>
/// Request for metadata information
/// </summary>
[JsonDerivedType(typeof(ProtectedAppMetadata))]
internal class IntegratedAppMetadata
{
    /// <summary>
    /// Application name
    /// </summary>
    [DataMember]
    [JsonPropertyName("name")]
    public string? Name { get; set; }

    /// <summary>
    /// Application version
    /// </summary>
    [DataMember]
    [JsonPropertyName("version")]
    public string? Version { get; set; }
}
