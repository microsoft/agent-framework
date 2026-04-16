// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Net;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Threading;
using System.Threading.Tasks;
using Azure.Core;

namespace Microsoft.Agents.AI.Foundry.Hosting;

/// <summary>
/// An <see cref="DelegatingHandler"/> that:
/// <list type="bullet">
///   <item>Acquires a fresh Azure bearer token (scope: <c>https://cognitiveservices.azure.com/.default</c>) per request.</item>
///   <item>Injects the <c>Foundry-Features</c> header from <c>FOUNDRY_AGENT_TOOLSET_FEATURES</c> when non-empty.</item>
///   <item>Retries on HTTP 429, 500, 502, and 503 with exponential back-off (max 3 attempts, per spec §7).</item>
/// </list>
/// </summary>
internal sealed class FoundryToolboxBearerTokenHandler : DelegatingHandler
{
    private const int MaxRetries = 3;
    private static readonly TokenRequestContext s_tokenContext =
        new(["https://cognitiveservices.azure.com/.default"]);

    private readonly TokenCredential _credential;
    private readonly string? _featuresHeaderValue;

    internal FoundryToolboxBearerTokenHandler(TokenCredential credential, string? featuresHeaderValue)
    {
        this._credential = credential;
        this._featuresHeaderValue = featuresHeaderValue;
    }

    protected override async Task<HttpResponseMessage> SendAsync(
        HttpRequestMessage request,
        CancellationToken cancellationToken)
    {
        var token = await this._credential
            .GetTokenAsync(s_tokenContext, cancellationToken)
            .ConfigureAwait(false);

        request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", token.Token);

        if (!string.IsNullOrEmpty(this._featuresHeaderValue))
        {
            request.Headers.TryAddWithoutValidation("Foundry-Features", this._featuresHeaderValue);
        }

        for (int attempt = 0; attempt < MaxRetries; attempt++)
        {
            // Clone the request for retries (the original request cannot be sent twice)
            HttpRequestMessage requestToSend = attempt == 0
                ? request
                : await CloneRequestAsync(request, cancellationToken).ConfigureAwait(false);

            var response = await base.SendAsync(requestToSend, cancellationToken).ConfigureAwait(false);

            if (response.StatusCode is not (HttpStatusCode.TooManyRequests
                or HttpStatusCode.InternalServerError
                or HttpStatusCode.BadGateway
                or HttpStatusCode.ServiceUnavailable))
            {
                return response;
            }

            response.Dispose();

            if (attempt < MaxRetries - 1)
            {
                await Task.Delay(TimeSpan.FromSeconds(Math.Pow(2, attempt)), cancellationToken)
                    .ConfigureAwait(false);
            }
        }

        // Final attempt after backoff exhausted — return last response (already disposed above, so resend)
        return await base.SendAsync(
            await CloneRequestAsync(request, cancellationToken).ConfigureAwait(false),
            cancellationToken).ConfigureAwait(false);
    }

    private static async Task<HttpRequestMessage> CloneRequestAsync(
        HttpRequestMessage original,
        CancellationToken cancellationToken)
    {
        var clone = new HttpRequestMessage(original.Method, original.RequestUri);

        foreach (var header in original.Headers)
        {
            clone.Headers.TryAddWithoutValidation(header.Key, header.Value);
        }

        if (original.Content is not null)
        {
            var contentBytes = await original.Content.ReadAsByteArrayAsync(cancellationToken).ConfigureAwait(false);
            clone.Content = new ByteArrayContent(contentBytes);

            foreach (var header in original.Content.Headers)
            {
                clone.Content.Headers.TryAddWithoutValidation(header.Key, header.Value);
            }
        }

        return clone;
    }
}
