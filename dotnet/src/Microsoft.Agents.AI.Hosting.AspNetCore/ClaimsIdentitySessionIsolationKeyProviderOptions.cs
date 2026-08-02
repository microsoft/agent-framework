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
    /// Defaults to <see cref="ClaimTypes.NameIdentifier"/>, which corresponds to a stable, unique
    /// subject identifier for the authenticated principal. For OpenID Connect tokens (including those
    /// issued by Microsoft Entra ID), this is typically populated from the <c>sub</c> claim via the
    /// default JWT inbound claim mapping. Note that <c>sub</c> is distinct from Entra's object
    /// identifier (<c>oid</c>) claim; if you require the <c>oid</c> claim, or your provider does not map
    /// a unique identifier onto <see cref="ClaimTypes.NameIdentifier"/>, override <see cref="ClaimType"/>
    /// with the appropriate claim type.
    /// </para>
    /// <para>
    /// <strong>Security warning:</strong> The configured claim must uniquely identify the principal
    /// within the served population. Display names (<see cref="ClaimsIdentity.DefaultNameClaimType"/>
    /// / <see cref="ClaimTypes.Name"/>), usernames, email aliases, and other mutable or non-unique
    /// claims are <strong>unsafe</strong> isolation keys unless the host can prove their uniqueness
    /// across all callers. Two distinct principals that share the same value for a non-unique claim
    /// would receive the same session-isolation key and could read or overwrite one another's
    /// persisted sessions. Only override this value with a claim that is guaranteed unique and stable.
    /// </para>
    /// <para>
    /// Common alternatives include:
    /// <list type="bullet">
    /// <item><description>A composite of tenant and subject identifiers — required for multi-tenant hosts where the subject is only unique per tenant</description></item>
    /// <item><description>Custom claim types specific to your authentication provider, provided they are unique and stable</description></item>
    /// </list>
    /// </para>
    /// </remarks>
    public string ClaimType { get; set; } = ClaimTypes.NameIdentifier;
}
