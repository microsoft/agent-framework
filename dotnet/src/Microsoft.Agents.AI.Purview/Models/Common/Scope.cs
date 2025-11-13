// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.Purview.Models.Common;

/// <summary>
/// Represents tenant/user/group scopes.
/// </summary>
internal sealed class Scope
{
    /// <summary>
    /// The odata type of the scope used to identify what type of scope was returned.
    /// </summary>
    [JsonPropertyName("@odata.type")]
    public string? ODataType { get; set; }

    /// <summary>
    /// Gets or sets the scope identifier.
    /// </summary>
    [JsonPropertyName("identity")]
    public string? Identity { get; set; }
}
