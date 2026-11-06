// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;

namespace Microsoft.Agents.AI.Foundry.Hosting;

/// <summary>
/// Validates OAuth consent links before they are surfaced as <c>oauth_consent_request</c> output items.
/// </summary>
/// <remarks>
/// <para>
/// Every link must be an absolute HTTPS URL with a valid host and no user information, whitespace,
/// control characters, or backslashes. This check always runs.
/// </para>
/// <para>
/// When the host configures <see cref="FoundryToolboxOptions.AllowedOAuthConsentOrigins"/>, the link's
/// normalized origin (scheme, host, and port) must also match one of the configured origins. A
/// <see langword="null"/> configuration skips only this origin check; an empty configuration rejects
/// every link.
/// </para>
/// </remarks>
internal sealed class OAuthConsentLinkPolicy
{
    private readonly HashSet<string>? _allowedOrigins;

    /// <summary>
    /// Gets the policy that validates absolute HTTPS consent links without restricting their origin.
    /// </summary>
    internal static OAuthConsentLinkPolicy UnrestrictedOrigin { get; } = new(null);

    /// <summary>
    /// Initializes a new instance of the <see cref="OAuthConsentLinkPolicy"/> class.
    /// </summary>
    /// <param name="allowedOrigins">
    /// The exact HTTPS origins allowed for consent links, or <see langword="null"/> to skip the origin restriction.
    /// </param>
    /// <exception cref="ArgumentException">An entry is not an absolute HTTPS origin.</exception>
    internal OAuthConsentLinkPolicy(IEnumerable<Uri>? allowedOrigins)
    {
        if (allowedOrigins is null)
        {
            return;
        }

        this._allowedOrigins = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (Uri? origin in allowedOrigins)
        {
            if (!TryNormalizeOrigin(origin, requireOriginOnly: true, out string? normalizedOrigin))
            {
                throw new ArgumentException(
                    $"OAuth consent allowlist entry '{origin?.OriginalString}' must be an absolute HTTPS origin without a path, query, or fragment.",
                    nameof(allowedOrigins));
            }

            this._allowedOrigins.Add(normalizedOrigin);
        }
    }

    /// <summary>
    /// Returns whether <paramref name="consentUrl"/> may be surfaced as an OAuth consent link.
    /// </summary>
    internal bool IsAllowed(string? consentUrl)
    {
        // URL validation is enforced before the optional origin gate so that an omitted allowlist still
        // rejects non-HTTPS schemes such as javascript: or http:.
        if (!TryNormalizeOrigin(consentUrl, requireOriginOnly: false, out string? normalizedOrigin))
        {
            return false;
        }

        return this._allowedOrigins?.Contains(normalizedOrigin) ?? true;
    }

    private static bool TryNormalizeOrigin(
        string? value,
        bool requireOriginOnly,
        [NotNullWhen(true)] out string? normalizedOrigin)
    {
        normalizedOrigin = null;

        if (string.IsNullOrWhiteSpace(value))
        {
            return false;
        }

        // Backslashes are rejected because Uri normalizes them to forward slashes, which would let
        // the validated URL differ from the raw string that clients receive and parse.
        if (ContainsDisallowedCharacters(value))
        {
            return false;
        }

        if (!Uri.TryCreate(value, UriKind.Absolute, out Uri? uri))
        {
            return false;
        }

        return TryNormalizeOrigin(uri, requireOriginOnly, out normalizedOrigin);
    }

    private static bool TryNormalizeOrigin(
        Uri? uri,
        bool requireOriginOnly,
        [NotNullWhen(true)] out string? normalizedOrigin)
    {
        normalizedOrigin = null;

        if (uri?.IsAbsoluteUri != true
            || ContainsDisallowedCharacters(uri.OriginalString)
            || !string.Equals(uri.Scheme, Uri.UriSchemeHttps, StringComparison.OrdinalIgnoreCase)
            || !string.IsNullOrEmpty(uri.UserInfo)
            || uri.HostNameType == UriHostNameType.Unknown
            || string.IsNullOrEmpty(uri.Host))
        {
            return false;
        }

        if (requireOriginOnly
            && (uri.AbsolutePath != "/" || !string.IsNullOrEmpty(uri.Query) || !string.IsNullOrEmpty(uri.Fragment)))
        {
            return false;
        }

        normalizedOrigin = uri.GetLeftPart(UriPartial.Authority);
        return true;
    }

    private static bool ContainsDisallowedCharacters(string value)
    {
        foreach (char character in value)
        {
            if (char.IsWhiteSpace(character) || char.IsControl(character) || character == '\\')
            {
                return true;
            }
        }

        return false;
    }
}
