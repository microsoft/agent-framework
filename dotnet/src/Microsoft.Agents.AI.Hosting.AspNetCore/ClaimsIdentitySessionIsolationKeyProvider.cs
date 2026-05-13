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
    /// configured claim type from the current user's identity, or <see langword="null"/> if the claim
    /// is not present or the HTTP context is unavailable.
    /// </returns>
    /// <remarks>
    /// This method retrieves the claim value from <c>HttpContext.User.Claims</c>. If multiple claims
    /// of the specified type exist, the first match is returned.
    /// </remarks>
    public override ValueTask<string?> GetSessionIsolationKeyAsync(CancellationToken cancellationToken = default)
    {
        Claim? claim = this._httpContextAccessor?
                           .HttpContext?
                           .User?.Claims.FirstOrDefault(c => c.Type == this._claimType);

        return new ValueTask<string?>(claim?.Value);
    }
}
