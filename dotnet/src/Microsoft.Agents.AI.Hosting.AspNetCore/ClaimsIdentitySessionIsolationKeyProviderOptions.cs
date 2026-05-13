// Copyright (c) Microsoft. All rights reserved.

using System.Security.Claims;

namespace Microsoft.Agents.AI.Hosting;

/// <summary>
/// Options for configuring <see cref="ClaimsIdentitySessionIsolationKeyProvider"/>.
/// </summary>
public class ClaimsIdentitySessionIsolationKeyProviderOptions
{
    /// <summary>
    /// Gets or sets the claim type to extract from the user's identity for session isolation.
    /// </summary>
    /// <remarks>
    /// <para>
    /// Defaults to <see cref="ClaimsIdentity.DefaultNameClaimType"/>, which typically corresponds to
    /// the user's name or unique identifier claim.
    /// </para>
    /// <para>
    /// Common alternatives include:
    /// <list type="bullet">
    /// <item><description><c>ClaimTypes.NameIdentifier</c> — Stable user identifier</description></item>
    /// <item><description><c>ClaimTypes.Email</c> — Email address</description></item>
    /// <item><description>Custom claim types specific to your authentication provider</description></item>
    /// </list>
    /// </para>
    /// </remarks>
    public string ClaimType { get; set; } = ClaimsIdentity.DefaultNameClaimType;
}
