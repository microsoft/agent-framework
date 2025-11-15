// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.Purview.Models.Common;

/// <summary>
/// Represents a scope for policy protection.
/// </summary>
internal sealed class PolicyScopeBase
{
    /// <summary>
    /// Gets or sets the locations to be protected, e.g. domains or URLs.
    /// </summary>
    [JsonPropertyName("locations")]
    public ICollection<PolicyLocation>? Locations { get; set; }

    /// <summary>
    /// Gets or sets the activities to be protected, e.g. uploadText, downloadText.
    /// </summary>
    [JsonPropertyName("activities")]
    public ProtectionScopeActivities Activities { get; set; }

    /// <summary>
    /// Gets or sets how policy should be executed - fire-and-forget or wait for completion.
    /// </summary>
    [JsonPropertyName("executionMode")]
    public ExecutionMode ExecutionMode { get; set; }

    /// <summary>
    /// Gets or sets the enforcement actions to be taken on activities and locations from this scope.
    /// There may be no actions in the response.
    /// </summary>
    [JsonPropertyName("policyActions")]
    public ICollection<DlpActionInfo>? PolicyActions { get; set; }

    /// <summary>
    /// Gets or sets information about policy applicability to a specific user.
    /// </summary>
    [JsonPropertyName("policyScope")]
    public PolicyBinding? PolicyScope { get; set; }
}
