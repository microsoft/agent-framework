// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Purview.Models.Common;

/// <summary>
/// A cache key for tenant-level payment required state.
/// </summary>
internal sealed class PaymentRequiredCacheKey
{
    /// <summary>
    /// Creates a new instance of <see cref="PaymentRequiredCacheKey"/>.
    /// </summary>
    /// <param name="tenantId">The id of the tenant.</param>
    public PaymentRequiredCacheKey(string tenantId)
    {
        this.TenantId = tenantId;
    }

    /// <summary>
    /// The id of the tenant.
    /// </summary>
    public string TenantId { get; set; }
}
