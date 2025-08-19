// Copyright (c) Microsoft. All rights reserved.

#if NET

using System;
using System.Net.Http;
using System.Threading;
using System.Threading.Tasks;

namespace Demo.DeclarativeWorkflow;

internal sealed record class HttpResponseIntercept(HttpMethod RequestMethod, Uri? RequestUri, string? ResponseContent);

internal sealed class HttpInterceptHandler : HttpClientHandler
{
    public Func<HttpResponseIntercept, ValueTask>? OnIntercept { get; set; }

    protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
    {
        // Call the inner handler to process the request and get the response
        HttpResponseMessage response = await base.SendAsync(request, cancellationToken);

        // Intercept and modify the response
        string? responseContent = null;
        if (response.Content != null)
        {
            responseContent = await response.Content.ReadAsStringAsync(cancellationToken);

            response.Content = new StringContent(responseContent);
        }

        if (this.OnIntercept is not null)
        {
            // Invoke the intercept callback if it is set
            await this.OnIntercept(new HttpResponseIntercept(request.Method, request.RequestUri, responseContent)).ConfigureAwait(false);
        }

        return response;
    }
}

#endif
