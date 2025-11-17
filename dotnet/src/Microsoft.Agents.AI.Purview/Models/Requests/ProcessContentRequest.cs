// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text.Json.Serialization;
using Microsoft.Agents.AI.Purview.Models.Common;

namespace Microsoft.Agents.AI.Purview.Models.Requests;

/// <summary>
/// Request for ProcessContent API
/// </summary>
internal sealed class ProcessContentRequest
{
    /// <summary>
    /// Creates a new instance of ProcessContentRequest.
    /// </summary>
    /// <param name="contentToProcess">The content and its metadata that will be processed.</param>
    /// <param name="userId">The entra user id of the user making the request.</param>
    /// <param name="tenantId">The tenant id of the user making the request.</param>
    public ProcessContentRequest(ContentToProcess contentToProcess, string userId, string tenantId)
    {
        this.ContentToProcess = contentToProcess;
        this.UserId = userId;
        this.TenantId = tenantId;
    }

    /// <summary>
    /// The content to process.
    /// </summary>
    [JsonPropertyName("contentToProcess")]
    public ContentToProcess ContentToProcess { get; set; }

    /// <summary>
    /// The user id of the user making the request.
    /// </summary>
    [JsonIgnore]
    public string UserId { get; set; }

    /// <summary>
    /// The correlation id of the request.
    /// </summary>
    [JsonIgnore]
    public Guid CorrelationId { get; set; } = Guid.NewGuid();

    /// <summary>
    /// The tenant id of the user making the request.
    /// </summary>
    [JsonIgnore]
    public string TenantId { get; set; }

    /// <summary>
    /// The identifier of the cached protection scopes.
    /// </summary>
    [JsonIgnore]
    internal string? ScopeIdentifier { get; set; }
}
