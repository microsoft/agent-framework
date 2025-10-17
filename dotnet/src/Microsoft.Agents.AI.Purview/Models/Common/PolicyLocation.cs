// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.Purview.Models.Common;

/// <summary>
/// Represents a location to which policy is applicable.
/// </summary>
internal sealed class PolicyLocation : GraphDataTypeBase
{
    public PolicyLocation(string dataType, string value) : base(dataType)
    {
        this.Value = value;
    }

    /// <summary>
    /// Gets or sets the applicable value for location.
    /// </summary>
    [JsonPropertyName("value")]
    public string Value { get; set; }
}
