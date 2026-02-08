// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Runtime.Serialization;
using System.Text.Json.Serialization;
using Microsoft.Agents.AI.Purview.Models.Common;

namespace Microsoft.Agents.AI.Purview.Models.Requests;

/// <summary>
/// Request model for user protection scopes requests.
/// </summary>
[DataContract]
internal sealed class ProtectionScopesRequest
{
    /// <summary>
    /// Creates a new instance of ProtectionScopesRequest.
    /// </summary>
    /// <param name="userId">The entra id of the user who made the interaction.</param>
    /// <param name="tenantId">The tenant id of the user who made the interaction.</param>
    public ProtectionScopesRequest(string userId, string tenantId)
    {
        this.UserId = userId;
        this.TenantId = tenantId;
    }

    /// <summary>
    /// Activities to include in the scope
    /// </summary>
    [DataMember]
    [JsonPropertyName("activities")]
    public ProtectionScopeActivities Activities { get; set; }

    /// <summary>
    /// Gets or sets the locations to compute protection scopes for.
    /// </summary>
    [JsonPropertyName("locations")]
    public ICollection<PolicyLocation> Locations { get; set; } = Array.Empty<PolicyLocation>();

    /// <summary>
    /// Response aggregation pivot
    /// </summary>
    [DataMember]
    [JsonPropertyName("pivotOn")]
    public PolicyPivotProperty? PivotOn { get; set; }

    /// <summary>
    /// Device metadata
    /// </summary>
    [DataMember]
    [JsonPropertyName("deviceMetadata")]
    public DeviceMetadata? DeviceMetadata { get; set; }

    /// <summary>
    /// Integrated app metadata
    /// </summary>
    [DataMember]
    [JsonPropertyName("integratedAppMetadata")]
    public IntegratedAppMetadata? IntegratedAppMetadata { get; set; }

    /// <summary>
    /// The correlation id of the request.
    /// </summary>
    [JsonIgnore]
    public Guid CorrelationId { get; set; } = Guid.NewGuid();

    /// <summary>
    /// Scope ID, used to detect stale client scoping information
    /// </summary>
    [DataMember]
    [JsonIgnore]
    public string ScopeIdentifier { get; set; } = string.Empty;

    /// <summary>
    /// The id of the user making the request.
    /// </summary>
    [JsonIgnore]
    public string UserId { get; set; }

    /// <summary>
    /// The tenant id of the user making the request.
    /// </summary>
    [JsonIgnore]
    public string TenantId { get; set; }
}
