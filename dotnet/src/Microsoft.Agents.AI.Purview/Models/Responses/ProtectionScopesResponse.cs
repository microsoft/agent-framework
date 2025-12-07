// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Text.Json.Serialization;
using Microsoft.Agents.AI.Purview.Models.Common;

namespace Microsoft.Agents.AI.Purview.Models.Responses;

/// <summary>
/// A response object containing protection scopes for a tenant.
/// </summary>
internal sealed class ProtectionScopesResponse
{
    /// <summary>
    /// The identifier used for caching the user protection scopes.
    /// </summary>
    public string? ScopeIdentifier { get; set; }

    /// <summary>
    /// The user protection scopes.
    /// </summary>
    [JsonPropertyName("value")]
    public IReadOnlyCollection<PolicyScopeBase>? Scopes { get; set; }
}
