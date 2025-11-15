// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.Purview.Models.Common;

/// <summary>
/// Endpoint device Metdata
/// </summary>
internal sealed class DeviceMetadata
{
    /// <summary>
    /// Device type
    /// </summary>
    [JsonPropertyName("deviceType")]
    public string? DeviceType { get; set; }

    /// <summary>
    /// The ip address of the device.
    /// </summary>
    [JsonPropertyName("ipAddress")]
    public string? IpAddress { get; set; }

    /// <summary>
    /// OS specifications
    /// </summary>
    [JsonPropertyName("operatingSystemSpecifications")]
    public OperatingSystemSpecifications? OperatingSystemSpecifications { get; set; }
}
