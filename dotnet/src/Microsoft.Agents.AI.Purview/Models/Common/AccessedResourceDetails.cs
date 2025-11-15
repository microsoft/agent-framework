// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.Purview.Models.Common;

/// <summary>
/// Information about a resource accessed during a conversation.
/// </summary>
internal sealed class AccessedResourceDetails
{
    /// <summary>
    /// Resource ID.
    /// </summary>
    [JsonPropertyName("identifier")]
    public string? Identifier { get; set; }

    /// <summary>
    /// Resource name.
    /// </summary>
    [JsonPropertyName("name")]
    public string? Name { get; set; }

    /// <summary>
    /// Resource URL.
    /// </summary>
    [JsonPropertyName("url")]
    public string? Url { get; set; }

    /// <summary>
    /// Sensitivity label id detected on the resource.
    /// </summary>
    [JsonPropertyName("labelId")]
    public string? LabelId { get; set; }

    /// <summary>
    /// Access type performed on the resource.
    /// </summary>
    [JsonPropertyName("accessType")]
    public ResourceAccessType AccessType { get; set; }

    /// <summary>
    /// Status of the access operation.
    /// </summary>
    [JsonPropertyName("status")]
    public ResourceAccessStatus Status { get; set; }

    /// <summary>
    /// Indicates if cross prompt injection was detected.
    /// </summary>
    [JsonPropertyName("isCrossPromptInjectionDetected")]
    public bool? IsCrossPromptInjectionDetected { get; set; }
}
