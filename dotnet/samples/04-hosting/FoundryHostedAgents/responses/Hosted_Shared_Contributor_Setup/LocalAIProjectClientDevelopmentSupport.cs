// Copyright (c) Microsoft. All rights reserved.

using Azure.Core;

namespace Hosted_Shared_Contributor_Setup;

/// <summary>
/// Rewrites an HTTPS request to a loopback HTTP endpoint immediately before transport.
/// </summary>
/// <remarks>
/// Local development clients present an HTTPS endpoint to the bearer-token pipeline so it can
/// attach a token, then use this handler to reach a loopback HTTP server.
/// </remarks>
public sealed class LocalHttpSchemeRewriteHandler : DelegatingHandler
{
    private readonly Uri _localEndpoint;

    /// <summary>
    /// Initializes a new instance that routes requests to <paramref name="localEndpoint"/>.
    /// </summary>
    /// <param name="localEndpoint">The loopback HTTP endpoint hosting the local agent.</param>
    public LocalHttpSchemeRewriteHandler(Uri localEndpoint)
        : base(new HttpClientHandler())
    {
        ArgumentNullException.ThrowIfNull(localEndpoint);
        if (!localEndpoint.IsLoopback
            || localEndpoint.Scheme != Uri.UriSchemeHttp)
        {
            throw new ArgumentException(
                "The local endpoint must be an HTTP loopback URI.",
                nameof(localEndpoint));
        }

        this._localEndpoint = localEndpoint;
    }

    /// <inheritdoc/>
    protected override Task<HttpResponseMessage> SendAsync(
        HttpRequestMessage request,
        CancellationToken cancellationToken)
    {
        this.RewriteUri(request);
        return base.SendAsync(request, cancellationToken);
    }

    private void RewriteUri(HttpRequestMessage request)
    {
        Uri uri = request.RequestUri
            ?? throw new InvalidOperationException("The local request URI is missing.");
        if (!uri.IsLoopback)
        {
            throw new InvalidOperationException(
                "The local HTTP rewrite policy can only target a loopback endpoint.");
        }

        if (uri.Scheme == Uri.UriSchemeHttps)
        {
            request.RequestUri =
                new UriBuilder(uri)
                {
                    Scheme = Uri.UriSchemeHttp,
                    Host = this._localEndpoint.Host,
                    Port = this._localEndpoint.Port,
                }.Uri;
        }
    }
}

/// <summary>
/// Supplies a placeholder bearer token for a loopback server that does not validate authentication.
/// </summary>
/// <remarks>
/// This credential is only for local sample development. It must not be used with remote services.
/// </remarks>
public sealed class LocalDevelopmentTokenCredential : TokenCredential
{
    private static readonly AccessToken s_token =
        new("local-development", DateTimeOffset.MaxValue);

    /// <inheritdoc/>
    public override AccessToken GetToken(
        TokenRequestContext requestContext,
        CancellationToken cancellationToken) =>
        s_token;

    /// <inheritdoc/>
    public override ValueTask<AccessToken> GetTokenAsync(
        TokenRequestContext requestContext,
        CancellationToken cancellationToken) =>
        new(s_token);
}
