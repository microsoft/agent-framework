// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.Purview.Models.Common;

/// <summary>
/// Represents user scoping information, i.e. which users are affected by the policy.
/// </summary>
internal sealed class PolicyBinding
{
    /// <summary>
    /// Gets or sets the users to be included.
    /// </summary>
    [JsonPropertyName("inclusions")]
    public ICollection<Scope>? Inclusions { get; set; }

    /// <summary>
    /// Gets or sets the users to be excluded.
    /// Exclusions may not be present in the response, thus this property is nullable.
    /// </summary>
    [JsonPropertyName("exclusions")]
    public ICollection<Scope>? Exclusions { get; set; }
}
