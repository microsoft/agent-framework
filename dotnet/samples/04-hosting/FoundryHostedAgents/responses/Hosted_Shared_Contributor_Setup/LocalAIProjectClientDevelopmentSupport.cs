// Copyright (c) Microsoft. All rights reserved.

using Azure.Core;

namespace Hosted_Shared_Contributor_Setup;

/// <summary>
/// Adapts Foundry project client requests to a locally hosted agent immediately before transport.
/// </summary>
/// <remarks>
/// Local development clients present an HTTPS endpoint to the bearer-token pipeline so it can
/// attach a token. This handler rewrites that endpoint to loopback HTTP and maps the project
/// client's <c>/openai/v1/responses</c> route onto the container contract's <c>/responses</c> route.
/// </remarks>
public sealed class LocalHostedAgentTransportHandler : DelegatingHandler
{
    private const string OpenAIPathPrefix = "/openai/v1";
    private const string ResponsesPath = $"{OpenAIPathPrefix}/responses";

    private readonly Uri _localEndpoint;

    /// <summary>
    /// Initializes a new instance that routes requests to <paramref name="localEndpoint"/>.
    /// </summary>
    /// <param name="localEndpoint">The loopback HTTP endpoint hosting the local agent.</param>
    public LocalHostedAgentTransportHandler(Uri localEndpoint)
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

        var uriBuilder = new UriBuilder(uri)
        {
            Scheme = Uri.UriSchemeHttp,
            Host = this._localEndpoint.Host,
            Port = this._localEndpoint.Port,
        };

        if (uri.AbsolutePath.StartsWith(ResponsesPath, StringComparison.OrdinalIgnoreCase))
        {
            uriBuilder.Path = uri.AbsolutePath[OpenAIPathPrefix.Length..];
        }

        request.RequestUri = uriBuilder.Uri;
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
