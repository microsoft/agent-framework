// Copyright (c) Microsoft. All rights reserved.

using System.Security.Claims;

namespace AspNetAgentAuthorization.Service;

/// <summary>
/// Provides the authenticated user's identity for the current request.
/// </summary>
public interface IUserContext
{
    /// <summary>Unique identifier for the current user (e.g. the OIDC "sub" claim).</summary>
    string UserId { get; }

    /// <summary>Login name for the current user.</summary>
    string UserName { get; }

    /// <summary>Human-readable display name (e.g. "Test User").</summary>
    string DisplayName { get; }

    /// <summary>OAuth scopes granted in the current access token.</summary>
    IReadOnlySet<string> Scopes { get; }
}

/// <summary>
/// Resolves the current user's identity from Keycloak-specific JWT claims.
/// Keycloak uses <c>sub</c> for the user ID, <c>preferred_username</c>
/// for the login name, <c>given_name</c>/<c>family_name</c> for the
/// display name, and <c>scope</c> (space-delimited) for granted scopes.
/// Registered as a singleton — claims are parsed once per request and
/// cached in <see cref="HttpContext.Items"/>.
/// </summary>
public sealed class KeycloakUserContext : IUserContext
{
    private static readonly object s_cacheKey = new();

    private readonly IHttpContextAccessor _httpContextAccessor;

    public KeycloakUserContext(IHttpContextAccessor httpContextAccessor)
    {
        this._httpContextAccessor = httpContextAccessor;
    }

    public string UserId => this.GetOrCreateCachedInfo().UserId;

    public string UserName => this.GetOrCreateCachedInfo().UserName;

    public string DisplayName => this.GetOrCreateCachedInfo().DisplayName;

    public IReadOnlySet<string> Scopes => this.GetOrCreateCachedInfo().Scopes;

    private CachedUserInfo GetOrCreateCachedInfo()
    {
        HttpContext? httpContext = this._httpContextAccessor.HttpContext;
        if (httpContext is not null && httpContext.Items.TryGetValue(s_cacheKey, out object? cached) && cached is CachedUserInfo info)
        {
            return info;
        }

        info = ParseClaims(httpContext?.User);

        if (httpContext is not null)
        {
            httpContext.Items[s_cacheKey] = info;
        }

        return info;
    }

    private static CachedUserInfo ParseClaims(ClaimsPrincipal? user)
    {
        string userId = user?.FindFirstValue(ClaimTypes.NameIdentifier)
                     ?? user?.FindFirstValue("sub")
                     ?? "anonymous";

        string userName = user?.FindFirstValue("preferred_username")
                       ?? user?.FindFirstValue(ClaimTypes.Name)
                       ?? "unknown";

        string? givenName = user?.FindFirstValue("given_name") ?? user?.FindFirstValue(ClaimTypes.GivenName);
        string? familyName = user?.FindFirstValue("family_name") ?? user?.FindFirstValue(ClaimTypes.Surname);
        string displayName = (givenName, familyName) switch
        {
            (not null, not null) => $"{givenName} {familyName}",
            (not null, null) => givenName,
            (null, not null) => familyName,
            _ => userName,
        };

        string? scopeClaim = user?.FindFirstValue("scope");
        IReadOnlySet<string> scopes = scopeClaim is not null
            ? new HashSet<string>(scopeClaim.Split(' ', StringSplitOptions.RemoveEmptyEntries), StringComparer.OrdinalIgnoreCase)
            : new HashSet<string>(StringComparer.OrdinalIgnoreCase);

        return new CachedUserInfo(userId, userName, displayName, scopes);
    }

    private sealed record CachedUserInfo(string UserId, string UserName, string DisplayName, IReadOnlySet<string> Scopes);
}
