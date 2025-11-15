// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.Purview.Models.Common;

/// <summary>
/// Operating System Specifications
/// </summary>
internal sealed class OperatingSystemSpecifications
{
    /// <summary>
    /// OS platform
    /// </summary>
    [JsonPropertyName("operatingSystemPlatform")]
    public string? OperatingSystemPlatform { get; set; }

    /// <summary>
    /// OS version
    /// </summary>
    [JsonPropertyName("operatingSystemVersion")]
    public string? OperatingSystemVersion { get; set; }
}
