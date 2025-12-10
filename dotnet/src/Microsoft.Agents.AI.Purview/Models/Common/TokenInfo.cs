// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Purview.Models.Common;

/// <summary>
/// Info pulled from an auth token.
/// </summary>
internal sealed class TokenInfo
{
    /// <summary>
    /// The entra id of the authenticated user. This is null if the auth token is not a user token.
    /// </summary>
    public string? UserId { get; set; }

    /// <summary>
    /// The tenant id of the auth token.
    /// </summary>
    public string? TenantId { get; set; }

    /// <summary>
    /// The client id of the auth token.
    /// </summary>
    public string? ClientId { get; set; }

    /// <summary>
    /// Gets a value indicating whether the token is associated with a user.
    /// </summary>
    public bool IsUserToken => !string.IsNullOrEmpty(this.UserId);
}
