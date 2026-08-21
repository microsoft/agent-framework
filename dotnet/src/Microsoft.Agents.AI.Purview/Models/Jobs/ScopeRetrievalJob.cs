// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Purview.Models.Common;
using Microsoft.Agents.AI.Purview.Models.Requests;

namespace Microsoft.Agents.AI.Purview.Models.Jobs;

/// <summary>
/// Class representing a job that refreshes the protection scopes cache in the background.
/// </summary>
/// <remarks>
/// Used by the parallel protection scopes retrieval path to warm the cache without blocking the
/// foreground ProcessContent call.
/// </remarks>
internal sealed class ScopeRetrievalJob : BackgroundJobBase
{
    /// <summary>
    /// Initializes a new instance of the <see cref="ScopeRetrievalJob"/> class.
    /// </summary>
    /// <param name="request">The protection scopes request to send to Purview.</param>
    /// <param name="cacheKey">The cache key used to store the response.</param>
    /// <param name="processContentRequest">The original process content request that triggered scope retrieval.</param>
    public ScopeRetrievalJob(ProtectionScopesRequest request, ProtectionScopesCacheKey cacheKey, ProcessContentRequest processContentRequest)
    {
        this.Request = request;
        this.CacheKey = cacheKey;
        this.ProcessContentRequest = processContentRequest;
    }

    /// <summary>
    /// Gets the protection scopes request.
    /// </summary>
    public ProtectionScopesRequest Request { get; }

    /// <summary>
    /// Gets the cache key used to store the response.
    /// </summary>
    public ProtectionScopesCacheKey CacheKey { get; }

    /// <summary>
    /// Gets the original process content request that triggered scope retrieval.
    /// </summary>
    public ProcessContentRequest ProcessContentRequest { get; }
}
