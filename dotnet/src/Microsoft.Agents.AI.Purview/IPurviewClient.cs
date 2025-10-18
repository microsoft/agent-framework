// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Purview.Exceptions;
using Microsoft.Agents.AI.Purview.Models.Common;
using Microsoft.Agents.AI.Purview.Models.Requests;
using Microsoft.Agents.AI.Purview.Models.Responses;

namespace Microsoft.Agents.AI.Purview;
internal interface IPurviewClient
{
    /// <summary>
    /// Get user info from auth token.
    /// </summary>
    /// <param name="cancellationToken"></param>
    /// <param name="tenantId"></param>
    /// <returns></returns>
    /// <exception cref="InvalidOperationException"></exception>
    Task<TokenInfo> GetUserInfoFromTokenAsync(CancellationToken cancellationToken, string? tenantId = default);

    /// <summary>
    /// Call ProcessContent API.
    /// </summary>
    /// <param name="request"></param>
    /// <param name="cancellationToken"></param>
    /// <returns></returns>
    /// <exception cref="PurviewException"></exception>
    Task<ProcessContentResponse> ProcessContentAsync(ProcessContentRequest request, CancellationToken cancellationToken);

    /// <summary>
    /// Call user ProtectionScope API.
    /// </summary>
    /// <param name="request"></param>
    /// <param name="cancellationToken"></param>
    /// <returns></returns>
    /// <exception cref="PurviewException"></exception>
    Task<ProtectionScopesResponse> GetProtectionScopesAsync(ProtectionScopesRequest request, CancellationToken cancellationToken);

    /// <summary>
    /// Call contentActivities API.
    /// </summary>
    /// <param name="request"></param>
    /// <param name="cancellationToken"></param>
    /// <returns></returns>
    /// <exception cref="PurviewException"></exception>
    Task<ContentActivitiesResponse> SendContentActivitiesAsync(ContentActivitiesRequest request, CancellationToken cancellationToken);
}
