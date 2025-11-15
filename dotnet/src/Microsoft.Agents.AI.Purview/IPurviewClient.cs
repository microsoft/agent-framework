// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Purview.Models.Common;
using Microsoft.Agents.AI.Purview.Models.Requests;
using Microsoft.Agents.AI.Purview.Models.Responses;

namespace Microsoft.Agents.AI.Purview;

/// <summary>
/// Defines methods for interacting with the Purview service, including content processing,
/// protection scope management, and activity tracking.
/// </summary>
/// <remarks>This interface provides methods to interact with various Purview APIs.  It includes processing content, managing protection
/// scopes, and sending content activity data.  Implementations of this interface are expected to handle communication
/// with the Purview service  and manage any necessary authentication or error handling.</remarks>
internal interface IPurviewClient
{
    /// <summary>
    /// Get user info from auth token.
    /// </summary>
    /// <param name="cancellationToken">The cancellation token used to cancel async processing.</param>
    /// <param name="tenantId">The default tenant id used to retrieve the token and its info.</param>
    /// <returns>The token info from the token.</returns>
    /// <exception cref="InvalidOperationException">Throw if the token was invalid or could not be retrieved.</exception>
    Task<TokenInfo> GetUserInfoFromTokenAsync(CancellationToken cancellationToken, string? tenantId = default);

    /// <summary>
    /// Call ProcessContent API.
    /// </summary>
    /// <param name="request">The request containing the content to process.</param>
    /// <param name="cancellationToken">The cancellation token used to cancel async processing.</param>
    /// <returns>The response from the Purview API.</returns>
    /// <exception cref="PurviewException">Thrown for validation, auth, and network errors.</exception>
    Task<ProcessContentResponse> ProcessContentAsync(ProcessContentRequest request, CancellationToken cancellationToken);

    /// <summary>
    /// Call user ProtectionScope API.
    /// </summary>
    /// <param name="request">The request containing the protection scopes metadata.</param>
    /// <param name="cancellationToken">The cancellation token used to cancel async processing.</param>
    /// <returns>The protection scopes that apply to the data sent in the request.</returns>
    /// <exception cref="PurviewException">Thrown for validation, auth, and network errors.</exception>
    Task<ProtectionScopesResponse> GetProtectionScopesAsync(ProtectionScopesRequest request, CancellationToken cancellationToken);

    /// <summary>
    /// Call contentActivities API.
    /// </summary>
    /// <param name="request">The request containing the content metadata. Used to generate interaction records.</param>
    /// <param name="cancellationToken">The cancellation token used to cancel async processing.</param>
    /// <returns>The response from the Purview API.</returns>
    /// <exception cref="PurviewException">Thrown for validation, auth, and network errors.</exception>
    Task<ContentActivitiesResponse> SendContentActivitiesAsync(ContentActivitiesRequest request, CancellationToken cancellationToken);
}
