// Copyright (c) Microsoft. All rights reserved.

using System.Linq;
using Microsoft.Agents.AI.Purview.Models.Requests;

namespace Microsoft.Agents.AI.Purview.Models.Common;

/// <summary>
/// A cache key for storing protection scope responses.
/// </summary>
internal sealed class ProtectionScopesCacheKey
{
    /// <summary>
    /// Creates a mew instance of <see cref="ProtectionScopesCacheKey"/>.
    /// </summary>
    /// <param name="userId"></param>
    /// <param name="tenantId"></param>
    /// <param name="activities"></param>
    /// <param name="location"></param>
    /// <param name="pivotOn"></param>
    /// <param name="deviceMetadata"></param>
    /// <param name="integratedAppMetadata"></param>
    public ProtectionScopesCacheKey(
        string userId,
        string tenantId,
        ProtectionScopeActivities activities,
        PolicyLocation? location,
        PolicyPivotProperty? pivotOn,
        DeviceMetadata? deviceMetadata,
        IntegratedAppMetadata? integratedAppMetadata)
    {
        this.UserId = userId;
        this.TenantId = tenantId;
        this.Activities = activities;
        this.Location = location;
        this.PivotOn = pivotOn;
        this.DeviceMetadata = deviceMetadata;
        this.IntegratedAppMetadata = integratedAppMetadata;
    }

    /// <summary>
    /// Creates a mew instance of <see cref="ProtectionScopesCacheKey"/>.
    /// </summary>
    /// <param name="request">A protection scopes request.</param>
    public ProtectionScopesCacheKey(
        ProtectionScopesRequest request) : this(
            request.UserId,
            request.TenantId,
            request.Activities,
            request.Locations.FirstOrDefault(),
            request.PivotOn,
            request.DeviceMetadata,
            request.IntegratedAppMetadata)
    {
    }

    /// <summary>
    /// The id of the user making the request.
    /// </summary>
    public string UserId { get; set; }

    /// <summary>
    /// The id of the tenant containing the user making the request.
    /// </summary>
    public string TenantId { get; set; }

    /// <summary>
    /// The activity performed with the content.
    /// </summary>
    public ProtectionScopeActivities Activities { get; set; }

    /// <summary>
    /// The location of the application.
    /// </summary>
    public PolicyLocation? Location { get; set; }

    /// <summary>
    /// The property used to pivot the policy evaluation.
    /// </summary>
    public PolicyPivotProperty? PivotOn { get; set; }

    /// <summary>
    /// Metadata about the device used to access the content.
    /// </summary>
    public DeviceMetadata? DeviceMetadata { get; set; }

    /// <summary>
    /// Metadata about the integrated app used to access the content.
    /// </summary>
    public IntegratedAppMetadata? IntegratedAppMetadata { get; set; }
}
