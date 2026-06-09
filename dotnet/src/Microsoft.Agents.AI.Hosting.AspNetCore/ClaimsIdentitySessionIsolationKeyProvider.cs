// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Linq;
using System.Security.Claims;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.AspNetCore.Http;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Hosting;

/// <summary>
/// A <see cref="SessionIsolationKeyProvider"/> that extracts the session isolation key from a claim
/// in the current user's identity, as provided by ASP.NET Core's <see cref="IHttpContextAccessor"/>.
/// </summary>
/// <remarks>
/// <para>
/// This provider is suitable for ASP.NET Core web applications where session isolation is based on
/// authenticated user identity. It reads a specified claim type (e.g., name, email, or a custom identifier)
/// from the ambient <see cref="HttpContext"/>.
/// </para>
/// <para>
/// <strong>Security warning:</strong> The configured <see cref="ClaimsIdentitySessionIsolationKeyProviderOptions.ClaimType"/>
/// must uniquely identify the principal within the served population. Display names, usernames, email
/// aliases, and other mutable or non-unique claims are <strong>unsafe</strong> isolation keys unless the
/// host can prove their uniqueness across all callers: two distinct principals that share the same value
/// would receive the same isolation key and could read or overwrite one another's persisted sessions.
/// The default claim type is <see cref="ClaimTypes.NameIdentifier"/>, a stable unique subject identifier
/// that is typically populated from the OpenID Connect <c>sub</c> claim via the default JWT inbound claim
/// mapping (note that this differs from Entra's object identifier <c>oid</c> claim; override
/// <see cref="ClaimsIdentitySessionIsolationKeyProviderOptions.ClaimType"/> if you need <c>oid</c> or your
/// provider maps a different claim).
/// </para>
/// <para>
/// If the <see cref="HttpContext"/> is unavailable, the user is not authenticated, or the specified claim
/// is missing, the provider returns <see langword="null"/>. The consuming <see cref="IsolationKeyScopedAgentSessionStore"/>
/// will then enforce strict or pass-through behavior based on its configuration.
/// </para>
/// <para>
/// This class relies on <see cref="IHttpContextAccessor"/>, which uses <see cref="AsyncLocal{T}"/>
/// to provide access to the current <see cref="HttpContext"/>.
/// </para>
/// </remarks>
public class ClaimsIdentitySessionIsolationKeyProvider : SessionIsolationKeyProvider
{
    private readonly IHttpContextAccessor? _httpContextAccessor;
    private readonly string _claimType;

    /// <summary>
    /// Initializes a new instance of the <see cref="ClaimsIdentitySessionIsolationKeyProvider"/> class.
    /// </summary>
    /// <param name="httpContextAccessor">
    /// The <see cref="IHttpContextAccessor"/> used to retrieve the current HTTP context and user claims.
    /// </param>
    /// <param name="options">The options for configuring the provider. If null, defaults are used.</param>
    /// <exception cref="ArgumentException">
    /// <see cref="ClaimsIdentitySessionIsolationKeyProviderOptions.ClaimType"/> is null, empty, or whitespace.
    /// </exception>
    public ClaimsIdentitySessionIsolationKeyProvider(
        IHttpContextAccessor? httpContextAccessor,
        ClaimsIdentitySessionIsolationKeyProviderOptions? options = null)
    {
        options ??= new ClaimsIdentitySessionIsolationKeyProviderOptions();
        this._httpContextAccessor = httpContextAccessor;
        this._claimType = Throw.IfNullOrWhitespace(options.ClaimType);
    }

    /// <summary>
    /// Extracts the session isolation key from the current user's claims.
    /// </summary>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests.</param>
    /// <returns>
    /// A task that represents the asynchronous operation. The task result contains the value of the
    /// configured claim type from the current user's identity, or <see langword="null"/> if the HTTP
    /// context is unavailable, the user is not authenticated, or the claim is not present.
    /// </returns>
    /// <remarks>
    /// This method only reads claims from an authenticated principal: if the current request has no
    /// authenticated user, it returns <see langword="null"/> rather than trusting claims on an
    /// unauthenticated identity. The claim value is retrieved from <c>HttpContext.User.Claims</c>; if
    /// multiple claims of the specified type exist, the first match is returned.
    /// </remarks>
    public override ValueTask<string?> GetSessionIsolationKeyAsync(CancellationToken cancellationToken = default)
    {
        ClaimsPrincipal? user = this._httpContextAccessor?.HttpContext?.User;
        if (user?.Identity?.IsAuthenticated != true)
        {
            return new ValueTask<string?>((string?)null);
        }

        Claim? claim = user?.Claims.FirstOrDefault(c => c.Type == this._claimType);

        return new ValueTask<string?>(claim?.Value);
    }
}
