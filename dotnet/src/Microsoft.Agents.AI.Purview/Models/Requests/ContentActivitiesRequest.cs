// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text.Json.Serialization;
using Microsoft.Agents.AI.Purview.Models.Common;

namespace Microsoft.Agents.AI.Purview.Models.Requests;

/// <summary>
/// A request class used for contentActivity requests.
/// </summary>
internal sealed class ContentActivitiesRequest
{
    /// <summary>
    /// Initializes a new instance of the <see cref="ContentActivitiesRequest"/> class.
    /// </summary>
    /// <param name="userId">The entra id of the user who performed the activity.</param>
    /// <param name="tenantId">The tenant id of the user who performed the activity.</param>
    /// <param name="contentMetadata">The metadata about the content that was sent.</param>
    /// <param name="correlationId">The correlation id of the request.</param>
    /// <param name="scopeIdentifier">The scope identifier of the protection scopes associated with this request.</param>
    public ContentActivitiesRequest(string userId, string tenantId, ContentToProcess contentMetadata, Guid correlationId = default, string? scopeIdentifier = null)
    {
        this.UserId = userId ?? throw new ArgumentNullException(nameof(userId));
        this.TenantId = tenantId ?? throw new ArgumentNullException(nameof(tenantId));
        this.ContentMetadata = contentMetadata ?? throw new ArgumentNullException(nameof(contentMetadata));
        this.CorrelationId = correlationId == default ? Guid.NewGuid() : correlationId;
        this.ScopeIdentifier = scopeIdentifier;
    }

    /// <summary>
    /// Gets or sets the ID of the signal.
    /// </summary>
    [JsonPropertyName("id")]
    public string Id { get; set; } = Guid.NewGuid().ToString();

    /// <summary>
    /// Gets or sets the user ID of the content that is generating the signal.
    /// </summary>
    [JsonPropertyName("userId")]
    public string UserId { get; set; }

    /// <summary>
    /// Gets or sets the scope identifier for the signal.
    /// </summary>
    [JsonPropertyName("scopeIdentifier")]
    public string? ScopeIdentifier { get; set; }

    /// <summary>
    /// Gets or sets the content and associated content metadata for the content used to generate the signal.
    /// </summary>
    [JsonPropertyName("contentMetadata")]
    public ContentToProcess ContentMetadata { get; set; }

    /// <summary>
    /// Gets or sets the correlation ID for the signal.
    /// </summary>
    [JsonIgnore]
    public Guid CorrelationId { get; set; }

    /// <summary>
    /// Gets or sets the tenant id for the signal.
    /// </summary>
    [JsonIgnore]
    public string TenantId { get; set; }
}
