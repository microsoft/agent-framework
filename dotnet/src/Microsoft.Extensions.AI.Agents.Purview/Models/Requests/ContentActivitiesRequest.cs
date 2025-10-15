// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text.Json.Serialization;
using Microsoft.Extensions.AI.Agents.Purview.Models.Common;

namespace Microsoft.Extensions.AI.Agents.Purview.Models.Requests;

/// <summary>
/// A request class used for contentActivity requests.
/// </summary>
internal sealed class ContentActivitiesRequest
{
    /// <summary>
    /// Initializes a new instance of the <see cref="ContentActivitiesRequest"/> class.
    /// </summary>
    /// <param name="userId"></param>
    /// <param name="tenantId"></param>
    /// <param name="contentMetadata"></param>
    /// <param name="correlationId"></param>
    /// <param name="scopeIdentifier"></param>
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
    public string? UserId { get; set; }

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
